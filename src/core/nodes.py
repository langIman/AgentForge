"""AgentForge Lite — 图节点实现"""

import asyncio

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.core.config import MODEL_NAME, TODO_NAG_INTERVAL, TOKEN_THRESHOLD
from src.memory.compressor import auto_compact, estimate_tokens, micro_compact
from src.memory.transcript import transcript_repo
from src.tools.todo import todo_manager


def get_system_prompt(skill_loader=None, has_team=False) -> str:
    """构建系统提示词"""
    from datetime import date
    today = date.today().isoformat()

    base = (
        f"你是 AgentForge，一个强大的AI助手。当前日期: {today}。\n\n"
        "## 重要规则\n"
        "- 你的训练数据可能已过时。当web_search返回的信息与你的记忆冲突时，"
        "**始终信任搜索结果**，因为搜索结果是实时的。\n"
        "- 不要质疑搜索结果中的日期或事件，直接基于搜索结果回答用户。\n\n"
        "## 工作原则\n"
        "- 先理解任务，再拆分为待办事项\n"
        "- 每次只做一件事，完成后标记为completed\n"
        "- 使用bash执行命令，使用file工具操作文件\n"
        "- 复杂探索交给子Agent，避免主上下文膨胀\n"
        "- 使用task_create/task_update管理持久化任务\n"
        "- 当上下文过长时，使用compact工具手动压缩\n"
        "- 需要实时信息时，使用web_search搜索互联网\n"
    )
    if has_team:
        base += (
            "\n## 团队管理 (Phase 3)\n"
            "- 使用 spawn_teammate 创建Worker执行子任务\n"
            "- 使用 send_message/read_inbox 与Worker通信\n"
            "- 使用 broadcast 群发消息给所有Worker\n"
            "- 使用 background_run 执行耗时命令，不阻塞当前对话\n"
            "- 使用 shutdown_request 请求Worker优雅退出\n"
            "- 使用 plan_approval 向Worker发送计划请求审批\n"
        )
    if skill_loader:
        skills_desc = skill_loader.get_descriptions()
        if skills_desc:
            base += f"\n## 可用技能\n{skills_desc}\n"
            base += "使用 load_skill 工具加载技能的完整内容。\n"
    return base


def _run_async(coro):
    """在同步上下文中运行async协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def make_nodes(model, skill_loader=None, bg_manager=None, mailbox=None):
    """创建图节点字典。

    Args:
        model: 已bind_tools的LLM实例
        skill_loader: 技能加载器（可选）
        bg_manager: 后台任务管理器（Phase 3，可选）
        mailbox: 消息总线（Phase 3，可选）

    Returns:
        dict with keys: pre_process, agent, should_continue, post_process
    """

    def pre_process(state):
        """预处理：压缩 + 后台通知注入 + 收件箱注入。

        不改图拓扑，所有预处理逻辑在此节点内完成。
        """
        messages = list(state["messages"])
        updates = {}

        # 检查是否有手动compact请求（来自compact工具的返回值）
        compact_requested = False
        for msg in reversed(messages[-5:]):
            if isinstance(msg, ToolMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if "[COMPACT_REQUESTED]" in content:
                    compact_requested = True
                    break

        # 层1: micro_compact — 每轮执行，截断旧ToolMessage
        messages = micro_compact(messages, keep_recent=3)

        # 估算token
        token_count = estimate_tokens(messages)
        updates["token_count"] = token_count

        # 层2: auto_compact — token超阈值 或 手动请求
        if token_count > TOKEN_THRESHOLD or compact_requested:
            session_id = state.get("session_id", "unknown")
            compressed_msgs = _run_async(
                auto_compact(messages, model, session_id, transcript_repo)
            )
            messages = compressed_msgs
            updates["messages"] = messages
            updates["compressed"] = True
            updates["token_count"] = estimate_tokens(messages)
        else:
            updates["compressed"] = False

        # Phase 3: 注入后台任务通知
        if bg_manager:
            notifications = bg_manager.drain_notifications()
            if notifications:
                lines = []
                for n in notifications:
                    lines.append(f"[{n['status']}] task {n['task_id']}: {n['result']}")
                notif_msg = SystemMessage(
                    content="<bg_notifications>\n" + "\n".join(lines) + "\n</bg_notifications>"
                )
                messages = updates.get("messages", messages)
                messages.append(notif_msg)
                updates["messages"] = messages

        # Phase 3: 注入Lead收件箱消息
        if mailbox:
            agent_name = state.get("agent_name", "lead")
            inbox = mailbox.read_inbox(agent_name)
            if inbox:
                lines = []
                for m in inbox:
                    lines.append(f"[{m['type']}] {m['from']}: {m['content']}")
                inbox_msg = SystemMessage(
                    content="<inbox>\n" + "\n".join(lines) + "\n</inbox>"
                )
                messages = updates.get("messages", messages)
                messages.append(inbox_msg)
                updates["messages"] = messages

        return updates

    def agent(state):
        """调用LLM"""
        has_team = bg_manager is not None or mailbox is not None
        system_prompt = get_system_prompt(skill_loader, has_team=has_team)
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = model.invoke(messages)
        return {"messages": [response]}

    def should_continue(state):
        """判断是否需要执行工具"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "continue"
        return "end"

    def post_process(state):
        """后处理：Nag机制 — 超过N轮未更新todo则提醒"""
        rounds = state.get("rounds_since_todo", 0) + 1

        if rounds >= TODO_NAG_INTERVAL and todo_manager.has_open_items():
            reminder = SystemMessage(
                content=(
                    "<reminder>你有未完成的待办事项，请使用 todo_write 工具更新进度。"
                    "完成的项目请标记为 completed。</reminder>"
                )
            )
            return {"messages": [reminder], "rounds_since_todo": 0}

        return {"rounds_since_todo": rounds}

    return {
        "pre_process": pre_process,
        "agent": agent,
        "should_continue": should_continue,
        "post_process": post_process,
    }
