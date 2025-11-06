"""
SQL 查询工具

使用 LangChain @tool 装饰器封装 MySQL 查询功能
"""

from typing import Dict, Any, List, Optional
import mysql.connector
from mysql.connector import Error
from langchain_core.tools import tool
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


@tool
async def query_mysql(sql: str) -> Dict[str, Any]:
    """
    执行 MySQL 只读查询（仅支持 SELECT 语句）

    Args:
        sql: SQL 查询语句（必须是 SELECT 语句）

    Returns:
        查询结果，格式:
        {
            "columns": ["col1", "col2", ...],
            "rows": [[val1, val2], ...],
            "row_count": 10,
            "success": True
        }

    Raises:
        ValueError: 如果 SQL 不是只读查询
        Exception: 查询执行失败
    """
    logger.info(f"执行 SQL 查询: {sql[:100]}...")

    # 验证只读查询
    if not _is_readonly_query(sql):
        error_msg = "只允许执行 SELECT 查询语句"
        logger.error(error_msg)
        raise ValueError(error_msg)

    conn = None
    cursor = None
    retry_count = 0
    max_retries = settings.mysql.mysql_max_retries

    while retry_count < max_retries:
        try:
            # 创建数据库连接
            # 使用 use_pure=True 避免 C 扩展的 "Failed raising error" 问题
            conn = mysql.connector.connect(
                host=settings.mysql.mysql_host,
                port=settings.mysql.mysql_port,
                user=settings.mysql.mysql_user,
                password=settings.mysql.mysql_password,
                database=settings.mysql.mysql_database,
                charset=settings.mysql.mysql_charset,
                connection_timeout=settings.mysql.mysql_connection_timeout,
                autocommit=True,
                use_pure=True
            )

            logger.info(f"连接到 MySQL: {settings.mysql.mysql_host}/{settings.mysql.mysql_database}")

            # 执行查询
            cursor = conn.cursor()
            cursor.execute(sql)

            # 获取列名
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # 获取数据
            rows = cursor.fetchall()

            # 转换为可序列化的格式
            serialized_rows = []
            for row in rows:
                serialized_row = []
                for value in row:
                    # 处理特殊类型
                    if isinstance(value, bytes):
                        serialized_row.append(value.decode('utf-8', errors='replace'))
                    elif value is None:
                        serialized_row.append(None)
                    else:
                        serialized_row.append(str(value))
                serialized_rows.append(serialized_row)

            result = {
                "columns": columns,
                "rows": serialized_rows,
                "row_count": len(serialized_rows),
                "success": True
            }

            logger.info(f"查询执行成功: 返回 {len(serialized_rows)} 行")

            return result

        except Error as e:
            retry_count += 1
            logger.error(f"MySQL 错误 (尝试 {retry_count}/{max_retries}): {e}")
            logger.error(f"错误代码: {e.errno}, SQL 状态: {getattr(e, 'sqlstate', 'N/A')}")

            if retry_count >= max_retries:
                raise Exception(f"MySQL 查询失败 (尝试 {max_retries} 次): {str(e)}")

            logger.info(f"1 秒后重试...")
            import asyncio
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"执行 SQL 时发生意外错误: {e}")
            raise Exception(f"查询执行失败: {str(e)}")

        finally:
            # 清理资源
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
                logger.debug("MySQL 连接已关闭")

    # 不应该到达这里
    raise Exception("查询失败：超出最大重试次数")


def _is_readonly_query(sql: str) -> bool:
    """
    验证是否为只读查询

    Args:
        sql: SQL 语句

    Returns:
        是否为只读查询
    """
    sql_upper = sql.strip().upper()

    # 只允许 SELECT 查询
    if not sql_upper.startswith("SELECT"):
        return False

    # 检查是否包含不允许的关键字
    forbidden_keywords = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "REPLACE",
        "RENAME",
        "CALL",
        "EXECUTE",
    ]

    for keyword in forbidden_keywords:
        if keyword in sql_upper:
            logger.warning(f"SQL 包含禁止的关键字: {keyword}")
            return False

    return True


def format_query_result(result: Dict[str, Any]) -> str:
    """
    格式化查询结果为可读文本

    Args:
        result: 查询结果

    Returns:
        格式化后的文本
    """
    if not result.get("success"):
        return "查询失败"

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    row_count = result.get("row_count", 0)

    if row_count == 0:
        return "查询成功，但没有返回数据"

    # 构建表格
    lines = []
    lines.append(f"查询成功，返回 {row_count} 行数据")
    lines.append("")

    # 表头
    lines.append(" | ".join(columns))
    lines.append("-" * (len(" | ".join(columns))))

    # 数据行（限制显示前 10 行）
    display_rows = rows[:10]
    for row in display_rows:
        lines.append(" | ".join(str(val) for val in row))

    if row_count > 10:
        lines.append("")
        lines.append(f"... 还有 {row_count - 10} 行数据未显示")

    return "\n".join(lines)
