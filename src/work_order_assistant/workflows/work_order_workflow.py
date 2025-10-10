"""
工单处理工作流编排

使用 LangGraph 编排工单处理流程
"""

from langgraph.graph import StateGraph, END
from typing import Literal
from .state import WorkOrderState
from .nodes import (
    intent_recognition_node,
    entity_extraction_node,
    mcp_query_node,
    generate_dml_node,
    send_query_email_node,
    send_dml_email_node,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


def create_work_order_workflow():
    """
    创建工单处理工作流

    Returns:
        编译后的工作流应用
    """
    # 创建状态图
    workflow = StateGraph(WorkOrderState)

    # 添加节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("entity_extraction", entity_extraction_node)
    workflow.add_node("mcp_query", mcp_query_node)
    workflow.add_node("generate_dml", generate_dml_node)
    workflow.add_node("send_query_email", send_query_email_node)
    workflow.add_node("send_dml_email", send_dml_email_node)

    # 设置入口点
    workflow.set_entry_point("intent_recognition")

    # 意图识别 → 实体提取
    workflow.add_edge("intent_recognition", "entity_extraction")

    # 实体提取 → 条件分支（查询/变更）
    workflow.add_conditional_edges(
        "entity_extraction",
        _route_by_operation_type,
        {
            "query": "mcp_query",
            "mutation": "generate_dml",
            "error": END,
        },
    )

    # 查询路径：MCP查询 → 发送查询邮件 → 结束
    workflow.add_edge("mcp_query", "send_query_email")
    workflow.add_edge("send_query_email", END)

    # 变更路径：生成DML → 发送DML邮件 → 结束
    workflow.add_edge("generate_dml", "send_dml_email")
    workflow.add_edge("send_dml_email", END)

    # 编译工作流
    app = workflow.compile()

    logger.info("Work order workflow compiled successfully")

    return app


def _route_by_operation_type(
    state: WorkOrderState,
) -> Literal["query", "mutation", "error"]:
    """
    根据操作类型路由

    Args:
        state: 工作流状态

    Returns:
        路由目标节点
    """
    operation_type = state.get("operation_type")
    error = state.get("error")

    # 如果有错误，直接结束
    if error:
        logger.warning(f"Workflow error detected: {error}")
        return "error"

    # 根据操作类型路由
    if operation_type == "query":
        logger.info("Routing to query path")
        return "query"
    elif operation_type == "mutation":
        logger.info("Routing to mutation path")
        return "mutation"
    else:
        logger.error(f"Unknown operation type: {operation_type}")
        return "error"


# 创建全局工作流实例
work_order_app = create_work_order_workflow()
