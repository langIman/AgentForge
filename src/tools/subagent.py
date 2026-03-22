"""AgentForge Lite — 子Agent工具：独立子图探索，只返回摘要"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from src.core.config import MODEL_NAME, SUBAGENT_MAX_ROUNDS


@tool
def spawn_subagent(prompt: str) -> str:
    """生成一个子Agent来执行探索性任务。

    子Agent拥有精简工具集（仅read_file和bash），运行在独立图中，
    不共享主Agent的checkpointer，完成后只返回最终摘要。

    Args:
        prompt: 交给子Agent的任务描述

    Returns:
        子Agent的执行结果摘要
    """
    # 延迟导入避免循环依赖
    from langchain_openai import ChatOpenAI

    from src.core.config import OPENAI_API_BASE, OPENAI_API_KEY
    from src.core.graph import build_graph
    from src.core.state import AgentState
    from src.tools.bash import bash
    from src.tools.file_ops import read_file

    child_tools = [read_file, bash]

    child_model = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
    ).bind_tools(child_tools)

    def child_pre_process(state):
        return {}

    def child_agent(state):
        system = SystemMessage(
            content="你是一个探索型子Agent。完成任务后，请给出简洁的总结。"
        )
        messages = [system] + state["messages"]
        response = child_model.invoke(messages)
        return {"messages": [response]}

    def child_should_continue(state):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            # 限制轮次
            ai_count = sum(1 for m in state["messages"] if isinstance(m, AIMessage))
            if ai_count >= SUBAGENT_MAX_ROUNDS:
                return "end"
            return "continue"
        return "end"

    def child_post_process(state):
        return {}

    child_nodes = {
        "pre_process": child_pre_process,
        "agent": child_agent,
        "should_continue": child_should_continue,
        "post_process": child_post_process,
    }

    # 独立子图，无checkpointer
    child_graph = build_graph(AgentState, child_nodes, child_tools)

    try:
        result = child_graph.invoke(
            {
                "messages": [HumanMessage(content=prompt)],
                "session_id": "subagent",
                "todos": [],
                "rounds_since_todo": 0,
            }
        )
        # 只返回最终AI消息的内容
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content[:5000]
        return "[子Agent未产生输出]"
    except Exception as e:
        return f"[子Agent错误] {type(e).__name__}: {e}"
