"""
SQL 查询节点

执行数据库查询并获取结果
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...tools.sql_tool import query_mysql, format_query_result
from ...utils.logger import get_logger

logger = get_logger(__name__)


async def sql_query_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    SQL 查询节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 query_result 和 sql
    """
    task_id = state.get("task_id")
    sql = state.get("sql")

    logger.info(f"[{task_id}] 开始执行 SQL 查询")

    # 检查 SQL 是否存在
    if not sql:
        logger.error(f"[{task_id}] 状态中缺少 SQL")
        return {
            "query_result": None,
            "error": "SQL 语句缺失，无法执行查询",
            "current_node": "sql_query",
        }

    try:
        # 调用 SQL 查询工具
        result = await query_mysql.ainvoke({"sql": sql})

        logger.info(
            f"[{task_id}] 查询执行成功: {result.get('row_count', 0)} 行"
        )

        # 格式化结果用于日志
        formatted_result = format_query_result(result)
        logger.debug(f"[{task_id}] 查询结果:\n{formatted_result}")

        return {
            "sql": sql,
            "query_result": result,
            "current_node": "sql_query",
        }

    except ValueError as e:
        # 只读查询验证失败
        logger.error(f"[{task_id}] SQL 验证失败: {e}")
        return {
            "sql": sql,
            "query_result": None,
            "error": f"SQL 验证失败: {str(e)}",
            "current_node": "sql_query",
        }

    except Exception as e:
        # 其他异常
        logger.error(f"[{task_id}] SQL 查询失败: {e}", exc_info=True)
        return {
            "sql": sql,
            "query_result": None,
            "error": f"查询执行失败: {str(e)}",
            "current_node": "sql_query",
        }
