"""
工单相关 API 路由
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..schemas.request import WorkOrderSubmitRequest
from ..schemas.response import (
    WorkOrderSubmitResponse,
    WorkOrderSubmitResponseData,
    WorkOrderStatusResponse,
    WorkOrderStatusResponseData,
    HealthCheckResponse,
    ServiceStatus,
)
from ...workflows.work_order_workflow import work_order_app
from ...workflows.state import WorkOrderState
from ...config import settings
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/work-order", tags=["work-order"])

# 存储任务状态的内存字典（生产环境应使用 Redis 或数据库）
task_store: Dict[str, Dict[str, Any]] = {}


@router.post("", response_model=WorkOrderSubmitResponse)
async def submit_work_order(
    request: WorkOrderSubmitRequest, background_tasks: BackgroundTasks
):
    """
    提交工单（异步处理）

    接收工单请求，立即返回任务 ID，后台异步处理并发送邮件
    """
    # 生成任务 ID
    task_id = f"task-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

    logger.info(f"[{task_id}] 收到工单提交请求")

    # 初始化任务状态
    task_store[task_id] = {
        "task_id": task_id,
        "status": "accepted",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "request": request.model_dump(),
    }

    # 添加后台任务
    background_tasks.add_task(process_work_order, task_id, request)

    # 立即返回响应
    response = WorkOrderSubmitResponse(
        code=0,
        message="工单已接收，将异步处理并发送邮件通知",
        data=WorkOrderSubmitResponseData(
            task_id=task_id,
            status="accepted",
            estimated_time="预计 30-60 秒内完成处理",
            notify_emails=request.cc_emails,
            created_at=datetime.utcnow(),
        ),
    )

    logger.info(f"[{task_id}] 工单已接收，后台处理中")

    return response


@router.get("/{task_id}", response_model=WorkOrderStatusResponse)
async def get_work_order_status(task_id: str):
    """
    查询工单处理状态
    """
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = task_store[task_id]

    response_data = WorkOrderStatusResponseData(
        task_id=task_id,
        status=task.get("status", "unknown"),
        operation_type=task.get("operation_type"),
        current_node=task.get("current_node"),
        progress=task.get("progress"),
        email_sent=task.get("email_sent"),
        email_recipients=task.get("email_recipients"),
        created_at=task.get("created_at"),
        updated_at=task.get("updated_at"),
        completed_at=task.get("completed_at"),
        error=task.get("error"),
    )

    return WorkOrderStatusResponse(code=0, message="success", data=response_data)


async def process_work_order(task_id: str, request: WorkOrderSubmitRequest):
    """
    后台处理工单

    Args:
        task_id: 任务 ID
        request: 工单请求
    """
    logger.info(f"[{task_id}] 开始处理工单")

    # 更新状态为处理中
    task_store[task_id]["status"] = "processing"
    task_store[task_id]["updated_at"] = datetime.utcnow()

    try:
        # 构建初始状态
        initial_state: WorkOrderState = {
            "task_id": task_id,
            "content": request.content,
            "oss_attachments": [att.model_dump() for att in request.oss_attachments],
            "cc_emails": request.cc_emails,
            "user": request.user.model_dump() if request.user else {},
            "metadata": request.metadata.model_dump() if request.metadata else {},
        }

        # 执行工作流
        logger.info(f"[{task_id}] 调用工作流")
        final_state = await work_order_app.ainvoke(initial_state)

        # 更新任务状态
        task_store[task_id].update(
            {
                "status": "completed" if not final_state.get("error") else "failed",
                "operation_type": final_state.get("operation_type"),
                "current_node": final_state.get("current_node"),
                "email_sent": final_state.get("email_sent", False),
                "email_recipients": request.cc_emails,
                "error": final_state.get("error"),
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )

        if final_state.get("error"):
            logger.error(f"[{task_id}] 工作流失败: {final_state.get('error')}")
        else:
            logger.info(f"[{task_id}] 工作流完成")

    except Exception as e:
        logger.error(f"[{task_id}] 处理过程中发生意外错误: {e}")
        task_store[task_id].update(
            {
                "status": "failed",
                "error": str(e),
                "updated_at": datetime.utcnow(),
            }
        )


@router.get("/", response_model=dict)
async def list_work_orders():
    """
    列出所有工单（简单实现）
    """
    return {
        "code": 0,
        "message": "success",
        "data": {
            "tasks": [
                {
                    "task_id": task_id,
                    "status": task["status"],
                    "created_at": task["created_at"],
                }
                for task_id, task in task_store.items()
            ],
            "total": len(task_store),
        },
    }
