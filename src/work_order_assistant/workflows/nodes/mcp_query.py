"""
MCP 查询节点

执行数据库查询并获取结果
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...services.mcp_service import MCPService
from ...services.llm_service import LLMService
from ...services.prompt_service import PromptService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
mcp_service = MCPService(settings.mcp)
llm_service = LLMService(settings.llm)
prompt_service = PromptService()


async def mcp_query_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    MCP 查询节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 query_result 和 sql
    """
    task_id = state.get("task_id")
    entities = state.get("entities")

    logger.info(f"[{task_id}] Starting MCP query execution")

    try:
        # 生成 SQL 查询语句
        # 这里简化处理，实际可以使用 LLM 生成 SQL
        sql = await _generate_query_sql(entities)

        logger.info(f"[{task_id}] Generated SQL: {sql[:100]}...")

        # 执行查询
        result = await mcp_service.execute_query(sql)

        logger.info(
            f"[{task_id}] Query executed successfully: {result.get('row_count')} rows"
        )

        return {
            "sql": sql,
            "query_result": result,
            "current_node": "mcp_query",
        }

    except Exception as e:
        logger.error(f"[{task_id}] MCP query failed: {e}")
        return {
            "sql": None,
            "query_result": None,
            "error": f"查询执行失败: {str(e)}",
            "current_node": "mcp_query",
        }


async def _generate_query_sql(entities: Dict[str, Any]) -> str:
    """
    从实体信息生成 SQL 查询语句

    Args:
        entities: 实体信息

    Returns:
        SQL 查询语句
    """
    # 简化实现：直接从实体构建 SQL
    # 实际应该使用 LLM 生成更复杂的 SQL

    target_tables = entities.get("target_tables", [])
    fields = entities.get("fields", ["*"])
    conditions = entities.get("conditions", {})

    if not target_tables:
        raise ValueError("未找到目标表")

    # 构建 SELECT 语句
    fields_str = ", ".join(fields) if fields else "*"
    table_str = target_tables[0]  # 简化处理，只使用第一个表

    # 构建 WHERE 子句
    where_clauses = []
    for key, value in conditions.items():
        if isinstance(value, str):
            where_clauses.append(f"{key} = '{value}'")
        else:
            where_clauses.append(f"{key} = {value}")

    sql = f"SELECT {fields_str} FROM {table_str}"

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    # 添加限制，防止查询过多数据
    sql += " LIMIT 1000"

    return sql
