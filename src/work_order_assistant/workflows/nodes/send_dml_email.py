"""
发送 DML 审核邮件节点
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...services.email_service import EmailService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
email_service = EmailService(settings.email)


async def send_dml_email_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    发送 DML 审核邮件节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 email_sent
    """
    task_id = state.get("task_id")
    cc_emails = state.get("cc_emails", [])
    dml_info = state.get("dml_info")
    metadata = state.get("metadata", {})

    logger.info(f"[{task_id}] Starting to send DML review email")

    try:
        # 获取工单编号
        ticket_id = metadata.get("ticket_id", task_id)

        # 获取运维团队邮箱
        ops_emails = settings.email.email_ops_team
        if isinstance(ops_emails, str):
            ops_emails = [email.strip() for email in ops_emails.split(",")]

        logger.info(f"[{task_id}] Sending DML email to ops: {ops_emails}")

        # 发送邮件
        await email_service.send_dml_review_email(
            to_emails=ops_emails,
            cc_emails=cc_emails,
            task_id=task_id,
            ticket_id=ticket_id,
            dml_info=dml_info,
        )

        logger.info(f"[{task_id}] DML review email sent successfully")

        return {
            "email_sent": True,
            "current_node": "send_dml_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] Failed to send DML review email: {e}")
        return {
            "email_sent": False,
            "error": f"邮件发送失败: {str(e)}",
            "current_node": "send_dml_email",
        }
