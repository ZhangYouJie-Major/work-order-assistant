"""
实体提取节点

从工单内容中提取结构化信息
"""

from typing import Dict, Any, Optional
from ...workflows.state import WorkOrderState
from ...services.prompt_service import PromptService
from ...services.llm_service import LLMService
from ...services.oss_service import OSSService
from ...services.mutation_steps_service import MutationStepsService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
prompt_service = PromptService()
llm_service = LLMService(settings.llm)
oss_service = OSSService(settings.oss)
mutation_steps_service = MutationStepsService()


async def entity_extraction_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    实体提取节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 entities 和 attachment_parsed_data
    """
    task_id = state.get("task_id")
    content = state.get("content")
    operation_type = state.get("operation_type")
    oss_attachments = state.get("oss_attachments", [])

    logger.info(f"[{task_id}] 开始实体提取 (类型: {operation_type})")

    try:
        # 处理 OSS 附件（如果有）
        attachment_data = None
        if oss_attachments:
            logger.info(f"[{task_id}] 处理 {len(oss_attachments)} 个附件")
            attachment_data = await _process_attachments(task_id, oss_attachments)

        # 加载实体提取提示词
        prompt_template = prompt_service.load_entity_extraction_prompt(operation_type)

        # 调用 LLM 提取实体
        entities = await llm_service.extract_entities(
            content, prompt_template, attachment_data
        )

        logger.info(
            f"[{task_id}] 实体提取完成: tables={entities.get('target_tables')}"
        )

        # 智能匹配配置（query 和 mutation 都支持）
        query_steps_config = None
        work_order_subtype = None
        sql = None
        config_match_failed = False  # 标记配置匹配是否失败

        logger.info(f"[{task_id}] 开始智能匹配配置 (类型: {operation_type})")
        match_result = await mutation_steps_service.match_config_by_content(
            content, llm_service
        )

        if match_result:
            work_order_subtype, query_steps_config = match_result
            logger.info(
                f"[{task_id}] 智能匹配成功: {work_order_subtype}, "
                f"包含 {len(query_steps_config.get('steps', []))} 个步骤"
            )

            # 如果是 query 类型且有 final_sql_template，直接使用
            if operation_type == "query" and query_steps_config.get("final_sql_template"):
                sql = query_steps_config.get("final_sql_template")
                logger.info(f"[{task_id}] 使用配置模板 SQL: {sql}")

                # 根据配置的 description 提取参数，用于 SQL 参数替换
                description = query_steps_config.get("description", "")
                if description and "{" in sql:  # 如果 SQL 模板有参数占位符
                    logger.info(f"[{task_id}] 根据配置描述提取参数: {description}")
                    params = await _extract_params_from_description(
                        task_id, content, description, llm_service
                    )
                    if params:
                        entities.update(params)
                        # 替换 SQL 模板中的参数
                        try:
                            sql = sql.format(**params)
                            logger.info(f"[{task_id}] 参数替换后的 SQL: {sql}")
                        except KeyError as e:
                            logger.warning(f"[{task_id}] SQL 参数替换失败: {e}，使用原模板")

        # 如果是 query 类型但没有匹配到配置，或者没有 SQL 模板
        if operation_type == "query" and not sql:
            logger.info(f"[{task_id}] 未找到查询配置或 SQL 模板，使用 LLM 生成 SQL")
            try:
                # 加载 SQL 生成提示词
                sql_prompt = prompt_service.load_sql_generation_prompt()

                # 调用 LLM 生成 SQL
                sql = await llm_service.generate_sql_query(entities, sql_prompt)

                logger.info(f"[{task_id}] SQL 生成完成: {sql[:100]}...")
            except Exception as e:
                logger.error(f"[{task_id}] SQL 生成失败: {e}")
                return {
                    "entities": entities,
                    "error": f"SQL 生成失败: {str(e)}",
                    "current_node": "entity_extraction",
                }

        # 如果是 mutation 类型，需要提取参数用于多步骤查询
        if operation_type == "mutation":
            if match_result:
                # 已经匹配到配置，提取参数
                description = query_steps_config.get("description", "")
                logger.info(f"[{task_id}] 根据配置描述提取参数: {description}")

                params = await _extract_params_from_description(
                    task_id, content, description, llm_service
                )
                if params:
                    entities.update(params)
            else:
                # 方案2：回退到从 entities 获取 work_order_subtype
                work_order_subtype = entities.get("work_order_subtype")

                if work_order_subtype:
                    logger.info(f"[{task_id}] 从实体提取结果加载配置: {work_order_subtype}")
                    query_steps_config = mutation_steps_service.load_config(work_order_subtype)

                    if query_steps_config:
                        logger.info(f"[{task_id}] 为 {work_order_subtype} 加载了 {len(query_steps_config.get('steps', []))} 个步骤")
                    else:
                        logger.warning(f"[{task_id}] 未找到 {work_order_subtype} 的配置")
                        config_match_failed = True
                else:
                    logger.warning(f"[{task_id}] 智能匹配失败且未指定 work_order_subtype")
                    config_match_failed = True

        logger.info(f"[{task_id}] DEBUG: 返回 config_match_failed = {config_match_failed}")
        
        result = {
            "entities": entities,
            "attachment_parsed_data": attachment_data,
            "query_steps_config": query_steps_config,
            "work_order_subtype": work_order_subtype,
            "config_match_failed": config_match_failed,
            "current_node": "entity_extraction",
        }

        # 如果是 query 类型，将生成的 SQL 添加到状态
        if operation_type == "query" and sql:
            result["sql"] = sql

        return result

    except Exception as e:
        logger.error(f"[{task_id}] 实体提取失败: {e}")
        return {
            "entities": None,
            "error": f"实体提取失败: {str(e)}",
            "current_node": "entity_extraction",
        }


async def _process_attachments(
    task_id: str, oss_attachments: list
) -> Dict[str, Any]:
    """
    处理 OSS 附件

    Args:
        task_id: 任务 ID
        oss_attachments: OSS 附件列表

    Returns:
        解析后的附件数据
    """
    parsed_attachments = []

    for attachment in oss_attachments:
        try:
            url = attachment.get("url")
            mime_type = attachment.get("mime_type")
            filename = attachment.get("filename")

            logger.info(f"[{task_id}] 解析附件: {filename}")

            parsed_data = oss_service.parse_attachment(url, mime_type)
            parsed_attachments.append(
                {"filename": filename, "data": parsed_data}
            )

        except Exception as e:
            logger.warning(
                f"[{task_id}] 解析附件失败 {filename}: {e}"
            )
            # 继续处理其他附件

    if parsed_attachments:
        return {"attachments": parsed_attachments, "count": len(parsed_attachments)}
    else:
        return None


async def _extract_params_from_description(
    task_id: str,
    content: str,
    description: str,
    llm_service: LLMService,
) -> Optional[Dict[str, Any]]:
    """
    根据配置描述从工单内容中提取参数

    Args:
        task_id: 任务 ID
        content: 工单内容
        description: 参数描述
        llm_service: LLM 服务

    Returns:
        提取的参数字典，失败返回 None
    """
    param_prompt = f"""你是一个参数提取专家。请根据工单内容和参数描述，提取出所有需要的参数。

工单内容：
{content}

参数描述：
{description}

请仔细分析工单内容，提取出描述中提到的所有参数及其值。

输出格式（JSON）：
{{
    "param1_name": "param1_value",
    "param2_name": "param2_value",
    ...
}}

例如，如果描述是"入参的customerID是客户id，new_price是月费金额"，
工单是"请将客户ID为 1001 的电信客户数据表中的月费金额更新为 99.99 元"，
则应该输出：
{{
    "customerID": "1001",
    "new_price": "99.99"
}}
"""

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content="你是一个参数提取专家"),
        HumanMessage(content=param_prompt),
    ]

    try:
        response = await llm_service.llm.ainvoke(messages)
        result_text = response.content

        logger.info(f"[{task_id}] 参数提取 LLM 输出: {result_text}")

        # 解析响应
        import re
        import json

        json_match = re.search(r"```json\s*(.*?)\s*```", result_text, re.DOTALL)
        if json_match:
            params = json.loads(json_match.group(1))
        else:
            params = json.loads(result_text)

        logger.info(f"[{task_id}] 提取的参数: {params}")
        return params

    except Exception as e:
        logger.error(f"[{task_id}] 参数提取失败: {e}")
        return None
