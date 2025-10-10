"""
邮件发送服务
"""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional
from ..config import EmailSettings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class EmailService:
    """邮件发送服务"""

    def __init__(self, settings: EmailSettings):
        """
        初始化邮件服务

        Args:
            settings: 邮件配置
        """
        self.settings = settings
        logger.info(
            f"Email Service initialized: SMTP={settings.smtp_host}:{settings.smtp_port}"
        )

    async def send_query_result_email(
        self,
        to_emails: List[str],
        task_id: str,
        ticket_id: str,
        sql: str,
        result_data: Dict[str, Any],
        excel_file: bytes,
    ) -> None:
        """
        发送查询结果邮件

        Args:
            to_emails: 收件人列表
            task_id: 任务 ID
            ticket_id: 工单编号
            sql: 执行的 SQL 语句
            result_data: 查询结果数据
            excel_file: Excel 附件内容
        """
        logger.info(f"Sending query result email for task {task_id}")

        subject = f"【工单查询结果】{ticket_id}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .container {{ padding: 20px; }}
        h3 {{ color: #333; }}
        .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .sql-block {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; border-radius: 3px; font-family: monospace; white-space: pre-wrap; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #888; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h3>工单查询结果</h3>

        <div class="info">
            <p><strong>任务 ID:</strong> {task_id}</p>
            <p><strong>工单编号:</strong> {ticket_id}</p>
        </div>

        <h4>执行的 SQL:</h4>
        <div class="sql-block">{sql}</div>

        <h4>结果摘要:</h4>
        <p>查询返回 <strong>{result_data.get('row_count', 0)}</strong> 行数据，详情见附件 Excel。</p>

        <div class="footer">
            <p>本邮件由工单智能处理助手自动生成</p>
        </div>
    </div>
</body>
</html>
"""

        await self._send_email_with_attachment(
            to_emails, subject, html_body, "查询结果.xlsx", excel_file
        )

        logger.info(f"Query result email sent successfully to {len(to_emails)} recipients")

    async def send_dml_review_email(
        self,
        to_emails: List[str],
        cc_emails: List[str],
        task_id: str,
        ticket_id: str,
        dml_info: Dict[str, Any],
    ) -> None:
        """
        发送 DML 审核邮件

        Args:
            to_emails: 收件人列表（运维/DBA）
            cc_emails: 抄送列表
            task_id: 任务 ID
            ticket_id: 工单编号
            dml_info: DML 信息
        """
        logger.info(f"Sending DML review email for task {task_id}")

        subject = f"【工单 DML 待执行】{ticket_id}"

        risk_color = self._get_risk_color(dml_info.get("risk_level", "medium"))
        highlighted_sql = self._highlight_sql(dml_info.get("sql", ""))

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .container {{ padding: 20px; }}
        h3 {{ color: #333; }}
        .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .sql-block {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #dc3545; border-radius: 3px; font-family: monospace; white-space: pre-wrap; }}
        .risk-badge {{ padding: 5px 10px; border-radius: 3px; color: white; font-weight: bold; }}
        ul {{ padding-left: 20px; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #888; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h3>工单 DML 待执行</h3>

        <div class="info">
            <p><strong>任务 ID:</strong> {task_id}</p>
            <p><strong>工单编号:</strong> {ticket_id}</p>
        </div>

        <h4>待执行的 SQL:</h4>
        <div class="sql-block">{highlighted_sql}</div>

        <h4>影响范围:</h4>
        <ul>
            <li>影响表: {', '.join(dml_info.get('affected_tables', []))}</li>
            <li>预计影响行数: {dml_info.get('estimated_rows', '未知')}</li>
            <li>风险等级: <span class="risk-badge" style="background-color: {risk_color};">{dml_info.get('risk_level', 'unknown')}</span></li>
        </ul>

        <h4>操作说明:</h4>
        <p>{dml_info.get('description', '')}</p>

        <div class="footer">
            <p>本邮件由工单智能处理助手自动生成，请运维人员审核后执行</p>
        </div>
    </div>
</body>
</html>
"""

        await self._send_email(to_emails, subject, html_body, cc_emails)

        logger.info(
            f"DML review email sent successfully to {len(to_emails)} recipients, "
            f"CC: {len(cc_emails)}"
        )

    def _highlight_sql(self, sql: str) -> str:
        """
        SQL 语法高亮（简单实现）

        Args:
            sql: SQL 语句

        Returns:
            带高亮的 HTML
        """
        keywords = [
            "SELECT",
            "FROM",
            "WHERE",
            "UPDATE",
            "SET",
            "INSERT",
            "INTO",
            "DELETE",
            "VALUES",
            "AND",
            "OR",
            "JOIN",
            "LEFT",
            "RIGHT",
            "INNER",
            "OUTER",
            "ON",
            "GROUP BY",
            "ORDER BY",
            "LIMIT",
        ]

        highlighted = sql
        for kw in keywords:
            highlighted = highlighted.replace(
                kw,
                f'<span style="color: #0066cc; font-weight: bold;">{kw}</span>',
            )
            # 也处理小写
            highlighted = highlighted.replace(
                kw.lower(),
                f'<span style="color: #0066cc; font-weight: bold;">{kw.lower()}</span>',
            )

        return highlighted

    def _get_risk_color(self, risk_level: str) -> str:
        """
        获取风险等级颜色

        Args:
            risk_level: 风险等级

        Returns:
            颜色代码
        """
        colors = {"low": "#28a745", "medium": "#ffc107", "high": "#dc3545"}
        return colors.get(risk_level, "#6c757d")

    async def _send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_body: str,
        cc_emails: Optional[List[str]] = None,
    ) -> None:
        """
        发送基本邮件

        Args:
            to_emails: 收件人列表
            subject: 邮件主题
            html_body: HTML 正文
            cc_emails: 抄送列表
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = self.settings.smtp_from
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        # 添加 HTML 正文
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # 发送邮件
        await self._send_smtp(msg, to_emails + (cc_emails or []))

    async def _send_email_with_attachment(
        self,
        to_emails: List[str],
        subject: str,
        html_body: str,
        attachment_filename: str,
        attachment_content: bytes,
    ) -> None:
        """
        发送带附件的邮件

        Args:
            to_emails: 收件人列表
            subject: 邮件主题
            html_body: HTML 正文
            attachment_filename: 附件文件名
            attachment_content: 附件内容
        """
        msg = MIMEMultipart()
        msg["From"] = self.settings.smtp_from
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        # 添加 HTML 正文
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # 添加附件
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(attachment_content)
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            f"attachment; filename={attachment_filename}",
        )
        msg.attach(attachment)

        # 发送邮件
        await self._send_smtp(msg, to_emails)

    async def _send_smtp(self, msg: MIMEMultipart, recipients: List[str]) -> None:
        """
        通过 SMTP 发送邮件

        Args:
            msg: 邮件消息对象
            recipients: 收件人列表
        """
        try:
            smtp = aiosmtplib.SMTP(
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                use_tls=self.settings.smtp_use_tls,
            )

            await smtp.connect()
            await smtp.login(self.settings.smtp_user, self.settings.smtp_password)
            await smtp.send_message(msg)
            await smtp.quit()

            logger.debug(f"SMTP send successful to {len(recipients)} recipients")

        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            raise
