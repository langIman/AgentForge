"""AgentForge Lite — Agent状态定义"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


class TodoItem(BaseModel):
    """单条待办项"""
    content: str
    status: str = "pending"  # pending | in_progress | completed


class AgentState(TypedDict):
    """Agent状态（Phase 1 + Phase 2）

    后续Phase只需新增字段，不修改已有字段。
    """
    # Phase 1
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    todos: list[TodoItem]
    rounds_since_todo: int
    # Phase 2
    token_count: int
    compressed: bool
    tasks_snapshot: str
