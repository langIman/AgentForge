"""测试团队管理：InMemoryMailbox + TeammateManager"""

import time

import pytest

from src.team.mailbox import InMemoryMailbox, make_read_inbox_tool, make_send_tool
from src.team.manager import TeammateManager


# ─── InMemoryMailbox ───


class TestInMemoryMailbox:
    @pytest.fixture
    def mbox(self):
        return InMemoryMailbox()

    def test_send_and_read(self, mbox):
        """发送和读取消息"""
        mbox.send("alice", "bob", "hello")
        messages = mbox.read_inbox("bob")
        assert len(messages) == 1
        assert messages[0]["from"] == "alice"
        assert messages[0]["content"] == "hello"
        assert messages[0]["type"] == "message"

    def test_read_clears_inbox(self, mbox):
        """读取后清空收件箱"""
        mbox.send("alice", "bob", "hello")
        mbox.read_inbox("bob")
        assert mbox.read_inbox("bob") == []

    def test_peek_does_not_clear(self, mbox):
        """peek不清空收件箱"""
        mbox.send("alice", "bob", "hello")
        peeked = mbox.peek_inbox("bob")
        assert len(peeked) == 1
        still_there = mbox.read_inbox("bob")
        assert len(still_there) == 1

    def test_empty_inbox(self, mbox):
        """空收件箱返回空列表"""
        assert mbox.read_inbox("nobody") == []

    def test_broadcast(self, mbox):
        """广播发送给所有人（除了自己）"""
        result = mbox.broadcast("lead", "hello all", ["lead", "w1", "w2"])
        assert "2" in result
        assert len(mbox.read_inbox("w1")) == 1
        assert len(mbox.read_inbox("w2")) == 1
        assert len(mbox.read_inbox("lead")) == 0  # 不发给自己

    def test_has_messages(self, mbox):
        """检查是否有未读消息"""
        assert mbox.has_messages("bob") is False
        mbox.send("alice", "bob", "hi")
        assert mbox.has_messages("bob") is True

    def test_multiple_messages(self, mbox):
        """多条消息按顺序"""
        mbox.send("a", "b", "msg1")
        mbox.send("c", "b", "msg2")
        messages = mbox.read_inbox("b")
        assert len(messages) == 2
        assert messages[0]["content"] == "msg1"
        assert messages[1]["content"] == "msg2"

    def test_extra_fields(self, mbox):
        """支持额外字段"""
        mbox.send("a", "b", "test", msg_type="shutdown", request_id="abc123")
        messages = mbox.read_inbox("b")
        assert messages[0]["type"] == "shutdown"
        assert messages[0]["request_id"] == "abc123"


# ─── 工厂工具 ───


class TestMailboxTools:
    def test_make_send_tool(self):
        """工厂创建的send_message工具能正常工作"""
        mbox = InMemoryMailbox()
        send = make_send_tool("worker1", mbox)
        result = send.invoke({"to": "lead", "content": "done"})
        assert "已发送" in result

        messages = mbox.read_inbox("lead")
        assert len(messages) == 1
        assert messages[0]["from"] == "worker1"

    def test_make_read_inbox_tool(self):
        """工厂创建的read_inbox工具能正常工作"""
        mbox = InMemoryMailbox()
        mbox.send("lead", "worker1", "go do task")
        read = make_read_inbox_tool("worker1", mbox)
        result = read.invoke({})
        assert "go do task" in result

    def test_read_inbox_empty(self):
        """空收件箱"""
        mbox = InMemoryMailbox()
        read = make_read_inbox_tool("worker1", mbox)
        result = read.invoke({})
        assert "为空" in result


# ─── TeammateManager ───


class TestTeammateManager:
    @pytest.fixture
    def mbox(self):
        return InMemoryMailbox()

    @pytest.fixture
    def manager(self, mbox):
        return TeammateManager(mbox)

    def test_initial_state(self, manager):
        """初始状态：无成员"""
        assert manager.list_members() == []
        info = manager.get_team_info()
        assert info["total"] == 0
        assert info["working"] == 0

    def test_list_members_after_config(self, manager):
        """手动添加成员配置"""
        manager.config["members"].append({
            "name": "test",
            "role": "tester",
            "status": "working",
        })
        members = manager.list_members()
        assert len(members) == 1
        assert members[0]["name"] == "test"

    def test_duplicate_spawn_blocked(self, manager, mbox):
        """重复名称的Worker不能同时运行 — 使用mock避免实际启动"""
        # 手动添加一个正在运行的mock线程
        import threading
        fake_thread = threading.Thread(target=lambda: time.sleep(10), daemon=True)
        fake_thread.start()
        manager.workers["dup"] = fake_thread
        manager.config["members"].append({"name": "dup", "role": "test", "status": "working"})

        result = manager.spawn("dup", "role", "task")
        assert "[ERROR]" in result

    def test_is_alive_false_for_unknown(self, manager):
        """不存在的Worker返回False"""
        assert manager.is_alive("ghost") is False
