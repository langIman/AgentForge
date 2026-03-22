"""测试协议FSM"""

import pytest

from src.team.protocols import ProtocolTracker


class TestProtocolTracker:
    @pytest.fixture
    def tracker(self):
        return ProtocolTracker()

    def test_create_request(self, tracker):
        """创建请求返回request_id"""
        rid = tracker.create("shutdown", "lead", "worker1")
        assert isinstance(rid, str)
        assert len(rid) == 8

    def test_get_request(self, tracker):
        """查询请求详情"""
        rid = tracker.create("shutdown", "lead", "worker1", {"reason": "done"})
        req = tracker.get(rid)
        assert req is not None
        assert req["protocol"] == "shutdown"
        assert req["initiator"] == "lead"
        assert req["target"] == "worker1"
        assert req["state"] == "pending"
        assert req["payload"]["reason"] == "done"

    def test_respond_approve(self, tracker):
        """批准请求"""
        rid = tracker.create("plan_approval", "lead", "worker1")
        result = tracker.respond(rid, approve=True, feedback="LGTM")
        assert "approved" in result

        req = tracker.get(rid)
        assert req["state"] == "approved"
        assert req["feedback"] == "LGTM"

    def test_respond_reject(self, tracker):
        """拒绝请求"""
        rid = tracker.create("plan_approval", "lead", "worker1")
        result = tracker.respond(rid, approve=False, feedback="需要修改")
        assert "rejected" in result

        req = tracker.get(rid)
        assert req["state"] == "rejected"

    def test_respond_nonexistent(self, tracker):
        """回复不存在的请求"""
        result = tracker.respond("fake_id", approve=True)
        assert "[ERROR]" in result

    def test_respond_already_processed(self, tracker):
        """不能重复处理"""
        rid = tracker.create("shutdown", "lead", "worker1")
        tracker.respond(rid, approve=True)
        result = tracker.respond(rid, approve=False)
        assert "[ERROR]" in result

    def test_get_nonexistent(self, tracker):
        """查询不存在的请求返回None"""
        assert tracker.get("nonexistent") is None

    def test_list_by_target(self, tracker):
        """按目标列出请求"""
        tracker.create("shutdown", "lead", "worker1")
        tracker.create("plan_approval", "lead", "worker2")
        tracker.create("shutdown", "lead", "worker1")

        w1_reqs = tracker.list_by_target("worker1")
        assert len(w1_reqs) == 2
        assert all(r["target"] == "worker1" for r in w1_reqs)

    def test_list_pending(self, tracker):
        """列出待处理请求"""
        rid1 = tracker.create("shutdown", "lead", "worker1")
        rid2 = tracker.create("plan_approval", "lead", "worker1")
        tracker.respond(rid1, approve=True)

        pending = tracker.list_pending()
        assert len(pending) == 1
        assert pending[0]["request_id"] == rid2

    def test_list_pending_filtered(self, tracker):
        """按目标过滤待处理请求"""
        tracker.create("shutdown", "lead", "worker1")
        tracker.create("shutdown", "lead", "worker2")

        pending = tracker.list_pending(target="worker1")
        assert len(pending) == 1
        assert pending[0]["target"] == "worker1"

    def test_fsm_state_transitions(self, tracker):
        """完整的FSM状态流转"""
        # pending → approved
        rid1 = tracker.create("shutdown", "lead", "w1")
        assert tracker.get(rid1)["state"] == "pending"
        tracker.respond(rid1, approve=True)
        assert tracker.get(rid1)["state"] == "approved"

        # pending → rejected
        rid2 = tracker.create("plan_approval", "lead", "w2")
        assert tracker.get(rid2)["state"] == "pending"
        tracker.respond(rid2, approve=False, feedback="no")
        assert tracker.get(rid2)["state"] == "rejected"
        assert tracker.get(rid2)["feedback"] == "no"

    def test_timestamps(self, tracker):
        """请求带有时间戳"""
        rid = tracker.create("shutdown", "lead", "w1")
        req = tracker.get(rid)
        assert "created_at" in req
        assert "updated_at" in req
        assert req["created_at"] > 0
