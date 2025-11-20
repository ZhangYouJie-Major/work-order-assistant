"""
DML 生成节点

生成数据变更 SQL 语句
"""

from typing import Dict, Any
import re
from ...workflows.state import WorkOrderState
from ...utils.logger import get_logger

logger = get_logger(__name__)


async def generate_dml_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    DML 生成节点

    根据多步骤查询结果或实体信息生成 DML 语句（支持多条 DML）

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 dml_info
    """
    task_id = state.get("task_id")
    entities = state.get("entities")
    query_steps_result = state.get("query_steps_result")
    query_steps_config = state.get("query_steps_config")
    config_match_failed = state.get("config_match_failed", False)

    logger.info(f"[{task_id}] 开始生成 DML")
    logger.info(f"[{task_id}] DEBUG: config_match_failed = {config_match_failed}")

    try:
        # 如果配置匹配失败，返回特殊的 dml_info，表示需要人工处理
        if config_match_failed:
            logger.warning(f"[{task_id}] 配置匹配失败，无法自动生成 DML，需要人工介入")
            return {
                "dml_info": {
                    "manual_intervention_required": True,
                    "reason": "工单内容不清晰或无法匹配到合适的配置，无法自动生成DML",
                    "operation_type": "MANUAL",
                    "affected_tables": [],
                    "sql": None,
                    "risk_level": "unknown",
                    "description": "此工单需要人工介入处理"
                },
                "current_node": "generate_dml",
            }

        # 基于多步骤查询配置生成 DML
        if query_steps_config and query_steps_result and query_steps_result.get("success"):
            logger.info(f"[{task_id}] 使用多步骤查询结果生成 DML")
            dml_info = _generate_dml_from_steps(
                task_id,
                query_steps_result
            )
        else:
            # 如果没有配置或查询失败，也需要人工介入
            logger.warning(f"[{task_id}] 缺少配置或多步骤查询失败，需要人工介入")
            return {
                "dml_info": {
                    "manual_intervention_required": True,
                    "reason": "缺少配置信息或多步骤查询执行失败，无法自动生成DML",
                    "operation_type": "MANUAL",
                    "affected_tables": [],
                    "sql": None,
                    "risk_level": "unknown",
                    "description": "此工单需要人工介入处理"
                },
                "current_node": "generate_dml",
            }

        # 记录生成的 SQL 语句数量
        sql_statements = dml_info.get("sql_statements", [dml_info.get("sql")])
        logger.info(
            f"[{task_id}] DML 生成完成: 共 {len(sql_statements)} 条语句 "
            f"(风险级别: {dml_info.get('risk_level')})"
        )

        return {
            "dml_info": dml_info,
            "sql": dml_info.get("sql"),  # 兼容性：保留单条 SQL
            "current_node": "generate_dml",
        }

    except Exception as e:
        logger.error(f"[{task_id}] DML 生成失败: {e}", exc_info=True)
        return {
            "dml_info": None,
            "error": f"DML 生成失败: {str(e)}",
            "current_node": "generate_dml",
        }


def _generate_dml_from_steps(
    task_id: str,
    query_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    从查询步骤结果中提取并生成所有 DML 语句

    Args:
        task_id: 任务 ID
        query_result: 多步骤查询结果

    Returns:
        DML 信息（包含多条 SQL）
    """
    steps = query_result.get("steps", [])
    context = query_result.get("context", {})

    sql_statements = []
    affected_tables = []
    max_risk_level = "low"

    # 遍历所有步骤，找到所有 GENERATE_DML 步骤
    for step_result in steps:
        if step_result.get("operation") != "GENERATE_DML":
            continue

        dml_config = step_result.get("dml_config")
        step_context = step_result.get("context_snapshot", context)

        if not dml_config:
            logger.warning(f"[{task_id}] DML 步骤缺少配置")
            continue

        # 提取 DML 配置
        dml_type = dml_config.get("type")
        table = dml_config.get("table")
        set_clause = dml_config.get("set", {})
        where_clause = dml_config.get("where", "")
        values_clause = dml_config.get("values", {})

        logger.info(f"[{task_id}] 为表 {table} 生成 {dml_type} DML")

        # 构建 SQL
        sql = _build_sql(dml_type, table, set_clause, where_clause, values_clause, step_context)
        sql_statements.append(sql)

        if table not in affected_tables:
            affected_tables.append(table)

        # 更新风险等级
        risk = _estimate_risk_level(dml_type, where_clause)
        if _compare_risk_level(risk, max_risk_level) > 0:
            max_risk_level = risk

    if not sql_statements:
        raise ValueError("No DML statements generated from steps")

    # 合并所有 SQL 语句
    combined_sql = ";\n".join(sql_statements) + ";"

    # 构建 DML 信息
    dml_info = {
        "operation_type": "MULTI_DML" if len(sql_statements) > 1 else sql_statements[0].split()[0],
        "affected_tables": affected_tables,
        "sql": combined_sql,  # 合并后的 SQL
        "sql_statements": sql_statements,  # 单独的 SQL 列表
        "statement_count": len(sql_statements),
        "context": context,
        "risk_level": max_risk_level,
        "description": f"执行 {len(sql_statements)} 条 DML 语句，影响表: {', '.join(affected_tables)}",
    }

    return dml_info


def _build_sql(
    dml_type: str,
    table: str,
    set_clause: Dict[str, Any],
    where_clause: str,
    values_clause: Dict[str, Any],
    context: Dict[str, Any]
) -> str:
    """
    构建 SQL 语句

    Args:
        dml_type: DML 类型（UPDATE/DELETE/INSERT）
        table: 表名
        set_clause: SET 子句（UPDATE）
        where_clause: WHERE 子句
        values_clause: VALUES 子句（INSERT）
        context: 变量上下文

    Returns:
        SQL 语句
    """
    if dml_type == "UPDATE":
        # 构建 SET 部分
        set_parts = []
        for field, value_template in set_clause.items():
            value = _replace_variables(value_template, context)
            set_parts.append(f"{field} = {value}")

        set_str = ", ".join(set_parts)

        # 构建 WHERE 部分
        where_str = _replace_variables(where_clause, context) if where_clause else ""

        # 组装 SQL
        sql = f"UPDATE {table} SET {set_str}"
        if where_str:
            sql += f" WHERE {where_str}"

        return sql

    elif dml_type == "DELETE":
        where_str = _replace_variables(where_clause, context) if where_clause else ""

        sql = f"DELETE FROM {table}"
        if where_str:
            sql += f" WHERE {where_str}"

        return sql

    elif dml_type == "INSERT":
        # 构建字段和值
        fields = []
        values = []

        for field, value_template in values_clause.items():
            fields.append(field)
            value = _replace_variables(value_template, context)
            values.append(value)

        fields_str = ", ".join(fields)
        values_str = ", ".join(values)

        sql = f"INSERT INTO {table} ({fields_str}) VALUES ({values_str})"

        return sql

    else:
        raise ValueError(f"Unsupported DML type: {dml_type}")


def _replace_variables(template: str, context: Dict[str, Any]) -> str:
    """
    替换模板中的变量

    支持格式: {variable_name}

    Args:
        template: 模板字符串
        context: 变量上下文

    Returns:
        替换后的字符串
    """
    # 处理 None 值（来自 JSON null）
    if template is None:
        return "NULL"

    # 处理数字类型（int, float）- 直接返回字符串形式，不加引号
    if isinstance(template, (int, float)):
        return str(template)

    # 处理特殊函数（如 NOW()）
    if isinstance(template, str) and template.upper() in ["NOW()", "CURRENT_TIMESTAMP()", "NULL"]:
        return template

    def replace_fn(match):
        var_name = match.group(1)
        value = context.get(var_name)

        if value is None:
            logger.warning(f"变量 '{var_name}' 在上下文中未找到")
            return "NULL"  # 返回 NULL 而不是保持原样

        # 如果是字符串，添加引号
        if isinstance(value, str):
            # 转义单引号
            escaped_value = value.replace("'", "''")
            return f"'{escaped_value}'"
        else:
            return str(value)

    template_str = str(template)

    # 检查是否包含变量占位符
    if '{' in template_str and '}' in template_str:
        # 包含变量，进行替换
        result = re.sub(r'\{(\w+)\}', replace_fn, template_str)
        return result
    else:
        # 不包含变量，视为字面量
        # 如果是数字字符串，不加引号
        if template_str.isdigit():
            return template_str
        # 其他情况加引号
        escaped_value = template_str.replace("'", "''")
        return f"'{escaped_value}'"


def _estimate_risk_level(dml_type: str, where_clause: str) -> str:
    """
    估算 DML 风险等级

    Args:
        dml_type: DML 类型
        where_clause: WHERE 条件

    Returns:
        风险等级（low/medium/high）
    """
    # DELETE 操作风险较高
    if dml_type == "DELETE":
        if not where_clause or where_clause.strip() == "":
            return "high"  # 无条件删除风险极高
        return "medium"

    # UPDATE 操作
    if dml_type == "UPDATE":
        if not where_clause or where_clause.strip() == "":
            return "high"  # 无条件更新风险极高
        return "low"

    # INSERT 操作
    if dml_type == "INSERT":
        return "low"

    return "medium"


def _compare_risk_level(risk1: str, risk2: str) -> int:
    """
    比较两个风险等级

    Args:
        risk1: 第一个风险等级
        risk2: 第二个风险等级

    Returns:
        如果 risk1 > risk2 返回 1
        如果 risk1 == risk2 返回 0
        如果 risk1 < risk2 返回 -1
    """
    risk_order = {"low": 0, "medium": 1, "high": 2}
    level1 = risk_order.get(risk1, 1)
    level2 = risk_order.get(risk2, 1)

    if level1 > level2:
        return 1
    elif level1 < level2:
        return -1
    else:
        return 0

