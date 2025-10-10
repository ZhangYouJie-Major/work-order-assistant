"""
API 响应模型
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class WorkOrderSubmitResponseData(BaseModel):
    """工单提交响应数据"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态 (accepted=已接受)")
    estimated_time: str = Field(..., description="预计处理时间")
    notify_emails: List[str] = Field(..., description="将接收邮件通知的邮箱列表")
    created_at: datetime = Field(..., description="任务创建时间")


class WorkOrderSubmitResponse(BaseModel):
    """工单提交响应"""

    code: int = Field(0, description="状态码 (0=成功, 非0=失败)")
    message: str = Field("工单已接收，将异步处理并发送邮件通知", description="状态消息")
    data: WorkOrderSubmitResponseData = Field(..., description="响应数据")


class ProgressInfo(BaseModel):
    """处理进度信息"""

    completed_nodes: List[str] = Field(..., description="已完成的节点")
    current_step: str = Field(..., description="当前步骤描述")
    progress_percent: int = Field(..., description="进度百分比")


class WorkOrderStatusResponseData(BaseModel):
    """工单状态查询响应数据"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(
        ..., description="任务状态 (accepted/processing/completed/failed)"
    )
    operation_type: Optional[str] = Field(None, description="操作类型")
    current_node: Optional[str] = Field(None, description="当前节点")
    progress: Optional[ProgressInfo] = Field(None, description="处理进度")
    email_sent: Optional[bool] = Field(None, description="邮件是否已发送")
    email_recipients: Optional[List[str]] = Field(None, description="邮件接收人")
    created_at: datetime = Field(..., description="任务创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error: Optional[str] = Field(None, description="错误信息")


class WorkOrderStatusResponse(BaseModel):
    """工单状态查询响应"""

    code: int = Field(0, description="状态码")
    message: str = Field("success", description="状态消息")
    data: WorkOrderStatusResponseData = Field(..., description="响应数据")


class ServiceStatus(BaseModel):
    """服务状态"""

    llm: str = Field(..., description="LLM 服务状态")
    mcp: str = Field(..., description="MCP 服务状态")
    oss: str = Field(..., description="OSS 服务状态")
    email: str = Field(..., description="邮件服务状态")


class HealthCheckResponse(BaseModel):
    """健康检查响应"""

    status: str = Field("healthy", description="健康状态")
    version: str = Field(..., description="版本号")
    timestamp: datetime = Field(..., description="时间戳")
    services: ServiceStatus = Field(..., description="各服务状态")


class ErrorDetail(BaseModel):
    """错误详情"""

    field: str = Field(..., description="错误字段")
    message: str = Field(..., description="错误消息")


class ErrorResponseData(BaseModel):
    """错误响应数据"""

    errors: Optional[List[ErrorDetail]] = Field(None, description="错误列表")


class ErrorResponse(BaseModel):
    """错误响应"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    data: Optional[ErrorResponseData] = Field(None, description="错误详情")

    class Config:
        json_schema_extra = {
            "example": {
                "code": 400,
                "message": "请求参数验证失败",
                "data": {
                    "errors": [
                        {"field": "cc_emails", "message": "抄送邮箱列表不能为空"}
                    ]
                },
            }
        }
