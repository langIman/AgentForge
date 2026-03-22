"""测试持久化任务系统（SQLite + SQLAlchemy + 依赖图）"""

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.storage.database import Base
from src.storage.models import Task, Transcript
from src.storage.repository import TaskRepository


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试使用独立的内存数据库"""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Patch SessionLocal in both modules
    import src.storage.database as db_module
    import src.storage.repository as repo_module
    import src.memory.transcript as transcript_module

    original_session = db_module.SessionLocal

    db_module.SessionLocal = test_session_factory
    repo_module.SessionLocal = test_session_factory
    transcript_module.SessionLocal = test_session_factory

    # 建表
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # 还原
    db_module.SessionLocal = original_session
    repo_module.SessionLocal = original_session
    transcript_module.SessionLocal = original_session

    await test_engine.dispose()


@pytest.fixture
def repo():
    return TaskRepository()


# ─── 基本CRUD ───


class TestTaskCRUD:
    @pytest.mark.asyncio
    async def test_create_task(self, repo):
        task = await repo.create("实现登录功能", "使用JWT认证")
        assert task["id"] is not None
        assert task["subject"] == "实现登录功能"
        assert task["description"] == "使用JWT认证"
        assert task["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_task(self, repo):
        created = await repo.create("测试任务")
        fetched = await repo.get(created["id"])
        assert fetched is not None
        assert fetched["subject"] == "测试任务"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        result = await repo.get(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task(self, repo):
        created = await repo.create("待更新任务")
        updated = await repo.update(created["id"], status="in_progress", owner="agent-1")
        assert updated["status"] == "in_progress"
        assert updated["owner"] == "agent-1"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, repo):
        result = await repo.update(999, status="completed")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_task(self, repo):
        created = await repo.create("待删除")
        assert await repo.delete(created["id"]) is True
        assert await repo.get(created["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repo):
        assert await repo.delete(999) is False

    @pytest.mark.asyncio
    async def test_list_all(self, repo):
        await repo.create("任务A")
        await repo.create("任务B")
        await repo.create("任务C")
        all_tasks = await repo.list_all()
        assert len(all_tasks) == 3

    @pytest.mark.asyncio
    async def test_list_by_status(self, repo):
        t1 = await repo.create("任务1")
        await repo.create("任务2")
        await repo.update(t1["id"], status="completed")

        pending = await repo.list_by_status("pending")
        completed = await repo.list_by_status("completed")

        assert len(pending) == 1
        assert len(completed) == 1
        assert pending[0]["subject"] == "任务2"


# ─── 依赖图 ───


class TestTaskDependency:
    @pytest.mark.asyncio
    async def test_create_with_dependency(self, repo):
        """创建带依赖的任务"""
        t1 = await repo.create("基础任务")
        t2 = await repo.create("依赖任务", blocked_by=[t1["id"]])

        fetched = await repo.get(t2["id"])
        assert t1["id"] in fetched["blocked_by"]

    @pytest.mark.asyncio
    async def test_complete_clears_dependency(self, repo):
        """完成任务后，自动解锁下游依赖"""
        t1 = await repo.create("前置任务")
        t2 = await repo.create("下游任务", blocked_by=[t1["id"]])

        # 确认t2被阻塞
        fetched_t2 = await repo.get(t2["id"])
        assert t1["id"] in fetched_t2["blocked_by"]

        # 完成t1
        await repo.update(t1["id"], status="completed")

        # t2的依赖应被清除
        fetched_t2 = await repo.get(t2["id"])
        assert t1["id"] not in fetched_t2["blocked_by"]

    @pytest.mark.asyncio
    async def test_multiple_dependencies(self, repo):
        """多重依赖：只有所有前置完成后才解锁"""
        t1 = await repo.create("前置1")
        t2 = await repo.create("前置2")
        t3 = await repo.create("最终任务", blocked_by=[t1["id"], t2["id"]])

        # 完成t1，t3仍被t2阻塞
        await repo.update(t1["id"], status="completed")
        fetched = await repo.get(t3["id"])
        assert t2["id"] in fetched["blocked_by"]
        assert t1["id"] not in fetched["blocked_by"]

        # 完成t2，t3完全解锁
        await repo.update(t2["id"], status="completed")
        fetched = await repo.get(t3["id"])
        assert len(fetched["blocked_by"]) == 0


# ─── 认领机制 ───


class TestTaskClaim:
    @pytest.mark.asyncio
    async def test_list_claimable(self, repo):
        """可认领：pending + 无owner + 无阻塞"""
        t1 = await repo.create("可认领任务")
        t2 = await repo.create("被阻塞任务", blocked_by=[t1["id"]])
        t3 = await repo.create("另一个可认领")

        claimable = await repo.list_claimable()
        ids = [t["id"] for t in claimable]
        assert t1["id"] in ids
        assert t3["id"] in ids
        assert t2["id"] not in ids  # 被阻塞的不可认领

    @pytest.mark.asyncio
    async def test_claim_task(self, repo):
        """认领任务"""
        t = await repo.create("待认领")
        claimed = await repo.claim(t["id"], "worker-1")

        assert claimed["status"] == "in_progress"
        assert claimed["owner"] == "worker-1"

        # 认领后不再出现在可认领列表
        claimable = await repo.list_claimable()
        assert all(c["id"] != t["id"] for c in claimable)


# ─── Transcript ───


class TestTranscriptModel:
    @pytest.mark.asyncio
    async def test_transcript_save(self):
        """对话存档保存"""
        from src.memory.transcript import TranscriptRepository

        repo = TranscriptRepository()
        tid = await repo.save(
            "test-session",
            [],  # 空消息列表（不使用真实LangChain消息避免序列化问题）
            "test summary",
        )
        assert tid is not None

        # 查询
        transcripts = await repo.get_by_session("test-session")
        assert len(transcripts) == 1
        assert transcripts[0]["summary"] == "test summary"
