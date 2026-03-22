"""AgentForge Lite — 内存消息总线

与 plan.md 的 RedisMailbox 接口完全一致。
要升级 Redis，只需替换此类，调用方无需改动。

设计：
- 每个 agent 有一个收件箱（list）
- send() 投递到目标收件箱
- read_inbox() 取走并清空（消费语义）
- broadcast() 群发给所有队友（排除自己）
"""

import threading
import time
from collections import defaultdict

from langchain_core.tools import tool


class InMemoryMailbox:
    """内存消息总线 — 线程安全实现"""

    def __init__(self):
        self._inboxes: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", **extra) -> str:
        """发送消息到目标收件箱"""
        msg = {
            "type": msg_type,
            "from": sender,
            "to": to,
            "content": content,
            "timestamp": time.time(),
            **extra,
        }
        with self._lock:
            self._inboxes[to].append(msg)
        return f"已发送给 {to}"

    def read_inbox(self, name: str) -> list[dict]:
        """读取并清空收件箱（消费语义）"""
        with self._lock:
            messages = self._inboxes.pop(name, [])
        return messages

    def peek_inbox(self, name: str) -> list[dict]:
        """查看收件箱但不消费"""
        with self._lock:
            return list(self._inboxes.get(name, []))

    def broadcast(self, sender: str, content: str,
                  teammates: list[str]) -> str:
        """群发消息给所有队友（排除发送者自己）"""
        count = 0
        for name in teammates:
            if name != sender:
                self.send(sender, name, content, msg_type="broadcast")
                count += 1
        return f"已广播给 {count} 个队友"

    def has_messages(self, name: str) -> bool:
        """是否有未读消息"""
        with self._lock:
            return bool(self._inboxes.get(name))


def make_send_tool(agent_name: str, mailbox: "InMemoryMailbox"):
    """工厂函数：为指定agent创建绑定的send_message工具。

    Worker使用此工具发送消息，sender自动绑定为自己的名字。
    """
    @tool
    def send_message(to: str, content: str) -> str:
        """发送消息给指定的队友。

        Args:
            to: 接收者名称
            content: 消息内容

        Returns:
            发送结果
        """
        return mailbox.send(agent_name, to, content)

    send_message.name = f"send_message"
    return send_message


def make_read_inbox_tool(agent_name: str, mailbox: "InMemoryMailbox"):
    """工厂函数：为指定agent创建绑定的read_inbox工具。

    Worker使用此工具读取收件箱，自动读取自己的邮箱。
    """
    @tool
    def read_inbox() -> str:
        """读取收件箱中的所有消息。

        Returns:
            收件箱中的消息列表
        """
        messages = mailbox.read_inbox(agent_name)
        if not messages:
            return "[收件箱为空]"
        lines = []
        for m in messages:
            lines.append(f"[{m['type']}] {m['from']} → {agent_name}: {m['content']}")
        return "\n".join(lines)

    read_inbox.name = f"read_inbox"
    return read_inbox


# 全局单例
mailbox = InMemoryMailbox()
