"""AgentForge Lite — TodoManager + todo_write工具"""

from langchain_core.tools import tool

from src.core.config import TODO_MAX_ITEMS
from src.core.state import TodoItem


class TodoManager:
    """待办事项管理器。

    约束：
    - 最多20条
    - 同时仅1个in_progress
    """

    def __init__(self):
        self._items: list[TodoItem] = []

    def update(self, items: list[dict]) -> str:
        """更新整个待办列表。

        Args:
            items: 待办项列表，每项包含 content 和 status

        Returns:
            更新结果描述
        """
        if len(items) > TODO_MAX_ITEMS:
            return f"[ERROR] 待办项超过上限（{TODO_MAX_ITEMS}条），当前 {len(items)} 条"

        # 检查同时仅1个in_progress
        in_progress = [i for i in items if i.get("status") == "in_progress"]
        if len(in_progress) > 1:
            return "[ERROR] 同时只能有1个 in_progress 的待办项"

        self._items = [TodoItem(**item) for item in items]
        return f"待办列表已更新（{len(self._items)}条）\n{self.render()}"

    def render(self) -> str:
        """渲染待办列表为文本格式"""
        if not self._items:
            return "[无待办事项]"

        lines = []
        for item in self._items:
            if item.status == "completed":
                prefix = "[x]"
            elif item.status == "in_progress":
                prefix = "[>]"
            else:
                prefix = "[ ]"
            lines.append(f"{prefix} {item.content}")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        """是否有未完成的项目"""
        return any(item.status in ("pending", "in_progress") for item in self._items)

    def get_items(self) -> list[TodoItem]:
        """获取当前所有待办项"""
        return list(self._items)


# 全局单例
todo_manager = TodoManager()


@tool
def todo_write(todos: list[dict]) -> str:
    """更新待办事项列表。

    Args:
        todos: 待办项列表，每项包含:
            - content (str): 任务内容
            - status (str): pending | in_progress | completed

    Returns:
        更新后的待办列表
    """
    return todo_manager.update(todos)
