"""
MCP (Model Context Protocol) 服务

负责与 MCP 服务器交互，执行数据库查询
"""

from typing import Dict, Any, Optional
import httpx
from ..config import MCPSettings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MCPService:
    """MCP 工具服务"""

    def __init__(self, settings: MCPSettings):
        """
        初始化 MCP 服务

        Args:
            settings: MCP 配置
        """
        self.settings = settings
        self.base_url = settings.mcp_server_url.rstrip("/")
        self.api_key = settings.mcp_api_key
        logger.info(f"MCP Service initialized: server={self.base_url}")

    async def execute_query(
        self, sql: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行只读 SQL 查询

        Args:
            sql: SQL 查询语句
            params: 查询参数（可选）

        Returns:
            查询结果，格式:
            {
                "columns": ["col1", "col2"],
                "rows": [[val1, val2], ...],
                "row_count": 10
            }

        Raises:
            ValueError: 如果 SQL 不是只读查询
            Exception: 查询执行失败
        """
        # 验证 SQL 是否为只读查询
        if not self._is_readonly_query(sql):
            raise ValueError("只允许执行 SELECT 查询")

        logger.info(f"Executing MCP query: {sql[:100]}...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/query",
                    json={"sql": sql, "params": params or {}},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                response.raise_for_status()
                result = response.json()

                logger.info(
                    f"Query executed successfully: {result.get('row_count', 0)} rows"
                )

                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"MCP query failed with HTTP {e.response.status_code}: {e}")
            raise Exception(f"MCP 查询失败: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"MCP query request error: {e}")
            raise Exception(f"MCP 连接失败: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during MCP query: {e}")
            raise

    def _is_readonly_query(self, sql: str) -> bool:
        """
        验证是否为只读查询

        Args:
            sql: SQL 语句

        Returns:
            是否为只读查询
        """
        sql_upper = sql.strip().upper()

        # 只允许 SELECT 查询
        if not sql_upper.startswith("SELECT"):
            return False

        # 检查是否包含不允许的关键字
        forbidden_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
        ]

        for keyword in forbidden_keywords:
            if keyword in sql_upper:
                logger.warning(
                    f"SQL contains forbidden keyword: {keyword}"
                )
                return False

        return True

    async def test_connection(self) -> bool:
        """
        测试 MCP 连接

        Returns:
            连接是否成功
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )

                response.raise_for_status()
                logger.info("MCP connection test successful")
                return True

        except Exception as e:
            logger.error(f"MCP connection test failed: {e}")
            return False

    def validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
        """
        验证 SQL 语法（基础检查）

        Args:
            sql: SQL 语句

        Returns:
            验证结果
        """
        errors = []

        # 检查是否为空
        if not sql or not sql.strip():
            errors.append("SQL 语句不能为空")

        # 检查是否为只读查询
        if not self._is_readonly_query(sql):
            errors.append("只允许执行 SELECT 查询")

        # 检查基本语法
        if sql.strip().endswith(";"):
            # 移除末尾分号是可选的，这里只是提示
            pass

        result = {"valid": len(errors) == 0, "errors": errors}

        if errors:
            logger.warning(f"SQL validation failed: {errors}")
        else:
            logger.debug("SQL validation passed")

        return result
