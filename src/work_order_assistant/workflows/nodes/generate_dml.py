"""
DML 生成节点

生成数据变更 SQL 语句
"""

from typing import Dict, Any
from ...workflows.state import WorkOrderState
from ...services.llm_service import LLMService
from ...services.prompt_service import PromptService
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

# 初始化服务
llm_service = LLMService(settings.llm)
prompt_service = PromptService()


async def generate_dml_node(state: WorkOrderState) -> Dict[str, Any]:
    """
    DML 生成节点

    Args:
        state: 工作流状态

    Returns:
        更新后的状态，包含 dml_info
    """
    task_id = state.get("task_id")
    entities = state.get("entities")

    logger.info(f"[{task_id}] Starting DML generation")

    try:
        # 加载 DML 生成提示词
        # 这里简化处理，实际可以根据更细的分类加载不同的提示词
        prompt_template = prompt_service.load_mutation_specific_prompt(
            "data_update"
        )  # 默认使用更新提示词

        # 调用 LLM 生成 DML
        dml_info = await llm_service.generate_dml(entities, prompt_template)

        logger.info(
            f"[{task_id}] DML generated: {dml_info.get('operation_type')} "
            f"on {dml_info.get('affected_tables')} "
            f"(risk: {dml_info.get('risk_level')})"
        )

        return {
            "dml_info": dml_info,
            "sql": dml_info.get("sql"),
            "current_node": "generate_dml",
        }

    except Exception as e:
        logger.error(f"[{task_id}] DML generation failed: {e}")
        return {
            "dml_info": None,
            "error": f"DML 生成失败: {str(e)}",
            "current_node": "generate_dml",
        }
