"""
Mutation 步骤配置服务

加载和管理不同工单类型的查询步骤配置
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MutationStepsService:
    """Mutation 步骤配置服务"""

    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化服务

        Args:
            config_dir: 配置文件目录路径，如果不提供则使用配置中的路径
        """
        if config_dir is None:
            config_dir = settings.resource.mutation_steps_dir
        self.config_dir = Path(config_dir)

        logger.info(f"MutationStepsService 初始化，配置目录: {self.config_dir}")

        # 缓存已加载的配置
        self._config_cache: Dict[str, Dict[str, Any]] = {}

    def load_config(self, work_order_type: str) -> Optional[Dict[str, Any]]:
        """
        加载指定工单类型的配置

        Args:
            work_order_type: 工单类型（如 cancel_marine_order）

        Returns:
            配置字典，如果不存在则返回 None
        """
        # 检查缓存
        if work_order_type in self._config_cache:
            logger.debug(f"使用缓存的配置: {work_order_type}")
            return self._config_cache[work_order_type]

        # 构建配置文件路径
        config_file = self.config_dir / f"{work_order_type}.json"

        if not config_file.exists():
            logger.warning(f"配置文件未找到: {config_file}")
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            logger.info(f"加载配置 {work_order_type}: {len(config.get('steps', []))} 个步骤")

            # 缓存配置
            self._config_cache[work_order_type] = config

            return config

        except json.JSONDecodeError as e:
            logger.error(f"解析配置文件失败 {config_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"加载配置文件失败 {config_file}: {e}")
            return None

    def list_available_types(self) -> list:
        """
        列出所有可用的工单类型

        Returns:
            工单类型列表
        """
        if not self.config_dir.exists():
            logger.warning(f"配置目录未找到: {self.config_dir}")
            return []

        types = []
        for config_file in self.config_dir.glob("*.json"):
            # 排除 schema.json
            if config_file.stem != "schema":
                types.append(config_file.stem)

        logger.info(f"找到 {len(types)} 个变更类型: {types}")
        return types

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        验证配置格式是否正确

        Args:
            config: 配置字典

        Returns:
            是否有效
        """
        required_fields = ["work_order_type", "steps"]

        for field in required_fields:
            if field not in config:
                logger.error(f"缺少必需字段: {field}")
                return False

        steps = config.get("steps", [])
        if not isinstance(steps, list) or len(steps) == 0:
            logger.error("步骤必须是非空列表")
            return False

        # 验证每个步骤
        for step in steps:
            if "step" not in step or "operation" not in step:
                logger.error(f"无效的步骤: {step}")
                return False

            operation = step.get("operation")
            if operation not in ["QUERY", "GENERATE_DML", "RETURN_ERROR", "RETURN_SUCCESS"]:
                logger.error(f"无效的操作: {operation}")
                return False

            # QUERY 需要 table
            if operation == "QUERY":
                if "table" not in step:
                    logger.error(f"QUERY 步骤缺少 table: {step}")
                    return False

            # GENERATE_DML 需要 type 和 table
            elif operation == "GENERATE_DML":
                if "type" not in step or "table" not in step:
                    logger.error(f"GENERATE_DML 步骤缺少 type 或 table: {step}")
                    return False

            # RETURN_ERROR 和 RETURN_SUCCESS 需要 message
            elif operation in ["RETURN_ERROR", "RETURN_SUCCESS"]:
                if "message" not in step:
                    logger.warning(f"{operation} 步骤建议配置 message: {step}")

            # 验证分支配置（可选）
            for branch_key in ["on_success", "on_failure"]:
                branch = step.get(branch_key)
                if branch:
                    if not isinstance(branch, dict):
                        logger.error(f"{branch_key} 必须是字典类型: {step}")
                        return False

                    # condition 是可选的
                    # next_step 和 else_step 至少要有一个
                    if "next_step" not in branch and "else_step" not in branch:
                        logger.warning(f"{branch_key} 中应至少配置 next_step 或 else_step: {step}")

        return True

    def get_dml_step(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从配置中提取 DML 生成步骤

        Args:
            config: 配置字典

        Returns:
            DML 步骤配置，如果不存在则返回 None
        """
        steps = config.get("steps", [])

        for step in steps:
            if step.get("operation") == "GENERATE_DML":
                return step

        logger.warning("配置中未找到 GENERATE_DML 步骤")
        return None

    def load_all_configs(self) -> List[Dict[str, Any]]:
        """
        加载所有可用的配置文件

        Returns:
            配置列表，每个配置包含 work_order_type, description 和完整配置
        """
        configs = []

        if not self.config_dir.exists():
            logger.warning(f"配置目录未找到: {self.config_dir}")
            return configs

        for config_file in self.config_dir.glob("*.json"):
            # 排除 schema.json
            if config_file.stem == "schema":
                continue

            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                configs.append({
                    "work_order_type": config.get("work_order_type", config_file.stem),
                    "description": config.get("description", ""),
                    "config": config
                })

            except Exception as e:
                logger.error(f"加载配置文件失败 {config_file}: {e}")
                continue

        logger.info(f"加载了 {len(configs)} 个配置文件")
        return configs

    async def match_config_by_content(
        self,
        work_order_content: str,
        llm_service: Any
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        根据工单内容智能匹配最合适的配置

        Args:
            work_order_content: 工单内容
            llm_service: LLM 服务实例

        Returns:
            (work_order_type, config) 元组，如果没有匹配则返回 None
        """
        configs = self.load_all_configs()

        if not configs:
            logger.warning("没有可用的配置文件")
            return None

        # 构建匹配提示词
        descriptions = []
        for idx, cfg in enumerate(configs):
            descriptions.append(
                f"{idx + 1}. {cfg['work_order_type']}: {cfg['description']}"
            )

        system_prompt = "你是一个工单分类专家。请根据工单内容，从以下配置中选择最匹配的一个。"

        user_prompt = f"""工单内容：
{work_order_content}

可选配置：
{chr(10).join(descriptions)}

请仔细分析工单内容，判断它最符合哪个配置的描述。

输出格式（JSON）：
{{
    "matched_index": 匹配的配置序号（1-{len(configs)}），如果都不匹配则为 0,
    "confidence": 置信度（0.0-1.0）,
    "reasoning": "匹配理由"
}}
"""

        try:
            # 使用 LLMService 的正确调用方式
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # 调用 LLM
            response = await llm_service.llm.ainvoke(messages)
            result_text = response.content

            logger.info(f"配置匹配 LLM 输出: {result_text}")

            # 解析响应
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(result_text)

            matched_index = result.get("matched_index", 0)
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "")

            logger.info(f"配置匹配结果: index={matched_index}, confidence={confidence}")
            logger.info(f"匹配理由: {reasoning}")

            # 如果匹配到了配置且置信度足够高
            if matched_index > 0 and matched_index <= len(configs) and confidence >= 0.7:
                matched_config = configs[matched_index - 1]
                work_order_type = matched_config["work_order_type"]

                logger.info(f"成功匹配配置: {work_order_type} (置信度: {confidence})")

                return (work_order_type, matched_config["config"])
            else:
                logger.warning(f"未找到匹配的配置 (matched_index={matched_index}, confidence={confidence})")
                return None

        except Exception as e:
            logger.error(f"配置匹配失败: {e}", exc_info=True)
            return None
