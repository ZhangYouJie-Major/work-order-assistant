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

    logger.info(f"[{task_id}] 开始发送 DML 审核邮件")

    try:
        # 检查 DML 信息是否存在
        if dml_info is None:
            logger.error(f"[{task_id}] DML 信息为空，无法发送邮件")
            return {
                "email_sent": False,
                "error": "DML 生成失败，无法发送审核邮件",
                "current_node": "send_dml_email",
            }

        # 获取工单编号
        ticket_id = metadata.get("ticket_id", task_id)

        # 获取运维团队邮箱
        ops_emails = settings.email.email_ops_team
        if isinstance(ops_emails, str):
            ops_emails = [email.strip() for email in ops_emails.split(",")]

        logger.info(f"[{task_id}] 发送 DML 邮件到运维: {ops_emails}")

        # 发送邮件
        await email_service.send_dml_review_email(
            to_emails=ops_emails,
            cc_emails=cc_emails,
            task_id=task_id,
            ticket_id=ticket_id,
            dml_info=dml_info,
        )

        logger.info(f"[{task_id}] DML 审核邮件发送成功")

        return {
            "email_sent": True,
            "current_node": "send_dml_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] 发送 DML 审核邮件失败: {e}")
        return {
            "email_sent": False,
            "error": f"邮件发送失败: {str(e)}",
            "current_node": "send_dml_email",
        }
