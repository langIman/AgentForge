"""测试后台命令运行器"""

import time
from unittest.mock import patch

import pytest

from src.tools.background import BackgroundCommandRunner


class TestBackgroundCommandRunner:
    @pytest.fixture
    def manager(self):
        return BackgroundCommandRunner()

    @pytest.fixture(autouse=True)
    def patch_workspace(self, tmp_path):
        with patch("src.tools.background.WORKSPACE_ROOT", tmp_path):
            yield

    def test_run_returns_task_id(self, manager):
        """run()立即返回task_id"""
        task_id = manager.run("echo hello", timeout=10)
        assert isinstance(task_id, str)
        assert len(task_id) == 8

    def test_run_does_not_block(self, manager):
        """run()不阻塞——sleep 5秒的命令应在<1秒内返回"""
        start = time.time()
        manager.run("sleep 5", timeout=10)
        elapsed = time.time() - start
        assert elapsed < 1.0

    def test_notification_after_completion(self, manager):
        """任务完成后通知进入队列"""
        manager.run("echo done", timeout=10)
        # 等待命令完成
        time.sleep(1)
        notifications = manager.drain_notifications()
        assert len(notifications) == 1
        assert notifications[0]["status"] == "completed"
        assert "done" in notifications[0]["result"]

    def test_drain_clears_queue(self, manager):
        """drain后队列为空"""
        manager.run("echo 1", timeout=10)
        time.sleep(1)
        manager.drain_notifications()
        assert manager.drain_notifications() == []

    def test_timeout_notification(self, manager):
        """超时命令产生timeout通知"""
        manager.run("sleep 30", timeout=1)
        time.sleep(3)  # 等待超时+通知
        notifications = manager.drain_notifications()
        assert len(notifications) == 1
        assert notifications[0]["status"] == "timeout"

    def test_get_status(self, manager):
        """查询任务状态"""
        task_id = manager.run("echo hi", timeout=10)
        # 刚启动时可能是running
        status = manager.get_status(task_id)
        assert status["status"] in ("running", "completed")

        # 等待完成
        time.sleep(1)
        status = manager.get_status(task_id)
        assert status["status"] == "completed"

    def test_unknown_task(self, manager):
        """查询不存在的任务"""
        status = manager.get_status("nonexistent")
        assert status["status"] == "unknown"

    def test_list_tasks(self, manager):
        """列出所有任务"""
        manager.run("echo 1", timeout=10)
        manager.run("echo 2", timeout=10)
        tasks = manager.list_tasks()
        assert len(tasks) == 2

    def test_multiple_notifications(self, manager):
        """多个任务的通知都能收到"""
        manager.run("echo a", timeout=10)
        manager.run("echo b", timeout=10)
        time.sleep(2)
        notifications = manager.drain_notifications()
        assert len(notifications) == 2
