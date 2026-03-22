"""AgentForge Lite — 手动压缩工具

Agent或用户可以主动触发上下文压缩，不必等到自动阈值。
实际压缩逻辑在 pre_process 节点中执行（通过 state 标志位触发）。
"""

from langchain_core.tools import tool


@tool
def compact() -> str:
    """手动触发上下文压缩。

    将当前对话历史存档到SQLite，然后用LLM生成摘要替换。
    适用于对话已经很长但还没到自动压缩阈值的场景。

    Returns:
        压缩触发确认（实际压缩在下一轮pre_process中执行）
    """
    # 实际压缩在 pre_process 节点中通过检查 state 来执行
    # 这里只是设置一个标志，通知 pre_process 执行压缩
    # 由于 tool 无法直接修改 state，我们通过返回特殊标记让 post_process 处理
    return "[COMPACT_REQUESTED] 已请求压缩上下文。将在下一轮处理中执行。"
