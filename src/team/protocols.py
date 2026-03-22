"""AgentForge Lite — 协议FSM（有限状态机）

与 plan.md 的 Redis 版接口一致，用内存 dict 实现。

支持的协议类型：
- shutdown: Lead请求Worker优雅退出
- plan_approval: Lead向Worker发送计划，等待批准/拒绝

状态流转：
  pending → approved / rejected

设计：
- 每个请求有唯一 request_id
- create() 创建请求，发送消息给 target
- respond() 目标回复，更新状态
- get() 查询请求状态
"""

import threading
import time
from uuid import uuid4


class ProtocolTracker:
    """协议追踪器 — 内存dict实现，线程安全"""

    def __init__(self):
        self._requests: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, protocol: str, initiator: str, target: str,
               payload: dict = None) -> str:
        """创建协议请求。

        Args:
            protocol: 协议类型 (shutdown / plan_approval)
            initiator: 发起者名称
            target: 目标名称
            payload: 附加数据

        Returns:
            request_id
        """
        request_id = uuid4().hex[:8]
        with self._lock:
            self._requests[request_id] = {
                "protocol": protocol,
                "initiator": initiator,
                "target": target,
                "state": "pending",
                "payload": payload or {},
                "feedback": "",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        return request_id

    def respond(self, request_id: str, approve: bool,
                feedback: str = "") -> str:
        """回复协议请求。

        Args:
            request_id: 请求ID
            approve: 是否批准
            feedback: 回复内容

        Returns:
            状态描述
        """
        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return f"[ERROR] 请求 {request_id} 不存在"
            if req["state"] != "pending":
                return f"[ERROR] 请求 {request_id} 已处理: {req['state']}"
            req["state"] = "approved" if approve else "rejected"
            req["feedback"] = feedback
            req["updated_at"] = time.time()
        return f"请求 {request_id}: {req['state']}"

    def get(self, request_id: str) -> dict | None:
        """查询请求详情"""
        with self._lock:
            return self._requests.get(request_id)

    def list_by_target(self, target: str) -> list[dict]:
        """列出发给指定目标的所有请求"""
        with self._lock:
            return [
                {"request_id": rid, **req}
                for rid, req in self._requests.items()
                if req["target"] == target
            ]

    def list_pending(self, target: str = None) -> list[dict]:
        """列出待处理请求，可选过滤目标"""
        with self._lock:
            results = []
            for rid, req in self._requests.items():
                if req["state"] != "pending":
                    continue
                if target and req["target"] != target:
                    continue
                results.append({"request_id": rid, **req})
            return results


# 全局单例
protocol_tracker = ProtocolTracker()
