"""
实体提取节点

从工单内容中提取结构化信息
"""

from typing import Dict, Any
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

        # 如果是 mutation 类型，加载查询步骤配置
        query_steps_config = None
        work_order_subtype = None

        if operation_type == "mutation":
            # 方案1：使用智能匹配（根据工单内容匹配最佳配置）
            logger.info(f"[{task_id}] 开始智能匹配变更配置")
            match_result = await mutation_steps_service.match_config_by_content(
                content, llm_service
            )

            if match_result:
                work_order_subtype, query_steps_config = match_result
                logger.info(
                    f"[{task_id}] 智能匹配成功: {work_order_subtype}, "
                    f"包含 {len(query_steps_config.get('steps', []))} 个步骤"
                )

                # 根据配置的 description 重新提取参数
                description = query_steps_config.get("description", "")
                logger.info(f"[{task_id}] 根据配置描述提取参数: {description}")

                # 调用 LLM 提取配置所需的参数
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
                    json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
                    if json_match:
                        params = json.loads(json_match.group(1))
                    else:
                        params = json.loads(result_text)

                    logger.info(f"[{task_id}] 提取的参数: {params}")

                    # 将提取的参数合并到 entities 中
                    entities.update(params)

                except Exception as e:
                    logger.error(f"[{task_id}] 参数提取失败: {e}")
                    # 继续使用原来的 entities

            else:
                # 方案2：回退到从 entities 获取 work_order_subtype
                work_order_subtype = entities.get("work_order_subtype")

                if work_order_subtype:
                    logger.info(f"[{task_id}] 从实体提取结果加载配置: {work_order_subtype}")
                    query_steps_config = mutation_steps_service.load_config(work_order_subtype)

                    if query_steps_config:
                        logger.info(f"[{task_id}] 为 {work_order_subtype} 加载了 {len(query_steps_config.get('steps', []))} 个步骤")
                    else:
                        logger.warning(f"[{task_id}] 未找到 {work_order_subtype} 的配置，将使用默认 DML 生成")
                else:
                    logger.warning(f"[{task_id}] 智能匹配失败且未指定 work_order_subtype，将使用默认 DML 生成")

        return {
            "entities": entities,
            "attachment_parsed_data": attachment_data,
            "query_steps_config": query_steps_config,
            "work_order_subtype": work_order_subtype,
            "current_node": "entity_extraction",
        }

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
