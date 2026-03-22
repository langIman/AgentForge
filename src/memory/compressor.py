"""AgentForge Lite — 三层上下文压缩

层1 micro_compact  : 每轮执行，截断旧ToolMessage为 [cleared]
层2 auto_compact   : token超阈值时，存档→摘要→替换
层3 manual compact : 用户/Agent手动触发（通过compact工具）

设计原则：不改图拓扑，全部在 pre_process 节点内调用。
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.core.config import TOKEN_THRESHOLD


def estimate_tokens(messages: list) -> int:
    """粗估token数（JSON字符数 / 4）

    不精确但足够用于判断是否需要压缩。
    """
    try:
        text = json.dumps(
            [{"type": type(m).__name__, "content": str(m.content)} for m in messages],
            ensure_ascii=False,
        )
        return len(text) // 4
    except Exception:
        return 0


def micro_compact(messages: list, keep_recent: int = 3) -> list:
    """层1: 截断旧ToolMessage为 [cleared]

    保留最近 keep_recent 个ToolMessage不动，
    其余超过100字符的截断为 [cleared: tool_name]。

    Args:
        messages: 消息列表
        keep_recent: 保留最近N个ToolMessage不截断

    Returns:
        处理后的消息列表（原地修改）
    """
    tool_indices = [
        (i, m) for i, m in enumerate(messages) if isinstance(m, ToolMessage)
    ]

    # 保留最近 keep_recent 个，截断其余
    to_truncate = tool_indices[:-keep_recent] if keep_recent else tool_indices

    for _idx, msg in to_truncate:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if len(content) > 100:
            tool_name = getattr(msg, "name", "unknown")
            msg.content = f"[cleared: {tool_name}]"

    return messages


async def auto_compact(messages: list, model, session_id: str,
                       transcript_repo) -> list:
    """层2: 自动压缩 — token超阈值时触发

    流程：
    1. 将当前消息存档到SQLite（TranscriptRepository）
    2. 用LLM生成对话摘要
    3. 用摘要消息替换全部历史

    Args:
        messages: 当前消息列表
        model: LLM实例（用于生成摘要）
        session_id: 会话ID
        transcript_repo: 对话存档仓库

    Returns:
        压缩后的消息列表（仅包含摘要）
    """
    # 1. 存档原始消息
    try:
        await transcript_repo.save(session_id, messages)
    except Exception:
        pass  # 存档失败不阻塞主流程

    # 2. 构建摘要请求
    summary_prompt = (
        "请简洁总结以下对话的关键信息，包括：\n"
        "1. 用户的主要需求和目标\n"
        "2. 已完成的操作和结果\n"
        "3. 当前进展和待处理事项\n"
        "4. 重要的文件路径、变量名等上下文\n\n"
        "对话内容：\n"
    )

    # 提取对话摘要素材（限制长度，避免摘要请求本身太大）
    summary_parts = []
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        if isinstance(m, HumanMessage):
            summary_parts.append(f"用户: {content[:500]}")
        elif isinstance(m, AIMessage) and content:
            summary_parts.append(f"AI: {content[:500]}")
        elif isinstance(m, ToolMessage):
            tool_name = getattr(m, "name", "tool")
            summary_parts.append(f"工具[{tool_name}]: {content[:200]}")

    summary_text = "\n".join(summary_parts[-50:])  # 最近50条

    try:
        summary_response = await model.ainvoke(
            [HumanMessage(content=summary_prompt + summary_text)]
        )
        summary_content = summary_response.content
    except Exception as e:
        summary_content = f"[摘要生成失败: {e}]\n最近操作: {summary_text[-1000:]}"

    # 3. 用摘要替换全部历史
    compressed = [
        HumanMessage(content=f"[上下文已压缩]\n{summary_content}"),
        AIMessage(content="明白，我已了解之前的对话上下文。请继续。"),
    ]

    return compressed


async def manual_compact(messages: list, model, session_id: str,
                         transcript_repo) -> list:
    """层3: 手动压缩 — 用户/Agent通过compact工具触发

    与auto_compact逻辑相同，但不受阈值限制。
    """
    return await auto_compact(messages, model, session_id, transcript_repo)
