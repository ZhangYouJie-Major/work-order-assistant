"""
发送查询结果邮件节点
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...services.email_service import EmailService
from ...utils.excel_generator import ExcelGenerator
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
email_service = EmailService(settings.email)


async def send_query_email_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    发送查询结果邮件节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 email_sent
    """
    task_id = state.get("task_id")
    cc_emails = state.get("cc_emails", [])
    query_result = state.get("query_result")
    sql = state.get("sql")
    metadata = state.get("metadata", {})

    logger.info(f"[{task_id}] Starting to send query result email")

    try:
        # 获取工单编号
        ticket_id = metadata.get("ticket_id", task_id)

        # 生成 Excel 附件
        columns = query_result.get("columns", [])
        rows = query_result.get("rows", [])
        excel_file = ExcelGenerator.generate_from_query_result(columns, rows)

        logger.info(f"[{task_id}] Excel generated: {len(excel_file)} bytes")

        # 发送邮件
        await email_service.send_query_result_email(
            to_emails=cc_emails,
            task_id=task_id,
            ticket_id=ticket_id,
            sql=sql,
            result_data=query_result,
            excel_file=excel_file,
        )

        logger.info(f"[{task_id}] Query result email sent successfully")

        return {
            "email_sent": True,
            "current_node": "send_query_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] Failed to send query result email: {e}")
        return {
            "email_sent": False,
            "error": f"邮件发送失败: {str(e)}",
            "current_node": "send_query_email",
        }
