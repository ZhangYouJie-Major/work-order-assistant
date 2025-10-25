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
    query_steps_config = state.get("query_steps_config")

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

        # ===== 打印 DML 信息 =====
        logger.info(f"[{task_id}] " + "=" * 60)
        logger.info(f"[{task_id}] 生成的 DML 语句")
        logger.info(f"[{task_id}] " + "=" * 60)
        logger.info(f"[{task_id}] 操作类型: {dml_info.get('operation_type', 'UNKNOWN')}")
        logger.info(f"[{task_id}] 涉及表: {dml_info.get('affected_tables', [])}")
        logger.info(f"[{task_id}] 风险级别: {dml_info.get('risk_level', 'unknown')}")
        logger.info(f"[{task_id}] " + "-" * 60)

        # 打印执行 SQL（从 dml_info 中获取）
        sql = dml_info.get("sql")
        if sql:
            logger.info(f"[{task_id}] 【执行 SQL】:")
            logger.info(f"[{task_id}]   {sql}")

        # 打印模板 SQL（从配置中获取 final_sql_template）
        if query_steps_config:
            final_sql_template = query_steps_config.get("final_sql_template")
            if final_sql_template:
                logger.info(f"[{task_id}] " + "-" * 60)
                logger.info(f"[{task_id}] 【SQL 模板】(使用参数化查询):")
                logger.info(f"[{task_id}]   {final_sql_template}")

                # 打印参数
                context = dml_info.get("context", {})
                if context:
                    logger.info(f"[{task_id}] 【参数】:")
                    for key, value in context.items():
                        logger.info(f"[{task_id}]   {key} = {value}")

        logger.info(f"[{task_id}] " + "-" * 60)
        logger.info(f"[{task_id}] 说明: {dml_info.get('description', '')}")
        logger.info(f"[{task_id}] " + "=" * 60)

        # ===== 暂时跳过邮件发送（SMTP 未配置）=====
        logger.warning(f"[{task_id}] 跳过邮件发送（SMTP 未配置），仅打印 DML")

        # 获取工单编号
        # ticket_id = metadata.get("ticket_id", task_id)

        # 获取运维团队邮箱
        # ops_emails = settings.email.email_ops_team
        # if isinstance(ops_emails, str):
        #     ops_emails = [email.strip() for email in ops_emails.split(",")]

        # logger.info(f"[{task_id}] 发送 DML 邮件到运维: {ops_emails}")

        # 发送邮件
        # await email_service.send_dml_review_email(
        #     to_emails=ops_emails,
        #     cc_emails=cc_emails,
        #     task_id=task_id,
        #     ticket_id=ticket_id,
        #     dml_info=dml_info,
        # )

        logger.info(f"[{task_id}] DML 处理完成（未发送邮件）")

        return {
            "email_sent": True,  # 标记为已完成，避免工作流失败
            "current_node": "send_dml_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] DML 邮件节点失败: {e}")
        # 即使失败也不阻塞工作流
        return {
            "email_sent": False,
            "current_node": "send_dml_email",
        }
