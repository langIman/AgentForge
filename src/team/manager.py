"""AgentForge Lite — 多Agent团队管理器

管理Worker的生命周期：spawn → 执行 → idle → shutdown。

设计：
- 每个Worker在独立线程中运行自己的图
- Lead通过工具spawn/list/shutdown管理Worker
- Worker通过mailbox与Lead和其他Worker通信
- 线程实现，与plan.md的asyncio版接口一致
"""

import threading
import time
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.config import MODEL_NAME, OPENAI_API_BASE, OPENAI_API_KEY
from src.core.state import AgentState
from src.team.mailbox import InMemoryMailbox, make_read_inbox_tool, make_send_tool
from src.team.worker_graph import build_worker_graph
from src.tools.bash import bash
from src.tools.file_ops import edit_file, read_file, write_file


class TeammateManager:
    """多Agent团队管理器"""

    def __init__(self, mailbox: InMemoryMailbox):
        self.mailbox = mailbox
        self.workers: dict[str, threading.Thread] = {}
        self.config: dict = {
            "team_name": "default",
            "members": [],
        }
        self._lock = threading.Lock()

    def spawn(self, name: str, role: str, prompt: str) -> str:
        """启动一个新的Worker。

        Args:
            name: Worker名称（唯一标识）
            role: 角色描述
            prompt: 初始任务指令

        Returns:
            启动结果描述
        """
        with self._lock:
            if name in self.workers and self.workers[name].is_alive():
                return f"[ERROR] Worker {name} 已在运行"

        # 构建Worker专用工具集
        worker_send = make_send_tool(name, self.mailbox)
        worker_read = make_read_inbox_tool(name, self.mailbox)
        worker_tools = [bash, read_file, write_file, edit_file,
                        worker_send, worker_read]

        # 创建Worker专用model
        worker_model = ChatOpenAI(
            model=MODEL_NAME,
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
        ).bind_tools(worker_tools)

        # 构建Worker专用图
        worker_graph = build_worker_graph(
            name, role, worker_model, self.mailbox, worker_tools
        )

        # 在独立线程中启动Worker
        thread = threading.Thread(
            target=self._worker_loop,
            args=(name, role, prompt, worker_graph),
            daemon=True,
            name=f"worker-{name}",
        )

        with self._lock:
            self.workers[name] = thread
            self.config["members"].append({
                "name": name,
                "role": role,
                "status": "working",
                "started_at": time.time(),
            })

        thread.start()
        return f"Worker {name} ({role}) 已启动"

    def _worker_loop(self, name: str, role: str, prompt: str, graph):
        """Worker主循环 — 在独立线程中运行。

        对应 plan.md s09 的 _teammate_loop。
        """
        try:
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content=prompt)],
                    "session_id": f"worker-{name}",
                    "todos": [],
                    "rounds_since_todo": 0,
                    "token_count": 0,
                    "compressed": False,
                    "tasks_snapshot": "",
                    "bg_notifications": [],
                    "inbox_messages": [],
                    "agent_name": name,
                    "agent_role": role,
                    "team_name": self.config["team_name"],
                },
                {"configurable": {"thread_id": f"worker-{name}"}},
            )
            # Worker完成后向Lead发送完成通知
            last_content = ""
            for msg in reversed(result.get("messages", [])):
                if hasattr(msg, "content") and msg.content:
                    last_content = msg.content[:500]
                    break
            self.mailbox.send(
                name, "lead",
                f"[任务完成] {last_content}",
                msg_type="worker_done",
            )
        except Exception as e:
            self.mailbox.send(
                name, "lead",
                f"[Worker异常] {type(e).__name__}: {e}",
                msg_type="worker_error",
            )
        finally:
            self._set_status(name, "idle")

    def _set_status(self, name: str, status: str):
        """更新Worker状态"""
        with self._lock:
            for member in self.config["members"]:
                if member["name"] == name:
                    member["status"] = status
                    member["updated_at"] = time.time()
                    break

    def list_members(self) -> list[dict]:
        """列出所有团队成员及其状态"""
        with self._lock:
            # 更新线程存活状态
            for member in self.config["members"]:
                name = member["name"]
                if name in self.workers:
                    if not self.workers[name].is_alive():
                        member["status"] = "idle"
            return list(self.config["members"])

    def get_team_info(self) -> dict:
        """获取团队完整信息"""
        return {
            "team_name": self.config["team_name"],
            "members": self.list_members(),
            "total": len(self.config["members"]),
            "working": sum(1 for m in self.config["members"] if m["status"] == "working"),
        }

    def is_alive(self, name: str) -> bool:
        """检查Worker是否仍在运行"""
        with self._lock:
            return name in self.workers and self.workers[name].is_alive()
