"""
LLM 服务

负责与大语言模型交互，执行意图识别、实体提取等任务
"""

import json
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from ..config import LLMSettings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LLMService:
    """LLM 服务"""

    def __init__(self, settings: LLMSettings):
        """
        初始化 LLM 服务

        Args:
            settings: LLM 配置
        """
        self.settings = settings
        self.llm = self._create_llm()
        self.json_parser = JsonOutputParser()

    def _create_llm(self) -> ChatOpenAI:
        """
        创建 LLM 客户端

        Returns:
            LLM 客户端实例
        """
        return ChatOpenAI(
            model=self.settings.openai_model,
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            temperature=0.0,  # 使用确定性输出
        )

    async def recognize_intent(
        self, work_order_content: str, prompt_template: str
    ) -> Dict[str, Any]:
        """
        识别工单意图

        Args:
            work_order_content: 工单正文内容
            prompt_template: 意图识别提示词模板

        Returns:
            意图识别结果，格式:
            {
                "operation_type": "query" | "mutation",
                "confidence": 0.95,
                "reasoning": "分析理由"
            }
        """
        logger.info("开始意图识别")

        try:
            # 构建提示词
            system_prompt = prompt_template
            user_prompt = f"""
工单内容:
{work_order_content}

请分析这个工单的操作类型，返回 JSON 格式:
{{
    "operation_type": "query" 或 "mutation",
    "confidence": 0.0-1.0 的置信度分数,
    "reasoning": "分析理由"
}}
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # 调用 LLM
            response = await self.llm.ainvoke(messages)
            logger.info(f"LLM 输出: {response.content}")
            result_text = response.content

            # 解析 JSON 响应
            result = self._parse_json_response(result_text)

            logger.info(
                f"意图识别完成: {result.get('operation_type')} "
                f"(置信度: {result.get('confidence')})"
            )

            return result

        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            raise

    async def extract_entities(
        self,
        work_order_content: str,
        prompt_template: str,
        attachment_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        提取工单实体信息

        Args:
            work_order_content: 工单正文内容
            prompt_template: 实体提取提示词模板
            attachment_data: 附件数据（可选）

        Returns:
            实体信息，格式:
            {
                "target_tables": ["orders", "users"],
                "conditions": {"user_id": 12345, "date_range": "7 days"},
                "fields": ["order_id", "amount", "status", "created_at"],
                "expected_result": "查询用户最近 7 天的订单信息"
            }
        """
        logger.info("开始实体提取")

        try:
            # 构建提示词
            system_prompt = prompt_template

            user_prompt = f"""
工单内容:
{work_order_content}
"""

            # 如果有附件数据，添加到提示词中
            if attachment_data:
                user_prompt += f"""

附件数据:
{json.dumps(attachment_data, ensure_ascii=False, indent=2)}
"""

            user_prompt += """

请从工单内容中提取结构化信息，返回 JSON 格式:
{
    "target_tables": ["表名列表"],
    "conditions": {"条件字段": "条件值"},
    "fields": ["目标字段列表"],
    "expected_result": "预期结果描述"
}
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # 调用 LLM
            response = await self.llm.ainvoke(messages)
            result_text = response.content

            # 解析 JSON 响应
            result = self._parse_json_response(result_text)

            logger.info(
                f"实体提取完成: tables={result.get('target_tables')}, "
                f"fields={len(result.get('fields', []))} 个字段"
            )

            return result

        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            raise


    async def generate_sql_query(
        self, entities: Dict[str, Any], prompt_template: str
    ) -> str:
        """
        生成 SQL 查询语句

        Args:
            entities: 提取的实体信息
            prompt_template: SQL 生成提示词模板

        Returns:
            SQL 查询语句
        """
        logger.info("开始生成 SQL 查询语句")

        try:
            system_prompt = prompt_template

            user_prompt = f"""
提取的实体信息:
{json.dumps(entities, ensure_ascii=False, indent=2)}

请生成规范的 SELECT 查询语句，返回 JSON 格式:
{{
    "sql": "SELECT 语句"
}}
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # 调用 LLM
            response = await self.llm.ainvoke(messages)
            result_text = response.content

            # 解析 JSON 响应
            result = self._parse_json_response(result_text)
            sql = result.get("sql", "")

            logger.info(f"SQL 查询生成完成: {sql[:100]}...")

            return sql

        except Exception as e:
            logger.error(f"SQL 查询生成失败: {e}")
            raise

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的 JSON 响应

        Args:
            response_text: LLM 响应文本

        Returns:
            解析后的 JSON 对象

        Raises:
            ValueError: 如果响应不是有效的 JSON
        """
        try:
            # 尝试直接解析
            return json.loads(response_text)
        except json.JSONDecodeError:
            # 如果失败，尝试提取 JSON 代码块
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
                return json.loads(json_str)
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
                return json.loads(json_str)
            else:
                # 最后尝试，去除可能的前后缀
                json_str = response_text.strip()
                return json.loads(json_str)
