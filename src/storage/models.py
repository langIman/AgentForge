"""AgentForge Lite — ORM模型（与plan.md完全兼容，换连接串即升级PG）"""

import time

from sqlalchemy import Column, Float, Integer, JSON, String, Text

from src.storage.database import Base


class Task(Base):
    """持久化任务 — 支持依赖图（blocked_by / blocks）"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(500), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="pending")  # pending | in_progress | completed
    owner = Column(String(100), default="")
    worktree = Column(String(100), default="")
    blocked_by = Column(JSON, default=list)  # list[int] — 依赖的任务ID
    blocks = Column(JSON, default=list)      # list[int] — 阻塞的下游任务ID
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "owner": self.owner,
            "worktree": self.worktree,
            "blocked_by": self.blocked_by or [],
            "blocks": self.blocks or [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return f"<Task #{self.id} [{self.status}] {self.subject[:40]}>"


class Transcript(Base):
    """对话存档 — 自动压缩时保存原始消息"""

    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), index=True)
    messages = Column(JSON)
    summary = Column(Text, default="")
    created_at = Column(Float, default=time.time)

    def __repr__(self):
        return f"<Transcript #{self.id} session={self.session_id}>"
