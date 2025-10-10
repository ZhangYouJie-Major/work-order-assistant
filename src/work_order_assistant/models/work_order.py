"""
工单数据模型
"""

from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class WorkOrderUser(BaseModel):
    """工单提交用户信息"""

    email: EmailStr = Field(..., description="用户邮箱")
    name: str = Field(..., description="用户姓名")
    department: Optional[str] = Field(None, description="用户部门")


class WorkOrderMetadata(BaseModel):
    """工单元数据"""

    ticket_id: Optional[str] = Field(None, description="工单编号")
    priority: Optional[str] = Field(
        "medium", description="优先级 (low/medium/high)"
    )
    source_system: Optional[str] = Field(None, description="来源系统")


class WorkOrder(BaseModel):
    """工单完整模型"""

    content: str = Field(..., description="工单正文内容")
    oss_attachments: List[dict] = Field(default_factory=list, description="OSS 附件列表")
    cc_emails: List[EmailStr] = Field(..., description="抄送邮箱列表")
    user: WorkOrderUser = Field(..., description="用户信息")
    metadata: Optional[WorkOrderMetadata] = Field(None, description="元数据")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "查询用户 ID 为 12345 的订单信息，最近 7 天的，包括订单金额、状态和创建时间",
                "oss_attachments": [
                    {
                        "filename": "requirement.xlsx",
                        "url": "https://oss.example.com/uploads/2025/10/requirement_20251010.xlsx",
                        "size": 102400,
                        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    }
                ],
                "cc_emails": ["user@example.com", "manager@example.com"],
                "user": {
                    "email": "user@example.com",
                    "name": "张三",
                    "department": "运营部",
                },
                "metadata": {
                    "ticket_id": "WO-2025-001",
                    "priority": "medium",
                    "source_system": "OA",
                },
            }
        }
