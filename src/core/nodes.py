"""AgentForge Lite — 图节点实现"""

import asyncio

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.core.config import MODEL_NAME, TODO_NAG_INTERVAL, TOKEN_THRESHOLD
from src.memory.compressor import auto_compact, estimate_tokens, micro_compact
from src.memory.transcript import transcript_repo
from src.tools.todo import todo_manager


def get_system_prompt(skill_loader=None) -> str:
    """构建系统提示词"""
    base = (
        "你是 AgentForge，一个强大的AI助手，能够执行bash命令、读写文件、管理待办事项、"
        "生成子Agent进行探索、以及按需加载技能。\n\n"
        "## 工作原则\n"
        "- 先理解任务，再拆分为待办事项\n"
        "- 每次只做一件事，完成后标记为completed\n"
        "- 使用bash执行命令，使用file工具操作文件\n"
        "- 复杂探索交给子Agent，避免主上下文膨胀\n"
        "- 使用task_create/task_update管理持久化任务\n"
        "- 当上下文过长时，使用compact工具手动压缩\n"
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


def make_nodes(model, skill_loader=None):
    """创建图节点字典。

    Returns:
        dict with keys: pre_process, agent, should_continue, post_process
    """

    def pre_process(state):
        """预处理：micro_compact每轮执行 + auto_compact超阈值触发。

        不改图拓扑，所有压缩逻辑在此节点内完成。
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
            updates["messages"] = compressed_msgs
            updates["compressed"] = True
            updates["token_count"] = estimate_tokens(compressed_msgs)
        else:
            updates["compressed"] = False

        return updates

    def agent(state):
        """调用LLM"""
        system_prompt = get_system_prompt(skill_loader)
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
