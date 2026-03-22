"""测试TodoManager"""

import pytest

from src.core.config import TODO_MAX_ITEMS
from src.tools.todo import TodoManager, todo_write


class TestTodoManager:
    @pytest.fixture
    def manager(self):
        return TodoManager()

    def test_update_and_render(self, manager):
        result = manager.update([
            {"content": "Task 1", "status": "completed"},
            {"content": "Task 2", "status": "in_progress"},
            {"content": "Task 3", "status": "pending"},
        ])
        assert "3条" in result

        rendered = manager.render()
        assert "[x] Task 1" in rendered
        assert "[>] Task 2" in rendered
        assert "[ ] Task 3" in rendered

    def test_max_items_limit(self, manager):
        items = [{"content": f"Task {i}", "status": "pending"} for i in range(TODO_MAX_ITEMS + 1)]
        result = manager.update(items)
        assert "[ERROR]" in result

    def test_single_in_progress(self, manager):
        result = manager.update([
            {"content": "Task 1", "status": "in_progress"},
            {"content": "Task 2", "status": "in_progress"},
        ])
        assert "[ERROR]" in result

    def test_has_open_items(self, manager):
        assert manager.has_open_items() is False

        manager.update([{"content": "Task", "status": "pending"}])
        assert manager.has_open_items() is True

        manager.update([{"content": "Task", "status": "completed"}])
        assert manager.has_open_items() is False

    def test_empty_render(self, manager):
        assert "无待办" in manager.render()

    def test_get_items(self, manager):
        manager.update([{"content": "Task", "status": "pending"}])
        items = manager.get_items()
        assert len(items) == 1
        assert items[0].content == "Task"

    def test_todo_write_tool(self):
        result = todo_write.invoke({"todos": [
            {"content": "Tool task", "status": "pending"},
        ]})
        assert "1条" in result
