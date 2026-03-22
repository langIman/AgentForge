"""AgentForge Lite — 后台任务工具

background_run: 启动后台命令，立即返回不阻塞
check_background: 查询后台任务状态
"""

from langchain_core.tools import tool

from src.background.manager import bg_manager


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
    task_id = bg_manager.run(command, timeout)
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
        status = bg_manager.get_status(task_id)
        if status["status"] == "unknown":
            return f"[ERROR] 未知任务: {task_id}"
        result = f"任务 {task_id}: {status['status']}"
        if "output" in status:
            result += f"\n输出: {status['output'][:2000]}"
        return result

    # 列出所有任务
    all_tasks = bg_manager.list_tasks()
    if not all_tasks:
        return "[无后台任务]"
    lines = []
    for tid, info in all_tasks.items():
        lines.append(f"  {tid}: {info['status']}")
    return "后台任务列表:\n" + "\n".join(lines)
