"""
意图识别节点

从工单内容中识别操作类型（查询/变更）
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...services.prompt_service import PromptService
from ...services.llm_service import LLMService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
prompt_service = PromptService()
llm_service = LLMService(settings.llm)


async def intent_recognition_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    意图识别节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 operation_type
    """
    task_id = state.get("task_id")
    content = state.get("content")

    logger.info(f"[{task_id}] 开始意图识别")

    try:
        # 加载意图识别提示词
        prompt_template = prompt_service.load_intent_recognition_prompt()

        # 调用 LLM 识别意图
        result = await llm_service.recognize_intent(content, prompt_template)

        operation_type = result.get("operation_type", "unknown")
        confidence = result.get("confidence", 0.0)

        logger.info(
            f"[{task_id}] 意图识别完成: {operation_type} "
            f"(置信度: {confidence})"
        )

        return {
            "operation_type": operation_type,
            "current_node": "intent_recognition",
        }

    except Exception as e:
        logger.error(f"[{task_id}] 意图识别失败: {e}")
        return {
            "operation_type": "unknown",
            "error": f"意图识别失败: {str(e)}",
            "current_node": "intent_recognition",
        }
