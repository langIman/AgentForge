"""测试三层压缩机制"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.memory.compressor import auto_compact, estimate_tokens, micro_compact


# ─── estimate_tokens ───


class TestEstimateTokens:
    def test_basic(self):
        msgs = [HumanMessage(content="hello world")]
        tokens = estimate_tokens(msgs)
        assert tokens > 0

    def test_longer_is_more(self):
        short = [HumanMessage(content="hi")]
        long = [HumanMessage(content="hello " * 1000)]
        assert estimate_tokens(long) > estimate_tokens(short)

    def test_empty(self):
        assert estimate_tokens([]) == 0


# ─── micro_compact ───


class TestMicroCompact:
    def test_truncates_old_tool_messages(self):
        msgs = [
            HumanMessage(content="go"),
            ToolMessage(content="x" * 200, name="bash", tool_call_id="1"),
            AIMessage(content="ok"),
            ToolMessage(content="y" * 200, name="read_file", tool_call_id="2"),
            AIMessage(content="ok2"),
            ToolMessage(content="z" * 200, name="bash", tool_call_id="3"),
            AIMessage(content="ok3"),
            ToolMessage(content="w" * 200, name="edit_file", tool_call_id="4"),
        ]
        result = micro_compact(msgs, keep_recent=2)

        # 前两个ToolMessage应被截断
        assert "[cleared: bash]" in result[1].content
        assert "[cleared: read_file]" in result[3].content
        # 后两个保留
        assert result[5].content == "z" * 200
        assert result[7].content == "w" * 200

    def test_keeps_short_messages(self):
        msgs = [
            ToolMessage(content="short", name="bash", tool_call_id="1"),
            ToolMessage(content="x" * 200, name="bash", tool_call_id="2"),
        ]
        result = micro_compact(msgs, keep_recent=0)
        # "short"（<100字符）不会被截断
        assert result[0].content == "short"
        # 长的会被截断
        assert "[cleared" in result[1].content

    def test_empty_messages(self):
        result = micro_compact([], keep_recent=3)
        assert result == []

    def test_no_tool_messages(self):
        msgs = [HumanMessage(content="hello"), AIMessage(content="world")]
        result = micro_compact(msgs, keep_recent=3)
        assert len(result) == 2
        assert result[0].content == "hello"


# ─── auto_compact ───


class TestAutoCompact:
    @pytest.mark.asyncio
    async def test_auto_compact_produces_summary(self):
        """auto_compact应保存存档并生成摘要消息"""
        messages = [
            HumanMessage(content="请帮我写个函数"),
            AIMessage(content="好的，我来写"),
            ToolMessage(content="def foo(): pass", name="write_file", tool_call_id="1"),
        ]

        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = AIMessage(content="用户请求写函数，已完成。")

        mock_transcript = AsyncMock()
        mock_transcript.save.return_value = 1

        result = await auto_compact(messages, mock_model, "test-session", mock_transcript)

        # 应该保存存档
        mock_transcript.save.assert_called_once()

        # 应该调用LLM生成摘要
        mock_model.ainvoke.assert_called_once()

        # 结果应该是两条消息：压缩提示 + AI确认
        assert len(result) == 2
        assert isinstance(result[0], HumanMessage)
        assert "[上下文已压缩]" in result[0].content
        assert isinstance(result[1], AIMessage)

    @pytest.mark.asyncio
    async def test_auto_compact_handles_model_failure(self):
        """LLM失败时应降级处理"""
        messages = [HumanMessage(content="test")]

        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("API error")

        mock_transcript = AsyncMock()

        result = await auto_compact(messages, mock_model, "test-session", mock_transcript)

        # 应该仍然返回两条消息
        assert len(result) == 2
        assert "[摘要生成失败" in result[0].content

    @pytest.mark.asyncio
    async def test_auto_compact_handles_transcript_failure(self):
        """存档失败不应阻塞主流程"""
        messages = [HumanMessage(content="test")]

        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = AIMessage(content="summary")

        mock_transcript = AsyncMock()
        mock_transcript.save.side_effect = Exception("DB error")

        # 不应抛出异常
        result = await auto_compact(messages, mock_model, "test-session", mock_transcript)
        assert len(result) == 2
