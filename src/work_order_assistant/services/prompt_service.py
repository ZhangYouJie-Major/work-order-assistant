"""
提示词管理服务

负责加载和管理不同场景的提示词模板
"""

import os
from pathlib import Path
from typing import Literal, Optional
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PromptService:
    """提示词管理服务"""

    def __init__(self, prompts_dir: Optional[str] = None):
        """
        初始化提示词服务

        Args:
            prompts_dir: 提示词目录路径，如果不提供则使用配置中的路径
        """
        if prompts_dir is None:
            prompts_dir = settings.resource.prompts_dir
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            logger.warning(
                f"提示词目录未找到: {self.prompts_dir}. "
                "加载提示词时将创建。"
            )

    def load_intent_recognition_prompt(self) -> str:
        """
        加载意图识别提示词

        Returns:
            意图识别提示词内容
        """
        return self._load_file("base/intent_recognition.txt")

    def load_entity_extraction_prompt(
        self, operation_type: Literal["query", "mutation"]
    ) -> str:
        """
        根据操作类型加载实体提取提示词

        Args:
            operation_type: 操作类型 (query | mutation)

        Returns:
            对应的实体提取提示词内容
        """
        if operation_type == "query":
            # 加载查询类提示词
            return self._load_file("query/general_query.txt")
        else:
            # 加载变更类提示词
            return self._load_file("mutation/general_mutation.txt")


    def load_sql_generation_prompt(self) -> str:
        """
        加载 SQL 查询生成提示词

        Returns:
            SQL 生成提示词内容
        """
        return self._load_file("query/sql_generation.txt")

    def _load_file(self, relative_path: str) -> str:
        """
        加载提示词文件

        Args:
            relative_path: 相对于 prompts_dir 的文件路径

        Returns:
            文件内容

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        file_path = self.prompts_dir / relative_path

        if not file_path.exists():
            logger.error(f"提示词文件未找到: {file_path}")
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"从 {relative_path} 加载提示词")
                return content
        except Exception as e:
            logger.error(f"加载提示词文件失败 {file_path}: {e}")
            raise
