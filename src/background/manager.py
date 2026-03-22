"""AgentForge Lite — 后台任务管理器

用 threading + subprocess 实现非阻塞后台命令执行。
接口与 plan.md 的 asyncio 版一致，升级只需换实现。

设计：
- run() 立即返回 task_id，命令在后台线程执行
- 完成后结果进入通知队列
- drain_notifications() 在 pre_process 中调用，注入对话
"""

import queue
import subprocess
import threading
import time
from uuid import uuid4

from src.core.config import WORKSPACE_ROOT


class BackgroundManager:
    """后台任务管理器 — 线程实现"""

    def __init__(self):
        self._tasks: dict[str, threading.Thread] = {}
        self._results: dict[str, dict] = {}
        self._notifications: queue.Queue = queue.Queue()

    def run(self, command: str, timeout: int = 300) -> str:
        """启动后台命令，立即返回 task_id。

        Args:
            command: Shell命令
            timeout: 超时秒数（默认300）

        Returns:
            task_id 字符串
        """
        task_id = uuid4().hex[:8]
        thread = threading.Thread(
            target=self._execute,
            args=(task_id, command, timeout),
            daemon=True,
        )
        self._tasks[task_id] = thread
        self._results[task_id] = {"status": "running", "started_at": time.time()}
        thread.start()
        return task_id

    def _execute(self, task_id: str, command: str, timeout: int):
        """后台线程：执行命令，完成后推入通知队列"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
            )
            output = (result.stdout + result.stderr)[:50_000]
            status = "completed"
        except subprocess.TimeoutExpired:
            output = f"[TIMEOUT] 命令超时（{timeout}秒）"
            status = "timeout"
        except Exception as e:
            output = f"[ERROR] {type(e).__name__}: {e}"
            status = "error"

        self._results[task_id] = {
            "status": status,
            "output": output,
            "finished_at": time.time(),
        }
        # 推入通知队列（摘要限500字符，避免撑大上下文）
        self._notifications.put({
            "task_id": task_id,
            "status": status,
            "result": output[:500],
        })

    def drain_notifications(self) -> list[dict]:
        """取出所有已完成的通知（非阻塞）。

        在 pre_process 节点中调用，将通知注入对话。
        """
        items = []
        while not self._notifications.empty():
            try:
                items.append(self._notifications.get_nowait())
            except queue.Empty:
                break
        return items

    def get_status(self, task_id: str) -> dict:
        """查询指定任务状态"""
        return self._results.get(task_id, {"status": "unknown"})

    def list_tasks(self) -> dict[str, dict]:
        """列出所有任务及其状态"""
        return dict(self._results)


# 全局单例
bg_manager = BackgroundManager()
