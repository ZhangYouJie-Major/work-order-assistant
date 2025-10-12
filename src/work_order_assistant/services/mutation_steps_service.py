"""
Mutation 步骤配置服务

加载和管理不同工单类型的查询步骤配置
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
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
            if operation not in ["QUERY", "GENERATE_DML"]:
                logger.error(f"无效的操作: {operation}")
                return False

            # QUERY 需要 table 和 output_fields
            if operation == "QUERY":
                if "table" not in step:
                    logger.error(f"QUERY 步骤缺少 table: {step}")
                    return False

            # GENERATE_DML 需要 type 和 table
            elif operation == "GENERATE_DML":
                if "type" not in step or "table" not in step:
                    logger.error(f"GENERATE_DML 步骤缺少 type 或 table: {step}")
                    return False

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
