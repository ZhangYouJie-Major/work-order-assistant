"""
DML 生成节点

生成数据变更 SQL 语句
"""

from typing import Dict, Any
import re
from ...workflows.state import WorkOrderState
from ...services.llm_service import LLMService
from ...services.prompt_service import PromptService
from ...services.mutation_steps_service import MutationStepsService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
llm_service = LLMService(settings.llm)
prompt_service = PromptService()
mutation_steps_service = MutationStepsService()


async def generate_dml_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    DML 生成节点

    根据多步骤查询结果或实体信息生成 DML 语句

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 dml_info
    """
    task_id = state.get("task_id")
    entities = state.get("entities")
    query_steps_result = state.get("query_steps_result")
    query_steps_config = state.get("query_steps_config")

    logger.info(f"[{task_id}] 开始生成 DML")

    try:
        # 模式1: 基于多步骤查询配置生成 DML
        if query_steps_config and query_steps_result and query_steps_result.get("success"):
            logger.info(f"[{task_id}] 使用多步骤查询结果生成 DML")
            dml_info = _generate_dml_from_config(
                task_id,
                query_steps_config,
                query_steps_result
            )
        # 模式2: 使用 LLM 生成 DML（回退方案）
        else:
            logger.info(f"[{task_id}] 使用 LLM 生成 DML")
            prompt_template = prompt_service.load_mutation_specific_prompt("data_update")
            dml_info = await llm_service.generate_dml(entities, prompt_template)

        logger.info(
            f"[{task_id}] DML 生成完成: {dml_info.get('operation_type')} "
            f"操作表 {dml_info.get('affected_tables')} "
            f"(风险级别: {dml_info.get('risk_level')})"
        )

        return {
            "dml_info": dml_info,
            "sql": dml_info.get("sql"),
            "current_node": "generate_dml",
        }

    except Exception as e:
        logger.error(f"[{task_id}] DML 生成失败: {e}", exc_info=True)
        return {
            "dml_info": None,
            "error": f"DML 生成失败: {str(e)}",
            "current_node": "generate_dml",
        }


def _generate_dml_from_config(
    task_id: str,
    config: Dict[str, Any],
    query_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    基于配置和查询结果生成 DML

    Args:
        task_id: 任务 ID
        config: 查询步骤配置
        query_result: 多步骤查询结果

    Returns:
        DML 信息
    """
    # 获取 DML 生成步骤
    dml_step = mutation_steps_service.get_dml_step(config)

    if not dml_step:
        raise ValueError("No GENERATE_DML step found in config")

    # 获取查询结果的上下文
    context = query_result.get("context", {})

    # 提取 DML 配置
    dml_type = dml_step.get("type")
    table = dml_step.get("table")
    set_clause = dml_step.get("set", {})
    where_clause = dml_step.get("where", "")
    values_clause = dml_step.get("values", {})

    logger.info(f"[{task_id}] 为表 {table} 生成 {dml_type} DML")

    # 构建 SQL
    sql = _build_sql(dml_type, table, set_clause, where_clause, values_clause, context)

    # 构建 DML 信息
    dml_info = {
        "operation_type": dml_type,
        "affected_tables": [table],
        "sql": sql,
        "context": context,
        "risk_level": _estimate_risk_level(dml_type, where_clause),
        "description": f"{dml_type} {table}",
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
    # 处理特殊函数（如 NOW()）
    if isinstance(template, str) and template.upper() in ["NOW()", "CURRENT_TIMESTAMP()", "NULL"]:
        return template

    def replace_fn(match):
        var_name = match.group(1)
        value = context.get(var_name)

        if value is None:
            logger.warning(f"变量 '{var_name}' 在上下文中未找到")
            return match.group(0)  # 保持原样

        # 如果是字符串，添加引号
        if isinstance(value, str):
            # 转义单引号
            escaped_value = value.replace("'", "''")
            return f"'{escaped_value}'"
        else:
            return str(value)

    # 匹配 {variable_name} 格式
    result = re.sub(r'\{(\w+)\}', replace_fn, str(template))
    return result


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
