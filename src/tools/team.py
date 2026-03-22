"""AgentForge Lite — 团队管理工具

Lead角色工具：spawn_teammate, list_teammates, broadcast
Lead+Worker共用：send_message, read_inbox

这些工具用于Lead Agent管理Worker团队。
"""

from langchain_core.tools import tool

from src.team.mailbox import mailbox
from src.team.manager import TeammateManager

# TeammateManager需要mailbox，在此初始化
teammate_manager = TeammateManager(mailbox)


@tool
def spawn_teammate(name: str, role: str, prompt: str) -> str:
    """生成一个新的Worker队友。

    Worker会在独立线程中执行任务，拥有受限的工具集
    （bash, read_file, write_file, edit_file, send_message, read_inbox）。

    Args:
        name: Worker名称（唯一标识，如 "coder", "reviewer"）
        role: 角色描述（如 "Python开发者", "代码审查员"）
        prompt: 初始任务指令

    Returns:
        启动结果
    """
    return teammate_manager.spawn(name, role, prompt)


@tool
def list_teammates() -> str:
    """列出当前团队的所有成员及其状态。

    Returns:
        团队成员列表
    """
    info = teammate_manager.get_team_info()
    if not info["members"]:
        return "[无团队成员]"

    lines = [f"团队: {info['team_name']} ({info['working']}/{info['total']} 工作中)"]
    for m in info["members"]:
        status_emoji = {"working": "🔄", "idle": "💤", "shutdown": "⏹️"}.get(
            m["status"], "❓"
        )
        lines.append(f"  {status_emoji} {m['name']} ({m['role']}) - {m['status']}")
    return "\n".join(lines)


@tool
def send_message(to: str, content: str) -> str:
    """发送消息给指定的队友。

    Lead使用此工具向Worker发送指令或回复。

    Args:
        to: 接收者名称
        content: 消息内容

    Returns:
        发送结果
    """
    return mailbox.send("lead", to, content)


@tool
def read_inbox() -> str:
    """读取Lead的收件箱中所有消息。

    Returns:
        收件箱中的消息列表
    """
    messages = mailbox.read_inbox("lead")
    if not messages:
        return "[收件箱为空]"
    lines = []
    for m in messages:
        lines.append(f"[{m['type']}] {m['from']}: {m['content']}")
    return "\n".join(lines)


@tool
def broadcast(content: str) -> str:
    """向所有团队成员广播消息。

    Args:
        content: 广播内容

    Returns:
        广播结果
    """
    members = teammate_manager.list_members()
    names = [m["name"] for m in members]
    if not names:
        return "[ERROR] 没有团队成员可广播"
    return mailbox.broadcast("lead", content, names + ["lead"])
