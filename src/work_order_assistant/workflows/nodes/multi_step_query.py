"""
多步骤 SQL 查询节点

用于 mutation 路径的多轮查询，支持步骤间数据传递、条件分支和跳转
"""

from typing import Dict, Any, List, Optional
import re
from ...workflows.state import WorkOrderState
from ...tools.sql_tool import query_mysql
from ...utils.logger import get_logger
from ...utils.condition_evaluator import evaluate_condition

logger = get_logger(__name__)


async def multi_step_query_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    多步骤 SQL 查询节点

    根据配置执行多轮查询，支持条件分支和跳转

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 query_steps_result
    """
    task_id = state.get("task_id")
    entities = state.get("entities", {})
    query_steps_config = state.get("query_steps_config")

    logger.info(f"[{task_id}] 开始执行多步骤查询（支持条件分支）")

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

        # 构建步骤索引（step_num -> step_config）
        steps_list = query_steps_config.get("steps", [])
        steps_dict = {step.get("step", idx + 1): step for idx, step in enumerate(steps_list)}

        logger.info(f"[{task_id}] 加载 {len(steps_dict)} 个步骤")

        # 从第一步开始执行
        current_step_num = 1
        max_iterations = 100  # 防止无限循环
        iteration = 0

        while current_step_num is not None and iteration < max_iterations:
            iteration += 1

            # 检查步骤是否存在
            if current_step_num not in steps_dict:
                logger.error(f"[{task_id}] 步骤 {current_step_num} 不存在")
                return {
                    "query_steps_result": {
                        "steps": all_step_results,
                        "success": False,
                        "error": f"步骤 {current_step_num} 不存在",
                    },
                    "error": f"步骤 {current_step_num} 不存在",
                    "current_node": "multi_step_query",
                }

            step = steps_dict[current_step_num]
            operation = step.get("operation")

            logger.info(f"[{task_id}] 执行步骤 {current_step_num}: {operation}")

            # 根据操作类型执行
            if operation == "QUERY":
                step_result = await _execute_query_step(task_id, step, context)
                all_step_results.append(step_result)

                if step_result.get("success"):
                    # 更新上下文
                    _update_context_from_query_result(
                        context, step_result, step.get("output_fields", [])
                    )
                    # 确定下一步（on_success 分支）
                    current_step_num = _determine_next_step(
                        step, context, branch="on_success"
                    )
                else:
                    # 查询失败，走 on_failure 分支
                    logger.warning(f"[{task_id}] 步骤 {current_step_num} 查询失败")
                    current_step_num = _determine_next_step(
                        step, context, branch="on_failure"
                    )
                    # 如果没有配置失败分支，则终止
                    if current_step_num is None:
                        logger.error(f"[{task_id}] 步骤失败且无失败分支，终止执行")
                        return {
                            "query_steps_result": {
                                "steps": all_step_results,
                                "success": False,
                                "error": step_result.get("error"),
                            },
                            "error": f"多步骤查询失败于步骤 {step.get('step')}",
                            "current_node": "multi_step_query",
                        }

            elif operation == "GENERATE_DML":
                # DML生成步骤（记录元数据，实际生成在 generate_dml_node）
                logger.info(f"[{task_id}] 步骤 {current_step_num} 为 DML 生成（稍后处理）")
                all_step_results.append({
                    "step": current_step_num,
                    "operation": "GENERATE_DML",
                    "dml_config": step,
                    "context_snapshot": context.copy(),  # 保存上下文快照
                })
                # 确定下一步（支持条件跳转）
                current_step_num = _determine_next_step(step, context, branch="on_success")

            elif operation == "RETURN_ERROR":
                # 返回错误
                error_message = step.get("message", "未知错误")
                logger.info(f"[{task_id}] 步骤 {current_step_num} 返回错误: {error_message}")
                all_step_results.append({
                    "step": current_step_num,
                    "operation": "RETURN_ERROR",
                    "message": error_message,
                })
                return {
                    "query_steps_result": {
                        "steps": all_step_results,
                        "context": context,
                        "success": False,
                        "error": error_message,
                    },
                    "error": error_message,
                    "current_node": "multi_step_query",
                }

            elif operation == "RETURN_SUCCESS":
                # 返回成功
                success_message = step.get("message", "操作成功")
                logger.info(f"[{task_id}] 步骤 {current_step_num} 返回成功: {success_message}")
                all_step_results.append({
                    "step": current_step_num,
                    "operation": "RETURN_SUCCESS",
                    "message": success_message,
                })
                return {
                    "query_steps_result": {
                        "steps": all_step_results,
                        "context": context,
                        "success": True,
                        "message": success_message,
                    },
                    "current_node": "multi_step_query",
                }

            else:
                logger.warning(f"[{task_id}] 未知操作: {operation}")
                # 尝试跳转到下一步
                current_step_num = step.get("next_step")

        # 检查是否超过最大迭代次数
        if iteration >= max_iterations:
            logger.error(f"[{task_id}] 步骤执行超过最大迭代次数，可能存在循环")
            return {
                "query_steps_result": {
                    "steps": all_step_results,
                    "success": False,
                    "error": "步骤执行超过最大迭代次数",
                },
                "error": "步骤执行超过最大迭代次数",
                "current_node": "multi_step_query",
            }

        logger.info(f"[{task_id}] 多步骤查询完成，共执行 {iteration} 步")

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
        # 查询未返回数据，显式将字段设置为 None
        logger.warning("查询未返回数据，将输出字段设置为 None")
        for field in output_fields:
            if field != "*":
                context[field] = None
                logger.debug(f"上下文已更新: {field} = None")
        return

    # 只取第一行数据
    first_row = rows[0]

    # 将列映射到上下文
    for idx, col_name in enumerate(columns):
        if col_name in output_fields or "*" in output_fields:
            context[col_name] = first_row[idx] if idx < len(first_row) else None
            logger.debug(f"上下文已更新: {col_name} = {context[col_name]}")



def _determine_next_step(
    step: Dict[str, Any],
    context: Dict[str, Any],
    branch: str = "on_success"
) -> Optional[int]:
    """
    根据配置和条件确定下一步

    Args:
        step: 当前步骤配置
        context: 当前上下文
        branch: 分支类型 ("on_success" 或 "on_failure")

    Returns:
        下一步步骤编号，如果没有则返回 None
    """
    # 获取分支配置
    branch_config = step.get(branch)

    if not branch_config:
        # 如果没有配置分支，尝试直接获取 next_step
        # 使用 "in" 判断键是否存在，区分"不存在"和"存在但为null"
        if "next_step" in step:
            next_step = step.get("next_step")
            logger.debug(f"使用默认 next_step: {next_step}")
            return next_step
        else:
            # 没有配置任何跳转，顺序执行下一步
            current_num = step.get("step")
            if current_num is not None:
                return current_num + 1
            return None

    # 检查是否有条件判断
    condition = branch_config.get("condition")

    if condition:
        # 有条件，进行求值
        try:
            condition_result = evaluate_condition(condition, context)
            logger.debug(f"条件 '{condition}' 求值结果: {condition_result}")

            if condition_result:
                # 条件为真，跳转到 next_step
                next_step = branch_config.get("next_step")
                logger.debug(f"条件满足，跳转到步骤: {next_step}")
                return next_step
            else:
                # 条件为假，跳转到 else_step
                else_step = branch_config.get("else_step")
                logger.debug(f"条件不满足，跳转到步骤: {else_step}")
                return else_step

        except Exception as e:
            logger.error(f"条件求值失败: {condition}, 错误: {e}")
            # 求值失败，尝试走 else 分支
            return branch_config.get("else_step")
    else:
        # 没有条件，直接返回 next_step
        next_step = branch_config.get("next_step")
        logger.debug(f"无条件，直接跳转到步骤: {next_step}")
        return next_step

