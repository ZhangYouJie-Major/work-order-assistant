"""
多步骤 SQL 查询节点

用于 mutation 路径的多轮查询，支持步骤间数据传递
"""

from typing import Dict, Any, List, Optional
import re
from ...workflows.state import WorkOrderState
from ...tools.sql_tool import query_mysql
from ...utils.logger import get_logger

logger = get_logger(__name__)


async def multi_step_query_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    多步骤 SQL 查询节点

    根据配置执行多轮查询，每一步的结果可供后续步骤使用

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 query_steps_result
    """
    task_id = state.get("task_id")
    entities = state.get("entities", {})
    query_steps_config = state.get("query_steps_config")

    logger.info(f"[{task_id}] 开始执行多步骤查询")

    # 检查配置是否存在
    if not query_steps_config:
        logger.warning(f"[{task_id}] 未找到查询步骤配置，跳过多步骤查询")
        return {
            "query_steps_result": {},
            "current_node": "multi_step_query",
        }

    try:
        # 初始化上下文（用于变量替换）
        context = {
            **entities,  # 实体提取的结果
        }

        # 存储每步的查询结果
        all_step_results = []

        # 执行每一步
        steps = query_steps_config.get("steps", [])
        logger.info(f"[{task_id}] 执行 {len(steps)} 个查询步骤")

        for step_idx, step in enumerate(steps, start=1):
            step_num = step.get("step", step_idx)
            operation = step.get("operation")

            logger.info(f"[{task_id}] 执行步骤 {step_num}: {operation}")

            if operation == "QUERY":
                # 执行查询步骤
                step_result = await _execute_query_step(
                    task_id, step, context
                )
                all_step_results.append(step_result)

                # 将查询结果添加到上下文（供后续步骤使用）
                if step_result.get("success"):
                    _update_context_from_query_result(
                        context, step_result, step.get("output_fields", [])
                    )
                else:
                    # 如果某一步失败，终止后续执行
                    logger.error(f"[{task_id}] 步骤 {step_num} 失败，终止执行")
                    return {
                        "query_steps_result": {
                            "steps": all_step_results,
                            "success": False,
                            "error": step_result.get("error"),
                        },
                        "error": f"多步骤查询失败于步骤 {step_num}",
                        "current_node": "multi_step_query",
                    }

            elif operation == "GENERATE_DML":
                # DML生成步骤（记录元数据，实际生成在 generate_dml_node）
                logger.info(f"[{task_id}] 步骤 {step_num} 为 DML 生成（稍后处理）")
                all_step_results.append({
                    "step": step_num,
                    "operation": "GENERATE_DML",
                    "dml_config": step,
                })
            else:
                logger.warning(f"[{task_id}] 未知操作: {operation}")

        logger.info(f"[{task_id}] 多步骤查询完成")

        return {
            "query_steps_result": {
                "steps": all_step_results,
                "context": context,  # 传递给后续节点
                "success": True,
            },
            "current_node": "multi_step_query",
        }

    except Exception as e:
        logger.error(f"[{task_id}] 多步骤查询失败: {e}", exc_info=True)
        return {
            "query_steps_result": None,
            "error": f"多步骤查询失败: {str(e)}",
            "current_node": "multi_step_query",
        }


async def _execute_query_step(
    task_id: str,
    step: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    执行单个查询步骤

    Args:
        task_id: 任务 ID
        step: 步骤配置
        context: 当前上下文（用于变量替换）

    Returns:
        步骤执行结果
    """
    step_num = step.get("step")
    table = step.get("table")
    where = step.get("where")
    output_fields = step.get("output_fields", ["*"])

    try:
        # 构建 SELECT 语句
        select_fields = ", ".join(output_fields)
        sql_template = f"SELECT {select_fields} FROM {table}"

        if where:
            # 替换变量（如 {receipt_order_no}）
            where_clause = _replace_variables(where, context)
            sql_template += f" WHERE {where_clause}"

        logger.info(f"[{task_id}] 步骤 {step_num} SQL: {sql_template}")

        # 执行查询
        result = await query_mysql.ainvoke({"sql": sql_template})

        if not result.get("success"):
            return {
                "step": step_num,
                "table": table,
                "sql": sql_template,
                "success": False,
                "error": "查询执行失败",
            }

        row_count = result.get("row_count", 0)
        logger.info(f"[{task_id}] 步骤 {step_num} 返回 {row_count} 行")

        return {
            "step": step_num,
            "table": table,
            "sql": sql_template,
            "columns": result.get("columns", []),
            "rows": result.get("rows", []),
            "row_count": row_count,
            "success": True,
        }

    except Exception as e:
        logger.error(f"[{task_id}] 步骤 {step_num} 执行失败: {e}")
        return {
            "step": step_num,
            "table": table,
            "success": False,
            "error": str(e),
        }


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
    def replace_fn(match):
        var_name = match.group(1)
        value = context.get(var_name)

        if value is None:
            logger.warning(f"变量 '{var_name}' 在上下文中未找到")
            return match.group(0)  # 保持原样

        # 如果是字符串，添加引号
        if isinstance(value, str):
            return f"'{value}'"
        else:
            return str(value)

    # 匹配 {variable_name} 格式
    result = re.sub(r'\{(\w+)\}', replace_fn, template)
    return result


def _update_context_from_query_result(
    context: Dict[str, Any],
    query_result: Dict[str, Any],
    output_fields: List[str]
) -> None:
    """
    将查询结果更新到上下文

    Args:
        context: 上下文字典（会被修改）
        query_result: 查询结果
        output_fields: 输出字段列表
    """
    rows = query_result.get("rows", [])
    columns = query_result.get("columns", [])

    if not rows:
        logger.warning("查询未返回数据，上下文未更新")
        return

    # 只取第一行数据
    first_row = rows[0]

    # 将列映射到上下文
    for idx, col_name in enumerate(columns):
        if col_name in output_fields or "*" in output_fields:
            context[col_name] = first_row[idx] if idx < len(first_row) else None
            logger.debug(f"上下文已更新: {col_name} = {context[col_name]}")
