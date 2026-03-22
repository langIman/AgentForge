"""AgentForge Lite — Worker专用图

Worker与Lead共用同一个图拓扑（build_graph），但有自己的：
1. 受限工具集：bash, read_file, write_file, edit_file, send_message, read_inbox
2. 专用节点：system prompt包含身份信息，pre_process注入收件箱消息
3. 无checkpointer：Worker是临时的，不需要持久化

Worker生命周期：
  Lead spawn → Worker执行任务 → 完成/收到shutdown → 退出
"""

from langchain_core.messages import AIMessage, SystemMessage

from src.core.graph import build_graph
from src.core.state import AgentState
from src.memory.compressor import micro_compact


def build_worker_graph(name: str, role: str, model, mailbox, tools):
    """构建Worker专用图。

    Args:
        name: Worker名称
        role: Worker角色描述
        model: 已bind_tools的LLM实例
        mailbox: InMemoryMailbox实例
        tools: Worker的工具列表

    Returns:
        编译后的Worker图（无checkpointer）
    """

    def worker_pre_process(state):
        """Worker预处理：micro_compact + 注入收件箱消息"""
        messages = list(state["messages"])
        updates = {}

        # micro_compact截断旧工具输出
        messages = micro_compact(messages, keep_recent=3)

        # 检查收件箱
        inbox = mailbox.read_inbox(name)
        if inbox:
            lines = []
            for m in inbox:
                lines.append(f"[{m['type']}] {m['from']}: {m['content']}")

                # 检查是否收到shutdown请求
                if m.get("type") == "shutdown":
                    lines.append(">>> 收到关闭请求，请尽快完成当前工作并汇报结果。")

            inbox_msg = SystemMessage(
                content=f"<inbox>\n" + "\n".join(lines) + "\n</inbox>"
            )
            messages.append(inbox_msg)
            updates["messages"] = messages

        return updates

    def worker_agent(state):
        """Worker LLM调用：system prompt包含身份和角色"""
        system_prompt = (
            f"你是 {name}，角色：{role}。\n\n"
            f"## 工作原则\n"
            f"- 专注完成分配给你的任务\n"
            f"- 完成后用 send_message 向 lead 汇报结果\n"
            f"- 收到 shutdown 请求时，尽快完成当前工作并汇报\n"
            f"- 用 read_inbox 查看是否有新消息\n"
        )
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = model.invoke(messages)
        return {"messages": [response]}

    def worker_should_continue(state):
        """判断是否继续"""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "continue"
        return "end"

    def worker_post_process(state):
        """Worker后处理：无nag机制"""
        return {}

    nodes = {
        "pre_process": worker_pre_process,
        "agent": worker_agent,
        "should_continue": worker_should_continue,
        "post_process": worker_post_process,
    }

    return build_graph(AgentState, nodes, tools)
