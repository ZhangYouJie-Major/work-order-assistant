"""
LangGraph 工作流状态定义
"""

from typing import Optional, Literal, List
from typing_extensions import TypedDict


class WorkOrderState(TypedDict, total=False):
    """
    工单处理工作流状态

    使用 TypedDict 定义状态，便于 LangGraph 管理
    """

    # ============ 输入字段 ============
    task_id: str
    """任务 ID"""

    content: str
    """工单正文内容"""

    oss_attachments: List[dict]
    """OSS 附件列表"""

    cc_emails: List[str]
    """抄送邮箱列表"""

    user: dict
    """用户信息"""

    metadata: dict
    """元数据"""

    # ============ 处理过程状态 ============
    operation_type: Optional[Literal["query", "mutation"]]
    """操作类型 (query=查询, mutation=变更)"""

    entities: Optional[dict]
    """提取的实体信息"""

    sql: Optional[str]
    """生成的 SQL 语句"""

    query_result: Optional[dict]
    """查询结果（用于 query 类型）"""

    dml_info: Optional[dict]
    """DML 信息（用于 mutation 类型）"""

    email_sent: Optional[bool]
    """邮件是否已发送"""

    # ============ Mutation 多步骤查询 ============
    query_steps_config: Optional[dict]
    """多步骤查询配置（用于 mutation 类型）"""

    query_steps_result: Optional[dict]
    """多步骤查询结果（用于 mutation 类型）"""

    work_order_subtype: Optional[str]
    """工单子类型（如 cancel_marine_order, update_quotation）"""

    config_match_failed: Optional[bool]
    """配置匹配是否失败（用于判断是否需要人工介入）"""

    # ============ 错误信息 ============
    error: Optional[str]
    """错误信息"""

    current_node: Optional[str]
    """当前处理节点"""

    # ============ 附件解析数据 ============
    attachment_parsed_data: Optional[dict]
    """解析后的附件数据"""
