"""AgentForge Lite — TaskRepository（任务CRUD + 依赖图自动解锁）

与plan.md逻辑一致，只是驱动从PostgreSQL换成SQLite。
接口签名完全相同，升级PG无需改调用方。
"""

import time
from typing import Optional

from sqlalchemy import select

import src.storage.database as db
from src.storage.models import Task

# 模块级引用，方便测试时 patch
SessionLocal = db.SessionLocal


class TaskRepository:
    """任务仓库 — 增删改查 + 依赖图管理"""

    async def create(self, subject: str, description: str = "",
                     blocked_by: list[int] | None = None) -> dict:
        """创建任务，可选指定前置依赖"""
        async with SessionLocal() as session:
            task = Task(
                subject=subject,
                description=description,
                blocked_by=blocked_by or [],
                created_at=time.time(),
                updated_at=time.time(),
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)

            # commit之后更新上游的blocks（因为task.id现在才有值）
            if blocked_by:
                for dep_id in blocked_by:
                    dep = await session.get(Task, dep_id)
                    if dep:
                        blocks = list(dep.blocks or [])
                        if task.id not in blocks:
                            blocks.append(task.id)
                            dep.blocks = blocks
                            dep.updated_at = time.time()
                await session.commit()

            return task.to_dict()

    async def get(self, task_id: int) -> Optional[dict]:
        """获取单个任务"""
        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return None
            return task.to_dict()

    async def update(self, task_id: int, **kwargs) -> Optional[dict]:
        """更新任务字段。完成时自动清除下游依赖。"""
        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return None

            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time.time()

            # 完成时自动解锁下游任务
            if kwargs.get("status") == "completed":
                await self._clear_dependency(session, task_id)

            await session.commit()
            await session.refresh(task)
            return task.to_dict()

    async def _clear_dependency(self, session, completed_id: int):
        """从所有任务的 blocked_by 中移除已完成任务"""
        result = await session.execute(select(Task))
        all_tasks = result.scalars().all()
        for t in all_tasks:
            blocked = t.blocked_by or []
            if completed_id in blocked:
                t.blocked_by = [x for x in blocked if x != completed_id]
                t.updated_at = time.time()

    async def list_all(self) -> list[dict]:
        """列出所有任务"""
        async with SessionLocal() as session:
            result = await session.execute(
                select(Task).order_by(Task.created_at.desc())
            )
            return [t.to_dict() for t in result.scalars().all()]

    async def list_by_status(self, status: str) -> list[dict]:
        """按状态过滤任务"""
        async with SessionLocal() as session:
            result = await session.execute(
                select(Task).where(Task.status == status)
            )
            return [t.to_dict() for t in result.scalars().all()]

    async def list_claimable(self) -> list[dict]:
        """列出可认领的任务：pending + 无owner + blocked_by为空"""
        async with SessionLocal() as session:
            result = await session.execute(
                select(Task).where(
                    Task.status == "pending",
                    Task.owner == "",
                )
            )
            tasks = result.scalars().all()
            # JSON字段无法在SQL层过滤空列表，在Python层过滤
            return [t.to_dict() for t in tasks if not t.blocked_by]

    async def claim(self, task_id: int, owner: str) -> Optional[dict]:
        """认领任务（单进程无需FOR UPDATE，直接更新）"""
        return await self.update(task_id, status="in_progress", owner=owner)

    async def delete(self, task_id: int) -> bool:
        """删除任务"""
        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            await session.delete(task)
            await session.commit()
            return True


# 全局单例
task_repo = TaskRepository()
