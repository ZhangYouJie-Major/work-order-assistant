"""
操作相关数据模型
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class OperationType:
    """操作类型枚举"""

    QUERY = "query"
    MUTATION = "mutation"
    UNKNOWN = "unknown"


class OSSAttachment(BaseModel):
    """OSS 附件模型"""

    filename: str = Field(..., description="文件名")
    url: str = Field(..., description="OSS 下载地址")
    size: Optional[int] = Field(None, description="文件大小（字节）")
    mime_type: str = Field(..., description="MIME 类型")


class EntityInfo(BaseModel):
    """实体提取信息"""

    target_tables: List[str] = Field(default_factory=list, description="目标表")
    conditions: dict = Field(default_factory=dict, description="查询/变更条件")
    fields: List[str] = Field(default_factory=list, description="目标字段")
    expected_result: Optional[str] = Field(None, description="预期结果描述")
    attachment_data: Optional[dict] = Field(None, description="附件解析数据")


class QueryResult(BaseModel):
    """查询结果"""

    columns: List[str] = Field(..., description="列名列表")
    rows: List[List] = Field(..., description="数据行列表")
    row_count: int = Field(..., description="返回行数")
    sql: str = Field(..., description="执行的 SQL 语句")


class DMLInfo(BaseModel):
    """DML 语句信息"""

    sql: str = Field(..., description="DML 语句")
    operation_type: Literal["INSERT", "UPDATE", "DELETE"] = Field(
        ..., description="操作类型"
    )
    affected_tables: List[str] = Field(..., description="影响的表")
    estimated_rows: Optional[int] = Field(None, description="预计影响行数")
    risk_level: Literal["low", "medium", "high"] = Field(..., description="风险等级")
    description: Optional[str] = Field(None, description="操作说明")
    conditions: Optional[dict] = Field(None, description="WHERE 条件")
