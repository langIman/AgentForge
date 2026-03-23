"""AgentForge Lite — 持久化任务工具（CRUD + 依赖图）

与P1的TodoManager不同：
- TodoManager：内存中的轻量待办，用于跟踪当前工作步骤
- TaskRepository：SQLite持久化任务，支持依赖图、跨会话存活、多Agent认领
"""

import asyncio
from typing import Optional

from langchain_core.tools import tool

from src.storage.task_repo import task_repo


def _run_async(coro):
    """在同步上下文中运行async函数"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 已经在 async 上下文中，创建 task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


@tool
def task_create(subject: str, description: str = "",
                blocked_by: Optional[list[int]] = None) -> str:
    """创建持久化任务。

    Args:
        subject: 任务标题
        description: 任务详细描述
        blocked_by: 前置依赖的任务ID列表（这些任务完成后本任务才可执行）

    Returns:
        创建的任务信息
    """
    try:
        task = _run_async(task_repo.create(subject, description, blocked_by))
        blocked_info = f"，依赖: {task['blocked_by']}" if task["blocked_by"] else ""
        return f"已创建任务 #{task['id']}: {task['subject']}{blocked_info}"
    except Exception as e:
        return f"[ERROR] 创建任务失败: {type(e).__name__}: {e}"


@tool
def task_update(task_id: int, status: Optional[str] = None,
                description: Optional[str] = None,
                owner: Optional[str] = None) -> str:
    """更新任务状态或信息。

    当任务标记为completed时，会自动解锁依赖它的下游任务。

    Args:
        task_id: 任务ID
        status: 新状态 (pending/in_progress/completed)
        description: 更新描述
        owner: 设置负责人

    Returns:
        更新后的任务信息
    """
    kwargs = {}
    if status is not None:
        kwargs["status"] = status
    if description is not None:
        kwargs["description"] = description
    if owner is not None:
        kwargs["owner"] = owner

    if not kwargs:
        return "[ERROR] 未指定要更新的字段"

    try:
        task = _run_async(task_repo.update(task_id, **kwargs))
        if task is None:
            return f"[ERROR] 任务 #{task_id} 不存在"
        status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(
            task["status"], "❓"
        )
        return f"{status_emoji} 任务 #{task['id']} [{task['status']}]: {task['subject']}"
    except Exception as e:
        return f"[ERROR] 更新任务失败: {type(e).__name__}: {e}"


@tool
def task_list(status: Optional[str] = None) -> str:
    """列出任务。

    Args:
        status: 可选，按状态过滤 (pending/in_progress/completed)。不传则列出全部。

    Returns:
        任务列表
    """
    try:
        if status:
            tasks = _run_async(task_repo.list_by_status(status))
        else:
            tasks = _run_async(task_repo.list_all())

        if not tasks:
            return f"[无任务{f'（状态: {status}）' if status else ''}]"

        lines = []
        for t in tasks:
            status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(
                t["status"], "❓"
            )
            blocked = f" [blocked by: {t['blocked_by']}]" if t["blocked_by"] else ""
            owner = f" @{t['owner']}" if t["owner"] else ""
            lines.append(f"#{t['id']} {status_emoji} {t['subject']}{owner}{blocked}")

        return "\n".join(lines)
    except Exception as e:
        return f"[ERROR] 列出任务失败: {type(e).__name__}: {e}"


@tool
def task_get(task_id: int) -> str:
    """获取任务详情。

    Args:
        task_id: 任务ID

    Returns:
        任务完整信息
    """
    try:
        task = _run_async(task_repo.get(task_id))
        if task is None:
            return f"[ERROR] 任务 #{task_id} 不存在"

        status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(
            task["status"], "❓"
        )
        parts = [
            f"任务 #{task['id']} {status_emoji}",
            f"  标题: {task['subject']}",
            f"  状态: {task['status']}",
        ]
        if task["description"]:
            parts.append(f"  描述: {task['description']}")
        if task["owner"]:
            parts.append(f"  负责人: {task['owner']}")
        if task["blocked_by"]:
            parts.append(f"  依赖: {task['blocked_by']}")
        if task["blocks"]:
            parts.append(f"  阻塞: {task['blocks']}")

        return "\n".join(parts)
    except Exception as e:
        return f"[ERROR] 获取任务失败: {type(e).__name__}: {e}"
