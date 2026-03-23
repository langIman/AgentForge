"""AgentForge Lite — 后台命令工具

用 threading + subprocess 实现非阻塞后台命令执行。

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

from langchain_core.tools import tool

from src.core.config import WORKSPACE_ROOT


class BackgroundCommandRunner:
    """后台bash命令异步运行 — 线程实现"""

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
bg_cmd_runner = BackgroundCommandRunner()


@tool
def background_run(command: str, timeout: int = 300) -> str:
    """在后台执行Shell命令，立即返回不阻塞。

    适用于耗时命令（测试、构建、部署等），命令完成后
    结果会自动注入下一轮对话。

    Args:
        command: 要执行的Shell命令
        timeout: 超时秒数（默认300）

    Returns:
        task_id，可用于查询状态
    """
    task_id = bg_cmd_runner.run(command, timeout)
    return f"后台任务已启动 [task_id: {task_id}]，完成后会自动通知。"


@tool
def check_background(task_id: str = "") -> str:
    """查询后台任务状态。

    不提供task_id时列出所有任务。

    Args:
        task_id: 要查询的任务ID（可选）

    Returns:
        任务状态信息
    """
    if task_id:
        status = bg_cmd_runner.get_status(task_id)
        if status["status"] == "unknown":
            return f"[ERROR] 未知任务: {task_id}"
        result = f"任务 {task_id}: {status['status']}"
        if "output" in status:
            result += f"\n输出: {status['output'][:2000]}"
        return result

    # 列出所有任务
    all_tasks = bg_cmd_runner.list_tasks()
    if not all_tasks:
        return "[无后台任务]"
    lines = []
    for tid, info in all_tasks.items():
        lines.append(f"  {tid}: {info['status']}")
    return "后台任务列表:\n" + "\n".join(lines)
