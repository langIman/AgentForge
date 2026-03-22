"""AgentForge Lite — StateGraph构建（永不修改）"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode


def build_graph(state_class, nodes, tools, checkpointer=None):
    """构建标准Agent图拓扑。

    pre_process -> agent -> should_continue? -> tools -> post_process -> pre_process
                                             -> END

    此函数永不修改，所有定制通过nodes和tools注入。
    """
    graph = StateGraph(state_class)
    graph.add_node("pre_process", nodes["pre_process"])
    graph.add_node("agent", nodes["agent"])
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("post_process", nodes["post_process"])

    graph.add_edge(START, "pre_process")
    graph.add_edge("pre_process", "agent")
    graph.add_conditional_edges(
        "agent",
        nodes["should_continue"],
        {"continue": "tools", "end": END},
    )
    graph.add_edge("tools", "post_process")
    graph.add_edge("post_process", "pre_process")

    return graph.compile(checkpointer=checkpointer)
