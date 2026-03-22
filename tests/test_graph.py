"""测试图构建和节点逻辑"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.core.graph import build_graph
from src.core.nodes import get_system_prompt, make_nodes
from src.core.state import AgentState
from src.tools.todo import TodoManager


class TestGraphBuild:
    def test_build_graph_compiles(self):
        """测试图可以正常编译"""
        mock_model = MagicMock()
        mock_model.invoke.return_value = AIMessage(content="hello")

        tools = []
        nodes = {
            "pre_process": lambda state: {},
            "agent": lambda state: {"messages": [AIMessage(content="test")]},
            "should_continue": lambda state: "end",
            "post_process": lambda state: {},
        }

        graph = build_graph(AgentState, nodes, tools)
        assert graph is not None


class TestNodes:
    def test_should_continue_with_tool_calls(self):
        """有tool_calls时返回continue"""
        mock_model = MagicMock()
        nodes = make_nodes(mock_model)

        tool_call_msg = AIMessage(
            content="",
            tool_calls=[{"id": "1", "name": "bash", "args": {"command": "ls"}}],
        )
        state = {"messages": [tool_call_msg]}
        assert nodes["should_continue"](state) == "continue"

    def test_should_continue_without_tool_calls(self):
        """无tool_calls时返回end"""
        mock_model = MagicMock()
        nodes = make_nodes(mock_model)

        state = {"messages": [AIMessage(content="done")]}
        assert nodes["should_continue"](state) == "end"

    def test_post_process_nag(self):
        """超过N轮且有待办时触发nag"""
        mock_model = MagicMock()
        nodes = make_nodes(mock_model)

        # 设置全局todo_manager有未完成项
        with patch("src.core.nodes.todo_manager") as mock_tm:
            mock_tm.has_open_items.return_value = True

            state = {"rounds_since_todo": 2}  # NAG_INTERVAL=3, rounds+1=3 >= 3
            result = nodes["post_process"](state)

            assert "messages" in result
            assert result["rounds_since_todo"] == 0

    def test_post_process_no_nag(self):
        """未到N轮不触发nag"""
        mock_model = MagicMock()
        nodes = make_nodes(mock_model)

        state = {"rounds_since_todo": 0}
        result = nodes["post_process"](state)

        assert "messages" not in result
        assert result["rounds_since_todo"] == 1

    def test_post_process_no_nag_when_no_open_items(self):
        """到了N轮但无待办也不触发"""
        mock_model = MagicMock()
        nodes = make_nodes(mock_model)

        with patch("src.core.nodes.todo_manager") as mock_tm:
            mock_tm.has_open_items.return_value = False

            state = {"rounds_since_todo": 5}
            result = nodes["post_process"](state)

            assert "messages" not in result


class TestSystemPrompt:
    def test_base_prompt(self):
        prompt = get_system_prompt()
        assert "AgentForge" in prompt

    def test_with_skill_loader(self):
        mock_loader = MagicMock()
        mock_loader.get_descriptions.return_value = "- **test**: A test skill"

        prompt = get_system_prompt(mock_loader)
        assert "test" in prompt
        assert "load_skill" in prompt

    def test_without_skills(self):
        mock_loader = MagicMock()
        mock_loader.get_descriptions.return_value = ""

        prompt = get_system_prompt(mock_loader)
        assert "可用技能" not in prompt
