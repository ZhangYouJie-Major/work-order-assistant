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
                "content": "查询海运所有箱型"
            }
        }
