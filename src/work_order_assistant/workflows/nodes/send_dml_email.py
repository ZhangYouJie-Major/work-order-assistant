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
    content = state.get("content", "")  # 获取工单原始内容

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

        # 检查是否需要人工介入
        if dml_info.get("manual_intervention_required", False):
            logger.warning(f"[{task_id}] 工单需要人工介入，发送通知邮件")

            # 获取工单编号
            ticket_id = metadata.get("ticket_id", task_id)

            # 获取运维团队邮箱
            ops_emails = settings.email.email_ops_team

            logger.info(f"[{task_id}] 发送人工介入邮件到运维: {ops_emails}")

            # 检查抄送邮箱
            if not cc_emails or len(cc_emails) == 0:
                default_cc = settings.email.email_dev_team
                if default_cc:
                    cc_emails = default_cc
                    logger.warning(
                        f"[{task_id}] 未提供抄送邮箱，使用默认: {cc_emails}"
                    )

            # 发送人工介入邮件
            await email_service.send_manual_intervention_email(
                to_emails=ops_emails,
                cc_emails=cc_emails,
                task_id=task_id,
                ticket_id=ticket_id,
                work_order_content=content,
                reason=dml_info.get("reason", "工单内容不清晰或无法匹配到合适的配置"),
            )

            logger.info(f"[{task_id}] 人工介入邮件发送成功")

            return {
                "email_sent": True,
                "manual_intervention": True,
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

        # ===== 发送邮件 =====
        # 获取工单编号
        ticket_id = metadata.get("ticket_id", task_id)

        # 获取运维团队邮箱（已经是列表类型）
        ops_emails = settings.email.email_ops_team

        logger.info(f"[{task_id}] 发送 DML 邮件到运维: {ops_emails}")

        # 检查抄送邮箱，如果为空则使用开发团队邮箱
        if not cc_emails or len(cc_emails) == 0:
            # settings.email.email_dev_team 已经是列表类型，不需要再 split
            default_cc = settings.email.email_dev_team
            if default_cc:
                cc_emails = default_cc
                logger.warning(
                    f"[{task_id}] 未提供抄送邮箱，使用默认: {cc_emails}"
                )

        # 发送邮件
        await email_service.send_dml_review_email(
            to_emails=ops_emails,
            cc_emails=cc_emails,
            task_id=task_id,
            ticket_id=ticket_id,
            dml_info=dml_info,
            work_order_content=content,
        )

        logger.info(f"[{task_id}] DML 邮件发送成功")

        return {
            "email_sent": True,
            "current_node": "send_dml_email",
        }

    except Exception as e:
        logger.error(f"[{task_id}] DML 邮件节点失败: {e}")
        # 即使失败也不阻塞工作流
        return {
            "email_sent": False,
            "current_node": "send_dml_email",
        }
