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
    content = state.get("content", "")  # 获取工单原始内容

    logger.info(f"[{task_id}] 开始发送查询结果邮件")

    # 检查收件人是否存在，如果为空则使用配置的默认邮箱
    if not cc_emails or len(cc_emails) == 0:
        # 使用 .env 中配置的开发团队邮箱作为默认收件人
        # settings.email.email_dev_team 已经是列表类型，不需要再 split
        default_emails = settings.email.email_dev_team
        if default_emails:
            cc_emails = default_emails
            logger.warning(
                f"[{task_id}] 未提供收件人，使用默认邮箱: {cc_emails}"
            )
        else:
            error_msg = "收件人列表为空且未配置默认邮箱，无法发送邮件"
            logger.error(f"[{task_id}] {error_msg}")
            return {
                "email_sent": False,
                "error": error_msg,
                "current_node": "send_query_email",
            }

    # 检查查询结果是否存在
    if not query_result:
        error_msg = "查询结果为空，无法发送邮件"
        logger.error(f"[{task_id}] {error_msg}")
        return {
            "email_sent": False,
            "error": error_msg,
            "current_node": "send_query_email",
        }

    try:
        # 获取工单编号
        ticket_id = metadata.get("ticket_id", task_id)

        # 生成 Excel 附件
        columns = query_result.get("columns", [])
        rows = query_result.get("rows", [])
        excel_file = ExcelGenerator.generate_from_query_result(columns, rows)

        logger.info(f"[{task_id}] Excel 已生成: {len(excel_file)} 字节")

        # 发送邮件
        await email_service.send_query_result_email(
            to_emails=cc_emails,
            task_id=task_id,
            ticket_id=ticket_id,
            sql=sql,
            result_data=query_result,
            excel_file=excel_file,
            work_order_content=content,
        )

        logger.info(f"[{task_id}] 查询结果邮件发送成功")

        return {
            "email_sent": True,
            "current_node": "send_query_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] 发送查询结果邮件失败: {e}")
        return {
            "email_sent": False,
            "error": f"邮件发送失败: {str(e)}",
            "current_node": "send_query_email",
        }
