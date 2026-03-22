"""AgentForge Lite — 对话存档仓库

压缩时将原始消息保存到SQLite，以便回溯。
"""

import time

from langchain_core.messages import messages_to_dict

import src.storage.database as db
from src.storage.models import Transcript

# 模块级引用，方便测试时 patch
SessionLocal = db.SessionLocal


class TranscriptRepository:
    """对话存档CRUD"""

    async def save(self, session_id: str, messages: list, summary: str = "") -> int:
        """保存一次对话存档"""
        async with SessionLocal() as session:
            transcript = Transcript(
                session_id=session_id,
                messages=messages_to_dict(messages),
                summary=summary,
                created_at=time.time(),
            )
            session.add(transcript)
            await session.commit()
            await session.refresh(transcript)
            return transcript.id

    async def get_by_session(self, session_id: str) -> list[dict]:
        """获取某session的所有存档"""
        from sqlalchemy import select

        async with SessionLocal() as session:
            result = await session.execute(
                select(Transcript)
                .where(Transcript.session_id == session_id)
                .order_by(Transcript.created_at.desc())
            )
            return [
                {
                    "id": t.id,
                    "session_id": t.session_id,
                    "summary": t.summary,
                    "message_count": len(t.messages) if t.messages else 0,
                    "created_at": t.created_at,
                }
                for t in result.scalars().all()
            ]


# 全局单例
transcript_repo = TranscriptRepository()
