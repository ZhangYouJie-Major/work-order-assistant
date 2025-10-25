# 工单智能处理助手系统设计文档

## 1. 系统概述

基于 LangGraph 和 MCP (Model Context Protocol) 的智能工单处理系统，接收审批流系统的工单请求，通过 LLM 理解工单内容，自动识别操作类型（查询/变更），执行相应操作后通过邮件将结果（查询数据或 DML 语句）发送给运维人员作为参考。

**核心定位**：异步邮件通知系统，而非实时响应系统。接口立即返回，后台异步处理并发送邮件。

## 2. 设计思路

### 2.1 核心理念

- **异步处理**：接口立即返回，后台异步处理工单并发送邮件通知
- **智能理解**：利用大模型的自然语言理解能力，从非结构化工单中提取结构化信息
- **提示词工程**：针对不同业务场景维护专用提示词模板，提升准确性
- **邮件通知**：将处理结果（查询数据/DML语句）通过邮件发送给运维人员作为参考
- **可扩展性**：基于 LangGraph 状态机架构，流程清晰易维护

### 2.2 处理流程

```
┌─────────────────────────────────────────────────────────┐
│                    审批流系统                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ POST /api/v1/work-order
                       │ {content, oss_attachments, cc_emails}
                       ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI 接口层（同步响应）                   │
│  立即返回: {"code": 0, "task_id": "xxx", "message":      │
│            "工单已接收，将异步处理并发送邮件通知"}          │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ 投递到后台异步任务队列
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph 工作流引擎                     │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │  Node 1: 意图识别                           │         │
│  │  ├─ 加载 base/intent_recognition.txt      │         │
│  │  ├─ LLM 分析工单内容                       │         │
│  │  └─ 输出: operation_type (query/mutation) │         │
│  └──────────────────┬─────────────────────────┘         │
│                     │                                    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────┐         │
│  │  Node 2: 实体提取 + 智能配置匹配            │         │
│  │  ├─ 提取: 目标表/条件/字段                 │         │
│  │  ├─ [mutation] 智能匹配配置文件             │         │
│  │  ├─ [mutation] 提取配置所需参数             │         │
│  │  └─ 下载并解析 OSS 附件（如有）            │         │
│  └──────────────────┬─────────────────────────┘         │
│                     │                                    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────┐         │
│  │  Conditional Edge: 操作分流                 │         │
│  └────┬───────────────────────────────┬───────┘         │
│       │                               │                 │
│  query│                               │mutation         │
│       ▼                               ▼                 │
│  ┌─────────────┐              ┌──────────────┐         │
│  │ Node 3a:    │              │ Node 3b:     │         │
│  │ SQL查询     │              │ 多步骤查询    │         │
│  │ ├─调用tool  │              │ ├─执行step1  │         │
│  │ └─获取数据  │              │ ├─执行step2  │         │
│  └──────┬──────┘              │ └─上下文传递 │         │
│         │                     └──────┬───────┘         │
│         │                            ▼                 │
│         │                     ┌──────────────┐         │
│         │                     │ Node 3c:     │         │
│         │                     │ 生成DML      │         │
│         │                     │ ├─基于配置   │         │
│         │                     │ ├─变量替换   │         │
│         │                     │ └─风险评估   │         │
│         │                     └──────┬───────┘         │
│         ▼                            ▼                 │
│  ┌─────────────┐              ┌──────────────┐         │
│  │ Node 4a:    │              │ Node 4b:     │         │
│  │ 发送查询结果│              │ 打印DML      │         │
│  │ ├─生成Excel │              │ ├─执行SQL    │         │
│  │ ├─邮件抄送  │              │ ├─SQL模板    │         │
│  │ └─cc_emails │              │ ├─参数列表   │         │
│  └─────────────┘              │ └─风险评估   │         │
│                               └──────────────┘         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.3 为什么使用 LangGraph？

**LangGraph 相比传统 LangChain Agent 的优势：**

1. **明确的流程控制**
   - 本系统有清晰的流程：意图识别 → 实体提取 → 条件分支 → 邮件发送
   - LangGraph 的状态机模型完美匹配这种固定流程
   - Agent 的自主决策能力在这里是多余的

2. **条件分支支持**
   - 查询操作和变更操作走不同的处理路径
   - LangGraph 的 ConditionalEdge 原生支持
   - 代码更清晰，逻辑更直观

3. **状态持久化**
   - 可以保存每个节点的处理状态
   - 便于异步任务的暂停/恢复
   - 方便排查问题和审计

4. **可视化调试**
   - LangGraph 可以导出流程图
   - 便于团队理解和维护
   - 新增节点更简单

5. **错误恢复**
   - 某个节点失败可以重试
   - 不需要重新执行整个流程

**核心代码示例：**

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

class WorkOrderState(TypedDict):
    task_id: str
    content: str
    oss_attachments: list
    cc_emails: list
    operation_type: Literal["query", "mutation"]
    entities: dict
    result: dict

# 定义节点
def intent_recognition_node(state: WorkOrderState):
    # 调用 LLM 识别意图
    return {"operation_type": "query"}

def entity_extraction_node(state: WorkOrderState):
    # 提取实体
    return {"entities": {...}}

def mcp_query_node(state: WorkOrderState):
    # 执行查询
    return {"result": {...}}

def send_email_node(state: WorkOrderState):
    # 发送邮件
    return state

# 构建图
workflow = StateGraph(WorkOrderState)
workflow.add_node("intent_recognition", intent_recognition_node)
workflow.add_node("entity_extraction", entity_extraction_node)
workflow.add_node("mcp_query", mcp_query_node)
workflow.add_node("generate_dml", generate_dml_node)
workflow.add_node("send_query_email", send_query_email_node)
workflow.add_node("send_dml_email", send_dml_email_node)

# 添加边
workflow.set_entry_point("intent_recognition")
workflow.add_edge("intent_recognition", "entity_extraction")
workflow.add_conditional_edges(
    "entity_extraction",
    lambda state: state["operation_type"],
    {
        "query": "mcp_query",
        "mutation": "generate_dml"
    }
)
workflow.add_edge("mcp_query", "send_query_email")
workflow.add_edge("generate_dml", "send_dml_email")
workflow.add_edge("send_query_email", END)
workflow.add_edge("send_dml_email", END)

app = workflow.compile()
```

### 2.4 技术架构

```
┌────────────────────────────────────────────────────────┐
│               FastAPI Application                      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │         API Layer (同步响应)                      │ │
│  │  - 接收请求并验证                                 │ │
│  │  - 生成 task_id                                  │ │
│  │  - 投递到后台任务队列                             │ │
│  │  - 立即返回响应                                   │ │
│  └────────────┬─────────────────────────────────────┘ │
│               │                                         │
│               ▼                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │      Background Task Queue (异步处理)             │ │
│  │  - Celery / asyncio.create_task                  │ │
│  └────────────┬─────────────────────────────────────┘ │
└───────────────┼─────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│             LangGraph Workflow Engine                  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │     State Management (状态持久化)                 │ │
│  │  - Task ID → State 映射                          │ │
│  │  - 支持状态查询和恢复                             │ │
│  └──────────────────────────────────────────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │     Nodes (处理节点)                              │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 1. Intent Recognition (意图识别)          │   │ │
│  │  │    - LLM Service                         │   │ │
│  │  │    - Prompt Service                      │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 2. Entity Extraction (实体提取)           │   │ │
│  │  │    - OSS Download Service                │   │ │
│  │  │    - LLM Service                         │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 3a. MCP Query (查询执行)                  │   │ │
│  │  │     - MCP Client                         │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 3b. Generate DML (生成SQL)                │   │ │
│  │  │     - LLM Service                        │   │ │
│  │  │     - SQL Validator                      │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 4a. Send Query Email (发送查询结果)       │   │ │
│  │  │     - Email Service                      │   │ │
│  │  │     - Excel Generator                    │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 4b. Send DML Email (发送DML邮件)          │   │ │
│  │  │     - Email Service                      │   │ │
│  │  │     - HTML Template Renderer             │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## 3. 项目架构

```
work-order-assistant/
├── pyproject.toml              # 项目配置和依赖管理
├── README.md                   # 项目说明
├── DESIGN.md                   # 本设计文档
├── .env.example                # 环境变量示例
├── src/
│   └── work_order_assistant/
│       ├── __init__.py
│       ├── main.py             # FastAPI 应用入口
│       ├── config.py           # 配置管理
│       │
│       ├── api/                # API 层
│       │   ├── __init__.py
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   └── work_order.py    # 工单接口
│       │   ├── schemas/
│       │   │   ├── __init__.py
│       │   │   ├── request.py       # 请求模型
│       │   │   └── response.py      # 响应模型
│       │   └── dependencies.py      # 依赖注入
│       │
│       ├── workflows/          # LangGraph 工作流
│       │   ├── __init__.py
│       │   ├── work_order_workflow.py  # 工单处理工作流
│       │   ├── nodes/
│       │   │   ├── __init__.py
│       │   │   ├── intent_recognition.py    # 意图识别节点
│       │   │   ├── entity_extraction.py     # 实体提取节点
│       │   │   ├── sql_query.py             # SQL 查询节点
│       │   │   ├── multi_step_query.py      # 多步骤查询节点
│       │   │   ├── generate_dml.py          # DML 生成节点
│       │   │   ├── send_query_email.py      # 发送查询邮件节点
│       │   │   └── send_dml_email.py        # 发送 DML 邮件节点
│       │   └── state.py        # 工作流状态定义
│       │
│       ├── services/           # 业务逻辑层
│       │   ├── __init__.py
│       │   ├── llm_service.py          # LLM 服务
│       │   ├── oss_service.py          # OSS 下载服务
│       │   ├── prompt_service.py       # 提示词管理服务
│       │   ├── email_service.py        # 邮件服务
│       │   └── mutation_steps_service.py  # Mutation 步骤配置服务
│       │
│       ├── tools/              # 工具层
│       │   ├── __init__.py
│       │   └── sql_tool.py             # SQL 执行工具
│       │
│       ├── models/             # 数据模型
│       │   ├── __init__.py
│       │   ├── work_order.py           # 工单模型
│       │   └── operation.py            # 操作模型
│       │
│       └── utils/              # 工具函数
│           ├── __init__.py
│           ├── logger.py               # 日志工具（简化 JSON 格式）
│           ├── validators.py           # 验证器
│           └── excel_generator.py      # Excel 生成工具
│
├── resources/                  # 资源文件目录
│   ├── prompts/                # 提示词模板目录
│   │   ├── base/
│   │   │   ├── intent_recognition.txt      # 意图识别
│   │   │   ├── entity_extraction.txt       # 实体提取
│   │   │   └── context_analysis.txt        # 上下文分析
│   │   │
│   │   ├── query/              # 查询类工单
│   │   │   ├── user_query.txt              # 用户查询
│   │   │   ├── order_query.txt             # 订单查询
│   │   │   └── log_query.txt               # 日志查询
│   │   │
│   │   └── mutation/           # 变更类工单
│   │       ├── data_update.txt             # 数据更新
│   │       ├── data_insert.txt             # 数据插入
│   │       └── data_delete.txt             # 数据删除
│   │
│   └── configs/                # 配置文件目录
│       └── mutation_steps/     # 变更步骤配置（重要）
│           ├── schema.json                 # 配置文件 Schema
│           ├── update_telco_customer.json  # 更新电信客户示例
│           └── cancel_marine_order.json    # 取消海运单示例
│
├── tests/                      # 测试目录
│   ├── __init__.py
│   ├── test_api/
│   ├── test_services/
│   └── test_workflows/
│
└── logs/                       # 日志目录
    └── .gitkeep
```

## 4. 接口设计

### 4.1 工单提交接口（异步处理）

**接口路径**: `POST /api/v1/work-order/submit`

**请求头**:
```
Content-Type: application/json
X-API-Key: <api_key>  # 可选的 API 认证
```

**请求体**:
```json
{
  "content": "查询用户 ID 为 12345 的订单信息，最近 7 天的，包括订单金额、状态和创建时间",
  "oss_attachments": [
    {
      "filename": "requirement.xlsx",
      "url": "https://oss.example.com/uploads/2025/10/requirement_20251010.xlsx",
      "size": 102400,
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
  ],
  "cc_emails": [
    "user@example.com",
    "manager@example.com"
  ],
  "user": {
    "email": "user@example.com",
    "name": "张三",
    "department": "运营部"
  },
  "metadata": {
    "ticket_id": "WO-2025-001",
    "priority": "medium",
    "source_system": "OA"
  }
}
```

**请求参数说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | 是 | 工单正文内容 |
| oss_attachments | array | 否 | OSS 附件列表 |
| oss_attachments[].filename | string | 是 | 附件文件名 |
| oss_attachments[].url | string | 是 | OSS 附件下载地址 |
| oss_attachments[].size | integer | 否 | 文件大小（字节） |
| oss_attachments[].mime_type | string | 是 | 附件 MIME 类型 |
| cc_emails | array | 是 | 抄送邮箱列表（接收处理结果） |
| user | object | 是 | 用户信息 |
| user.email | string | 是 | 用户邮箱 |
| user.name | string | 是 | 用户姓名 |
| user.department | string | 否 | 用户部门 |
| metadata | object | 否 | 元数据 |
| metadata.ticket_id | string | 否 | 工单编号 |
| metadata.priority | string | 否 | 优先级 (low/medium/high) |
| metadata.source_system | string | 否 | 来源系统 |

**成功响应（立即返回）**:
```json
{
  "code": 0,
  "message": "工单已接收，将异步处理并发送邮件通知",
  "data": {
    "task_id": "task-20251010-uuid-12345",
    "status": "accepted",
    "estimated_time": "预计 30-60 秒内完成处理",
    "notify_emails": [
      "user@example.com",
      "manager@example.com"
    ],
    "created_at": "2025-10-10T10:30:00Z"
  }
}
```

**响应参数说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| code | integer | 状态码 (0=成功, 非0=失败) |
| message | string | 状态消息 |
| data.task_id | string | 任务 ID，用于后续状态查询 |
| data.status | string | 任务状态 (accepted=已接受) |
| data.estimated_time | string | 预计处理时间 |
| data.notify_emails | array | 将接收邮件通知的邮箱列表 |
| data.created_at | string | 任务创建时间 (ISO 8601) |

**错误响应示例**:
```json
{
  "code": 400,
  "message": "请求参数验证失败",
  "data": {
    "errors": [
      {
        "field": "cc_emails",
        "message": "抄送邮箱列表不能为空"
      }
    ]
  }
}
```

**邮件发送逻辑**:

1. **查询操作**:
   - 通过 MCP 执行查询获取数据
   - 将查询结果生成 Excel 附件
   - 发送邮件到 `cc_emails` 列表
   - 邮件标题：`【工单查询结果】{ticket_id} - {简短描述}`
   - 邮件内容：查询 SQL、结果摘要、Excel 附件

2. **变更操作**:
   - 生成规范的 DML 语句
   - 发送邮件到运维/开发邮箱（配置在环境变量中）
   - 抄送到 `cc_emails` 列表
   - 邮件标题：`【工单 DML 待执行】{ticket_id} - {简短描述}`
   - 邮件内容：SQL 语句（语法高亮）、影响范围、风险评估

### 4.2 工单状态查询接口

**接口路径**: `GET /api/v1/work-order/{task_id}`

**响应示例**:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "task-20251010-uuid-12345",
    "status": "completed",
    "operation_type": "query",
    "current_node": "send_query_email",
    "progress": {
      "completed_nodes": [
        "intent_recognition",
        "entity_extraction",
        "mcp_query",
        "send_query_email"
      ],
      "current_step": "已发送查询结果邮件",
      "progress_percent": 100
    },
    "email_sent": true,
    "email_recipients": ["user@example.com", "manager@example.com"],
    "created_at": "2025-10-10T10:30:00Z",
    "updated_at": "2025-10-10T10:30:45Z",
    "completed_at": "2025-10-10T10:30:45Z"
  }
}
```

**状态枚举**:
- `accepted`: 已接受，等待处理
- `processing`: 处理中
- `completed`: 已完成
- `failed`: 处理失败

### 4.3 健康检查接口

**接口路径**: `GET /health`

**响应示例**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-10-10T10:30:00Z",
  "services": {
    "llm": "connected",
    "mcp": "connected",
    "oss": "connected",
    "email": "connected"
  }
}
```

## 5. 核心组件设计

### 5.1 LangGraph 工作流设计

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal, Optional

class WorkOrderState(TypedDict):
    """工单处理状态"""
    task_id: str
    content: str
    oss_attachments: list
    cc_emails: list
    user: dict
    metadata: dict

    # 处理过程中的状态
    operation_type: Optional[Literal["query", "mutation"]]
    entities: Optional[dict]
    sql: Optional[str]
    query_result: Optional[dict]
    dml_info: Optional[dict]
    email_sent: Optional[bool]
    error: Optional[str]

# 工作流构建
def create_work_order_workflow():
    workflow = StateGraph(WorkOrderState)

    # 添加节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("entity_extraction", entity_extraction_node)
    workflow.add_node("mcp_query", mcp_query_node)
    workflow.add_node("generate_dml", generate_dml_node)
    workflow.add_node("send_query_email", send_query_email_node)
    workflow.add_node("send_dml_email", send_dml_email_node)
    workflow.add_node("handle_error", handle_error_node)

    # 设置入口
    workflow.set_entry_point("intent_recognition")

    # 意图识别 → 实体提取
    workflow.add_edge("intent_recognition", "entity_extraction")

    # 实体提取 → 条件分支（查询/变更）
    workflow.add_conditional_edges(
        "entity_extraction",
        lambda state: state.get("operation_type", "unknown"),
        {
            "query": "mcp_query",
            "mutation": "generate_dml",
            "unknown": "handle_error"
        }
    )

    # 查询 → 发送查询邮件 → 结束
    workflow.add_edge("mcp_query", "send_query_email")
    workflow.add_edge("send_query_email", END)

    # 变更 → 发送 DML 邮件 → 结束
    workflow.add_edge("generate_dml", "send_dml_email")
    workflow.add_edge("send_dml_email", END)

    # 错误处理 → 结束
    workflow.add_edge("handle_error", END)

    return workflow.compile()
```

### 5.2 提示词加载策略

```python
class PromptService:
    """提示词管理服务"""

    def __init__(self, prompts_dir: str = "prompts"):
        self.prompts_dir = prompts_dir

    def load_intent_recognition_prompt(self) -> str:
        """加载意图识别提示词"""
        return self._load_file("base/intent_recognition.txt")

    def load_entity_extraction_prompt(
        self,
        operation_type: Literal["query", "mutation"]
    ) -> str:
        """
        根据操作类型加载实体提取提示词

        operation_type: query | mutation
        返回对应的提示词模板
        """
        if operation_type == "query":
            # 可以根据更细的分类加载不同的提示词
            # 例如: user_query, order_query, log_query
            return self._load_file("query/general_query.txt")
        else:
            return self._load_file("mutation/general_mutation.txt")

    def _load_file(self, relative_path: str) -> str:
        """加载提示词文件"""
        file_path = os.path.join(self.prompts_dir, relative_path)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
```

### 5.3 MCP 服务集成

```python
from mcp import MCPClient

class MCPService:
    """MCP 工具服务"""

    def __init__(self, server_url: str, api_key: str):
        self.client = MCPClient(server_url, api_key)

    async def execute_query(self, sql: str, params: dict = None) -> dict:
        """
        执行只读 SQL 查询

        返回: {
            "columns": ["col1", "col2"],
            "rows": [[val1, val2], ...],
            "row_count": 10
        }
        """
        # 验证 SQL 是否为只读查询
        if not self._is_readonly_query(sql):
            raise ValueError("只允许执行 SELECT 查询")

        result = await self.client.query(sql, params)
        return result

    def _is_readonly_query(self, sql: str) -> bool:
        """验证是否为只读查询"""
        sql_upper = sql.strip().upper()
        return sql_upper.startswith("SELECT")
```

### 5.4 OSS 下载服务（阿里云 OSS）

```python
import oss2
from io import BytesIO
import pandas as pd
from typing import Optional

class OSSService:
    """阿里云 OSS 文件下载服务"""

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str
    ):
        """
        初始化 OSS 客户端

        endpoint: OSS 地域节点，如 oss-cn-hangzhou.aliyuncs.com
        bucket_name: OSS Bucket 名称
        """
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, endpoint, bucket_name)

    def download_file(self, object_key: str) -> bytes:
        """
        从 OSS 下载文件

        object_key: OSS 对象键（文件路径）
        返回: 文件二进制内容
        """
        result = self.bucket.get_object(object_key)
        return result.read()

    def download_from_url(self, url: str) -> bytes:
        """
        从完整 OSS URL 下载文件

        url: 完整的 OSS URL，如
            https://bucket-name.oss-cn-hangzhou.aliyuncs.com/path/to/file.xlsx
        返回: 文件二进制内容
        """
        # 从 URL 提取 object_key
        object_key = self._extract_object_key(url)
        return self.download_file(object_key)

    def parse_attachment(
        self,
        url: str,
        mime_type: str
    ) -> dict:
        """
        解析 OSS 附件内容

        支持格式:
        - .xlsx, .xls (Excel)
        - .csv (CSV)
        - .txt (文本)
        - .pdf (PDF，需要额外库)

        返回: 解析后的结构化数据
        """
        content = self.download_from_url(url)

        if mime_type.endswith("spreadsheetml.sheet") or mime_type.endswith("ms-excel"):
            # 解析 Excel
            return self._parse_excel(content)
        elif mime_type == "text/csv":
            # 解析 CSV
            return self._parse_csv(content)
        elif mime_type == "text/plain":
            # 文本文件
            return {"raw": content.decode("utf-8")}
        elif mime_type == "application/pdf":
            # PDF 解析（需要 PyPDF2 或 pdfplumber）
            return self._parse_pdf(content)
        else:
            return {"raw": content.decode("utf-8", errors="ignore")}

    def _extract_object_key(self, url: str) -> str:
        """
        从完整 OSS URL 提取 object_key

        示例:
        https://my-bucket.oss-cn-hangzhou.aliyuncs.com/uploads/2025/file.xlsx
        -> uploads/2025/file.xlsx
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # 去掉开头的 /
        return parsed.path.lstrip("/")

    def _parse_excel(self, content: bytes) -> dict:
        """解析 Excel 文件"""
        bio = BytesIO(content)
        df = pd.read_excel(bio, engine="openpyxl")
        return {
            "columns": df.columns.tolist(),
            "rows": df.values.tolist(),
            "row_count": len(df),
            "preview": df.head(10).to_dict(orient="records")  # 预览前10行
        }

    def _parse_csv(self, content: bytes) -> dict:
        """解析 CSV 文件"""
        bio = BytesIO(content)
        df = pd.read_csv(bio)
        return {
            "columns": df.columns.tolist(),
            "rows": df.values.tolist(),
            "row_count": len(df),
            "preview": df.head(10).to_dict(orient="records")
        }

    def _parse_pdf(self, content: bytes) -> dict:
        """解析 PDF 文件（需要额外库）"""
        # 可选实现：使用 PyPDF2 或 pdfplumber
        # import pdfplumber
        # with pdfplumber.open(BytesIO(content)) as pdf:
        #     text = "\n".join([page.extract_text() for page in pdf.pages])
        #     return {"text": text}
        return {"error": "PDF parsing not implemented yet"}

    def check_file_exists(self, object_key: str) -> bool:
        """检查文件是否存在"""
        return self.bucket.object_exists(object_key)

    def get_file_meta(self, object_key: str) -> dict:
        """获取文件元信息"""
        meta = self.bucket.get_object_meta(object_key)
        return {
            "content_length": meta.headers.get("Content-Length"),
            "content_type": meta.headers.get("Content-Type"),
            "etag": meta.headers.get("ETag"),
            "last_modified": meta.headers.get("Last-Modified")
        }
```

### 5.5 邮件服务

```python
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class EmailService:
    """邮件发送服务"""

    def __init__(self, smtp_config: dict):
        self.config = smtp_config

    async def send_query_result_email(
        self,
        to_emails: list,
        task_id: str,
        ticket_id: str,
        sql: str,
        result_data: dict,
        excel_file: bytes
    ):
        """
        发送查询结果邮件

        包含:
        - 查询 SQL
        - 结果摘要
        - Excel 附件
        """
        subject = f"【工单查询结果】{ticket_id}"

        html_body = f"""
        <h3>工单查询结果</h3>
        <p><strong>任务 ID:</strong> {task_id}</p>
        <p><strong>工单编号:</strong> {ticket_id}</p>

        <h4>执行的 SQL:</h4>
        <pre style="background: #f5f5f5; padding: 10px; border-radius: 5px;">
        {sql}
        </pre>

        <h4>结果摘要:</h4>
        <p>查询返回 {result_data['row_count']} 行数据，详情见附件 Excel。</p>

        <hr>
        <p style="color: #888; font-size: 12px;">
        本邮件由工单智能处理助手自动生成
        </p>
        """

        await self._send_email_with_attachment(
            to_emails,
            subject,
            html_body,
            "查询结果.xlsx",
            excel_file
        )

    async def send_dml_review_email(
        self,
        to_emails: list,
        cc_emails: list,
        task_id: str,
        ticket_id: str,
        dml_info: dict
    ):
        """
        发送 DML 审核邮件

        包含:
        - SQL 语句（语法高亮）
        - 影响范围
        - 风险评估
        """
        subject = f"【工单 DML 待执行】{ticket_id}"

        html_body = f"""
        <h3>工单 DML 待执行</h3>
        <p><strong>任务 ID:</strong> {task_id}</p>
        <p><strong>工单编号:</strong> {ticket_id}</p>

        <h4>待执行的 SQL:</h4>
        <pre style="background: #f5f5f5; padding: 10px; border-radius: 5px;">
        {self._highlight_sql(dml_info['sql'])}
        </pre>

        <h4>影响范围:</h4>
        <ul>
            <li>影响表: {', '.join(dml_info['affected_tables'])}</li>
            <li>预计影响行数: {dml_info.get('estimated_rows', '未知')}</li>
            <li>风险等级: <span style="color: {self._get_risk_color(dml_info['risk_level'])}">{dml_info['risk_level']}</span></li>
        </ul>

        <h4>操作说明:</h4>
        <p>{dml_info.get('description', '')}</p>

        <hr>
        <p style="color: #888; font-size: 12px;">
        本邮件由工单智能处理助手自动生成，请运维人员审核后执行
        </p>
        """

        await self._send_email(to_emails, subject, html_body, cc_emails)

    def _highlight_sql(self, sql: str) -> str:
        """SQL 语法高亮（简单实现）"""
        keywords = ["SELECT", "FROM", "WHERE", "UPDATE", "SET", "INSERT", "DELETE"]
        highlighted = sql
        for kw in keywords:
            highlighted = highlighted.replace(
                kw,
                f'<span style="color: #0066cc; font-weight: bold;">{kw}</span>'
            )
        return highlighted

    def _get_risk_color(self, risk_level: str) -> str:
        """获取风险等级颜色"""
        colors = {
            "low": "#28a745",
            "medium": "#ffc107",
            "high": "#dc3545"
        }
        return colors.get(risk_level, "#6c757d")
```

## 6. 配置管理

### 6.1 pyproject.toml

```toml
[project]
name = "work-order-assistant"
version = "1.0.0"
description = "智能工单处理助手系统 - 基于 LangGraph 的异步邮件通知系统"
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
requires-python = ">=3.10"
dependencies = [
    # FastAPI 核心
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-multipart>=0.0.6",

    # LangChain 生态（固定版本）
    "langchain==0.2.16",
    "langchain-core==0.2.38",
    "langchain-community==0.2.16",
    "langchain-openai==0.1.23",
    "langgraph>=0.2.0",

    # MCP 协议
    "mcp>=0.1.0",

    # 异步任务
    "celery>=5.3.0",  # 可选，如果使用 Celery
    "redis>=5.0.0",   # 可选，Celery broker

    # 阿里云 OSS
    "oss2>=2.18.0",

    # 邮件发送
    "aiosmtplib>=3.0.0",

    # Excel 处理
    "openpyxl>=3.1.0",
    "pandas>=2.1.0",

    # 工具库
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "black>=23.11.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.black]
line-length = 100
target-version = ['py310']

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### 6.2 环境变量配置

```bash
# .env.example

# ============ 应用配置 ============
APP_NAME=work-order-assistant
APP_VERSION=1.0.0
APP_ENV=production
API_KEY=your-secret-api-key

# 服务端口
HOST=0.0.0.0
PORT=8000

# ============ LLM 配置 ============
LLM_PROVIDER=openai  # openai | azure | anthropic
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# ============ 数据库配置 ============
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_NAME=workorder
DATABASE_USER=admin
DATABASE_PASSWORD=password

# ============ 阿里云 OSS 配置 ============
# OSS AccessKey ID 和 Secret
ALIYUN_OSS_ACCESS_KEY_ID=LTAI5t***
ALIYUN_OSS_ACCESS_KEY_SECRET=your-secret-key

# OSS Endpoint（地域节点）
# 杭州: oss-cn-hangzhou.aliyuncs.com
# 北京: oss-cn-beijing.aliyuncs.com
# 上海: oss-cn-shanghai.aliyuncs.com
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com

# OSS Bucket 名称
ALIYUN_OSS_BUCKET_NAME=work-order-attachments

# OSS 附件下载超时时间（秒）
OSS_DOWNLOAD_TIMEOUT=30
# OSS 附件最大大小（MB）
OSS_MAX_FILE_SIZE=50

# ============ 邮件配置 ============
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=noreply@example.com
SMTP_PASSWORD=smtp-password
SMTP_FROM=noreply@example.com

# 邮件接收人配置
# 运维/DBA 邮箱（接收 DML 审核邮件）
EMAIL_OPS_TEAM=ops@example.com,dba@example.com
# 开发团队邮箱（抄送）
EMAIL_DEV_TEAM=dev-lead@example.com

# ============ 异步任务配置 ============
# 使用 Celery（可选）
USE_CELERY=false
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# ============ 日志配置 ============
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
LOG_FORMAT=json  # json | text

# ============ 工作流配置 ============
# LangGraph 状态持久化（可选）
LANGGRAPH_CHECKPOINTER=memory  # memory | sqlite | postgres
LANGGRAPH_DB_PATH=data/checkpoints.db
```

## 7. 安全性考虑

### 7.1 SQL 注入防护

- 所有 SQL 语句使用参数化查询
- MCP 工具层面进行语法校验
- 禁止执行 DDL、DCL 语句

### 7.2 权限控制

- API 密钥认证
- 工单操作审计日志
- 变更操作强制人工审核

### 7.3 数据隐私

- 敏感字段脱敏
- 查询结果行数限制
- 附件内容扫描

## 8. 部署方案

### 8.1 Docker 部署

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install -e .

COPY src/ ./src/
COPY prompts/ ./prompts/

CMD ["uvicorn", "work_order_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: work-order-assistant
spec:
  replicas: 3
  selector:
    matchLabels:
      app: work-order-assistant
  template:
    metadata:
      labels:
        app: work-order-assistant
    spec:
      containers:
      - name: api
        image: work-order-assistant:1.0.0
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: work-order-config
        - secretRef:
            name: work-order-secrets
```

## 9. 监控与日志

### 9.1 关键指标

- 工单处理成功率
- 平均处理时长
- LLM Token 消耗
- MCP 工具调用次数

### 9.2 日志规范

```python
# 示例日志输出
{
  "timestamp": "2025-10-10T10:30:00Z",
  "level": "INFO",
  "task_id": "task-uuid-12345",
  "user": "user@example.com",
  "operation": "query",
  "status": "success",
  "duration_ms": 1250
}
```

## 10. 扩展性设计

### 10.1 新增业务场景

1. 在 `prompts/` 下创建新的提示词文件
2. 在 `PromptService` 中注册新场景
3. 无需修改核心 LangGraph 工作流代码

### 10.2 新增工作流节点

```python
# 在 workflows/nodes/ 下创建新节点
def custom_processing_node(state: WorkOrderState):
    """自定义处理节点"""
    # 实现节点逻辑
    return {"custom_result": "..."}

# 在工作流中添加节点
workflow.add_node("custom_processing", custom_processing_node)
workflow.add_edge("entity_extraction", "custom_processing")
```

### 10.3 支持多模态输入

- **图片识别**：工单截图 → OCR 提取文本 → LLM 理解
- **PDF 解析**：需求文档 → 提取文本和表格 → 结构化
- **Excel 解析**：数据清单 → Pandas 解析 → 批量处理

## 11. 开发路线图

### Phase 1: MVP (2 周)
- [ ] 基础架构搭建
  - [ ] 项目脚手架（pyproject.toml）
  - [ ] 配置管理（config.py）
  - [ ] 日志系统（logger.py）
- [ ] FastAPI 接口实现
  - [ ] 工单提交接口（异步响应）
  - [ ] 状态查询接口
  - [ ] 健康检查接口
- [ ] LangGraph 工作流核心
  - [ ] 意图识别节点
  - [ ] 实体提取节点
  - [ ] 条件分支逻辑
- [ ] 基础提示词模板
  - [ ] intent_recognition.txt
  - [ ] general_query.txt
  - [ ] general_mutation.txt

### Phase 2: 核心功能 (3 周)
- [ ] MCP 查询集成
  - [ ] MCP 客户端封装
  - [ ] SQL 验证器
  - [ ] 查询结果处理
- [ ] DML 生成功能
  - [ ] SQL 生成提示词
  - [ ] 风险评估逻辑
  - [ ] 影响范围分析
- [ ] 邮件推送服务
  - [ ] 查询结果邮件（Excel 附件）
  - [ ] DML 审核邮件（HTML 模板）
  - [ ] 邮件模板管理
- [ ] OSS 附件处理
  - [ ] 文件下载
  - [ ] Excel/CSV/PDF 解析
- [ ] 异步任务队列
  - [ ] asyncio.create_task 实现
  - [ ] 可选 Celery 支持

### Phase 3: 增强功能 (2 周)
- [ ] 完整提示词库
  - [ ] 用户查询、订单查询、日志查询
  - [ ] 数据更新、插入、删除
- [ ] 状态持久化
  - [ ] LangGraph Checkpointer
  - [ ] 任务状态跟踪
- [ ] 错误处理机制
  - [ ] 节点失败重试
  - [ ] 错误邮件通知
- [ ] 审计日志
  - [ ] 工单处理记录
  - [ ] SQL 执行审计

### Phase 4: 优化与上线 (1 周)
- [ ] 性能优化
  - [ ] LLM 响应缓存
  - [ ] 提示词优化
  - [ ] 并发控制
- [ ] 安全加固
  - [ ] API 认证
  - [ ] SQL 注入防护
  - [ ] 附件扫描
- [ ] 文档完善
  - [ ] API 文档（OpenAPI）
  - [ ] 部署文档
  - [ ] 运维手册
- [ ] 生产部署
  - [ ] Docker 镜像
  - [ ] K8s 配置
  - [ ] 监控告警

## 12. 参考资料

- [LangChain 官方文档](https://python.langchain.com/docs/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [Pydantic 文档](https://docs.pydantic.dev/)

## 13. 总结

### 核心优势

1. **异步处理架构**：接口立即返回，后台异步处理，提升响应速度
2. **LangGraph 工作流**：清晰的状态机模型，易于理解和维护
3. **智能邮件通知**：自动将处理结果发送给相关人员，无需人工干预
4. **提示词工程**：针对不同场景的专用提示词，提升准确性
5. **安全可控**：查询自动执行，变更需人工审核

### 技术亮点

- 使用 LangGraph 而非传统 Agent，流程控制更清晰
- OSS 附件下载和解析，支持多种文件格式
- Excel 附件生成查询结果，便于查看
- HTML 邮件模板，SQL 语法高亮
- 支持状态持久化和错误恢复

### 下一步行动

按照开发路线图逐步实施：
1. 搭建基础架构和 FastAPI 接口
2. 实现 LangGraph 核心工作流
3. 集成 MCP、邮件、OSS 服务
4. 完善提示词库和错误处理
5. 测试、优化、上线
