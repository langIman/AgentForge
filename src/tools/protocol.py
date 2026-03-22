"""AgentForge Lite — 协议工具

shutdown_request: Lead请求Worker优雅退出
plan_approval: Lead向Worker发送计划，请求批准

这些工具结合ProtocolTracker（FSM）和InMemoryMailbox实现
结构化的Agent间交互协议。
"""

from langchain_core.tools import tool

from src.team.mailbox import mailbox
from src.team.protocols import protocol_tracker


@tool
def shutdown_request(target: str, reason: str = "任务完成") -> str:
    """向Worker发送优雅关闭请求。

    Worker收到后应完成当前工作、汇报结果，然后退出。

    Args:
        target: 目标Worker名称
        reason: 关闭原因

    Returns:
        请求ID和状态
    """
    request_id = protocol_tracker.create(
        protocol="shutdown",
        initiator="lead",
        target=target,
        payload={"reason": reason},
    )

    # 通过mailbox发送shutdown通知
    mailbox.send(
        "lead", target,
        f"[SHUTDOWN REQUEST] request_id={request_id}, reason={reason}",
        msg_type="shutdown",
        request_id=request_id,
    )

    return f"已发送关闭请求给 {target} [request_id: {request_id}]"


@tool
def plan_approval(target: str, plan: str) -> str:
    """向Worker发送计划，请求审批。

    Worker收到后可以批准（approve）或拒绝（reject）并附带反馈。

    Args:
        target: 目标Worker名称
        plan: 计划内容

    Returns:
        请求ID和状态
    """
    request_id = protocol_tracker.create(
        protocol="plan_approval",
        initiator="lead",
        target=target,
        payload={"plan": plan},
    )

    # 通过mailbox发送计划审批请求
    mailbox.send(
        "lead", target,
        f"[PLAN APPROVAL] request_id={request_id}\n计划内容:\n{plan}",
        msg_type="plan_approval",
        request_id=request_id,
    )

    return (
        f"已发送计划审批请求给 {target} [request_id: {request_id}]\n"
        f"等待 {target} 批准或拒绝。"
    )
