"""
提示词管理服务

负责加载和管理不同场景的提示词模板
"""

import os
from pathlib import Path
from typing import Literal, Optional
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PromptService:
    """提示词管理服务"""

    def __init__(self, prompts_dir: str = "prompts"):
        """
        初始化提示词服务

        Args:
            prompts_dir: 提示词目录路径，默认为 "prompts"
        """
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            logger.warning(
                f"Prompts directory not found: {self.prompts_dir}. "
                "Will create when loading prompts."
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

    def load_query_specific_prompt(self, query_type: str) -> str:
        """
        加载特定类型的查询提示词

        Args:
            query_type: 查询类型 (user_query | order_query | log_query)

        Returns:
            特定查询类型的提示词
        """
        file_map = {
            "user_query": "query/user_query.txt",
            "order_query": "query/order_query.txt",
            "log_query": "query/log_query.txt",
        }

        file_path = file_map.get(query_type, "query/general_query.txt")
        return self._load_file(file_path)

    def load_mutation_specific_prompt(self, mutation_type: str) -> str:
        """
        加载特定类型的变更提示词

        Args:
            mutation_type: 变更类型 (data_update | data_insert | data_delete)

        Returns:
            特定变更类型的提示词
        """
        file_map = {
            "data_update": "mutation/data_update.txt",
            "data_insert": "mutation/data_insert.txt",
            "data_delete": "mutation/data_delete.txt",
        }

        file_path = file_map.get(mutation_type, "mutation/general_mutation.txt")
        return self._load_file(file_path)

    def load_context_analysis_prompt(self) -> str:
        """
        加载上下文分析提示词

        Returns:
            上下文分析提示词内容
        """
        return self._load_file("base/context_analysis.txt")

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
            logger.error(f"Prompt file not found: {file_path}")
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"Loaded prompt from {relative_path}")
                return content
        except Exception as e:
            logger.error(f"Failed to load prompt file {file_path}: {e}")
            raise

    def list_available_prompts(self) -> dict:
        """
        列出所有可用的提示词文件

        Returns:
            提示词文件字典，按类型分组
        """
        available_prompts = {
            "base": [],
            "query": [],
            "mutation": [],
        }

        if not self.prompts_dir.exists():
            return available_prompts

        for category in ["base", "query", "mutation"]:
            category_dir = self.prompts_dir / category
            if category_dir.exists():
                prompt_files = list(category_dir.glob("*.txt"))
                available_prompts[category] = [
                    f.stem for f in prompt_files  # 只返回文件名（不含扩展名）
                ]

        return available_prompts

    def prompt_exists(self, relative_path: str) -> bool:
        """
        检查提示词文件是否存在

        Args:
            relative_path: 相对于 prompts_dir 的文件路径

        Returns:
            文件是否存在
        """
        file_path = self.prompts_dir / relative_path
        return file_path.exists()
