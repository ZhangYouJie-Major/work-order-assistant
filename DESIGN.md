# 工单智能处理助手系统设计文档

## 1. 系统概述

### 1.1 系统简介

基于 LangGraph 和 MCP (Model Context Protocol) 的智能工单处理系统，接收审批流系统的工单请求，通过 LLM 理解工单内容，自动识别操作类型（查询/变更），执行相应操作后通过邮件将结果（查询数据或 DML 语句）发送给运维人员。

### 1.2 核心定位

- **异步处理架构**：接口立即返回，后台异步处理并发送邮件通知
- **智能理解**：利用 LLM 理解非结构化工单内容
- **配置驱动**：通过 JSON 配置文件管理复杂的数据变更操作
- **安全可控**：查询自动执行，变更生成 DML 供人工审核

### 1.3 技术栈

- **后端框架**：FastAPI + Uvicorn
- **工作流引擎**：LangGraph（状态机编排）
- **大语言模型**：OpenAI GPT-4 / Azure OpenAI
- **数据库交互**：MCP (Model Context Protocol)
- **对象存储**：阿里云 OSS
- **邮件服务**：SMTP (aiosmtplib)
- **异步任务**：asyncio / Celery (可选)

## 2. 设计思路

### 2.1 核心理念

1. **异步处理**：接口立即返回，后台异步处理工单并发送邮件通知
2. **智能理解**：利用大模型的自然语言理解能力，从非结构化工单中提取结构化信息
3. **配置化变更管理**：通过 JSON 配置文件定义复杂的数据变更流程，支持条件分支和多步骤查询验证
4. **提示词工程**：针对不同业务场景维护专用提示词模板
5. **邮件通知**：将处理结果通过邮件发送给运维人员作为参考
6. **可扩展性**：基于 LangGraph 状态机架构，流程清晰易维护

### 2.2 处理流程

```
┌─────────────────────────────────────────────────────────┐
│                    审批流系统                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ POST /api/v1/work-order/submit
                       ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI 接口层（立即返回）                   │
│  {code: 0, task_id: "xxx", message: "已接收"}            │
└──────────────────────┬──────────────────────────────────┘
                       │ 投递到后台异步任务队列
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph 工作流引擎                     │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │  Node 1: 意图识别                           │         │
│  │  └─ 输出: query / mutation                │         │
│  └──────────────────┬─────────────────────────┘         │
│                     ▼                                    │
│  ┌────────────────────────────────────────────┐         │
│  │  Node 2: 实体提取 + 智能配置匹配            │         │
│  │  ├─ 提取目标表/条件/字段                   │         │
│  │  ├─ [mutation] LLM 智能匹配配置文件         │         │
│  │  └─ [mutation] 提取配置所需参数             │         │
│  └──────────────────┬─────────────────────────┘         │
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
│  │             │              │ ├─执行step1  │         │
│  │             │              │ ├─条件判断   │         │
│  │             │              │ └─上下文传递 │         │
│  └──────┬──────┘              └──────┬───────┘         │
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
│  │ 发送查询结果│              │ 发送DML邮件  │         │
│  │ ├─生成Excel │              │ ├─执行SQL    │         │
│  │ └─邮件抄送  │              │ ├─SQL模板    │         │
│  └─────────────┘              │ └─参数列表   │         │
│                               └──────────────┘         │
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

3. **状态持久化**
   - 可以保存每个节点的处理状态
   - 便于异步任务的暂停/恢复

4. **可视化调试**
   - LangGraph 可以导出流程图
   - 便于团队理解和维护

5. **错误恢复**
   - 某个节点失败可以重试
   - 不需要重新执行整个流程

## 3. 项目架构

### 3.1 目录结构

```
work-order-assistant/
├── pyproject.toml              # 项目配置和依赖管理
├── README.md                   # 项目说明
├── DESIGN.md                   # 本设计文档
├── .env.example                # 环境变量示例
│
├── src/
│   └── work_order_assistant/
│       ├── main.py             # FastAPI 应用入口
│       ├── config.py           # 配置管理
│       │
│       ├── api/                # API 层
│       │   ├── routes/
│       │   │   └── work_order.py    # 工单接口
│       │   └── schemas/
│       │       ├── request.py       # 请求模型
│       │       └── response.py      # 响应模型
│       │
│       ├── workflows/          # LangGraph 工作流
│       │   ├── work_order_workflow.py  # 主工作流
│       │   ├── nodes/
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
│       │   ├── llm_service.py          # LLM 服务
│       │   ├── oss_service.py          # OSS 下载服务
│       │   ├── prompt_service.py       # 提示词管理服务
│       │   ├── email_service.py        # 邮件服务
│       │   └── mutation_steps_service.py  # 配置服务（核心）
│       │
│       ├── tools/              # 工具层
│       │   └── sql_tool.py             # SQL 执行工具
│       │
│       └── utils/              # 工具函数
│           ├── logger.py               # 日志工具
│           ├── condition_evaluator.py  # 条件表达式求值器
│           └── excel_generator.py      # Excel 生成工具
│
├── resources/                  # 资源文件目录
│   ├── prompts/                # 提示词模板目录
│   │   ├── base/
│   │   │   ├── intent_recognition.txt      # 意图识别
│   │   │   └── entity_extraction.txt       # 实体提取
│   │   ├── query/
│   │   │   └── general_query.txt           # 通用查询
│   │   └── mutation/
│   │       └── general_mutation.txt        # 通用变更
│   │
│   └── configs/                # 配置文件目录
│       └── mutation_steps/     # 变更步骤配置（核心）
│           ├── schema.json                 # 配置文件 Schema
│           ├── update_telco_customer.json  # 更新电信客户示例
│           └── cancel_marine_order.json    # 取消海运单示例
│
└── tests/                      # 测试目录
```

### 3.2 技术架构

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
│  │  - asyncio.create_task / Celery                  │ │
│  └────────────┬─────────────────────────────────────┘ │
└───────────────┼─────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│             LangGraph Workflow Engine                  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │     Nodes (处理节点)                              │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 1. Intent Recognition (意图识别)          │   │ │
│  │  │    - LLM Service + Prompt Service        │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 2. Entity Extraction (实体提取)           │   │ │
│  │  │    - OSS Download + LLM Service          │   │ │
│  │  │    - 智能配置匹配 (mutation only)         │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 3a. SQL Query (查询执行)                  │   │ │
│  │  │     - MCP Client / SQL Tool              │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 3b. Multi-Step Query (多步骤查询)         │   │ │
│  │  │     - 条件分支 + 上下文传递               │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 3c. Generate DML (生成SQL)                │   │ │
│  │  │     - 基于配置 + 变量替换                 │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  │  ┌──────────────────────────────────────────┐   │ │
│  │  │ 4. Send Email (发送邮件)                  │   │ │
│  │  │    - Email Service + Excel Generator     │   │ │
│  │  └──────────────────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## 4. 核心设计

### 4.1 LangGraph 工作流设计

#### 4.1.1 状态定义

```python
from typing import TypedDict, Literal, Optional

class WorkOrderState(TypedDict):
    """工单处理状态"""
    # 输入
    task_id: str
    content: str
    oss_attachments: list
    cc_emails: list
    user: dict
    metadata: dict

    # 处理过程中的状态
    operation_type: Optional[Literal["query", "mutation"]]
    entities: Optional[dict]
    query_steps_config: Optional[dict]  # mutation 步骤配置
    query_steps_result: Optional[dict]  # 多步骤查询结果
    work_order_subtype: Optional[str]   # 工单子类型

    # 输出
    sql: Optional[str]
    query_result: Optional[dict]
    dml_info: Optional[dict]
    email_sent: Optional[bool]
    error: Optional[str]
```

#### 4.1.2 工作流构建

```python
from langgraph.graph import StateGraph, END

def create_work_order_workflow():
    workflow = StateGraph(WorkOrderState)

    # 添加节点
    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("entity_extraction", entity_extraction_node)
    workflow.add_node("sql_query", sql_query_node)
    workflow.add_node("multi_step_query", multi_step_query_node)
    workflow.add_node("generate_dml", generate_dml_node)
    workflow.add_node("send_query_email", send_query_email_node)
    workflow.add_node("send_dml_email", send_dml_email_node)

    # 设置入口
    workflow.set_entry_point("intent_recognition")

    # 意图识别 → 实体提取
    workflow.add_edge("intent_recognition", "entity_extraction")

    # 实体提取 → 条件分支（查询/变更）
    workflow.add_conditional_edges(
        "entity_extraction",
        lambda state: state.get("operation_type", "unknown"),
        {
            "query": "sql_query",
            "mutation": "multi_step_query",
            "unknown": END
        }
    )

    # 查询路径：SQL查询 → 发送查询邮件 → 结束
    workflow.add_edge("sql_query", "send_query_email")
    workflow.add_edge("send_query_email", END)

    # 变更路径：多步骤查询 → 生成DML → 发送DML邮件 → 结束
    workflow.add_edge("multi_step_query", "generate_dml")
    workflow.add_edge("generate_dml", "send_dml_email")
    workflow.add_edge("send_dml_email", END)

    return workflow.compile()
```

### 4.2 配置化变更管理（核心创新）

这是本系统的**核心创新点**，通过配置化的方式管理不同类型的数据变更操作。

#### 4.2.1 配置文件格式

**简单示例：更新操作**

```json
{
  "work_order_type": "update_telco_customer",
  "description": "电信客户数据表-根据客户唯一标识ID更新月费金额。入参的customerID是客户id，new_price是月费金额",
  "steps": [
    {
      "step": 1,
      "operation": "QUERY",
      "table": "telco_customer",
      "where": "customerID = {customerID}",
      "output_fields": ["customerID"]
    },
    {
      "step": 2,
      "operation": "GENERATE_DML",
      "type": "UPDATE",
      "table": "telco_customer",
      "set": {"MonthlyCharges": "{new_price}"},
      "where": "customerID = {customerID}"
    }
  ],
  "final_sql_template": "UPDATE telco_customer SET MonthlyCharges = ? WHERE customerID = ?"
}
```

**高级示例：支持条件分支**

```json
{
  "work_order_type": "cancel_marine_order",
  "description": "取消海运单 - 根据入库单号查询并取消关联的海运单",
  "steps": [
    {
      "step": 1,
      "operation": "QUERY",
      "table": "t_receipt_order",
      "where": "receipt_order_number = {receipt_order_number}",
      "output_fields": ["marine_order_id"],
      "on_success": {
        "condition": "{marine_order_id} != null",
        "next_step": 2,
        "else_step": 10
      },
      "on_failure": {
        "next_step": 11
      }
    },
    {
      "step": 2,
      "operation": "QUERY",
      "table": "r_electronic_container_order",
      "where": "marine_order_id = {marine_order_id}",
      "output_fields": ["id", "status"],
      "on_success": {
        "condition": "{id} != null",
        "next_step": 3,
        "else_step": 4
      }
    },
    {
      "step": 3,
      "operation": "GENERATE_DML",
      "type": "UPDATE",
      "table": "r_electronic_container_order",
      "set": {"status": "1"},
      "where": "id = {id}",
      "next_step": 4
    },
    {
      "step": 4,
      "operation": "GENERATE_DML",
      "type": "INSERT",
      "table": "t_check_status_change",
      "values": {
        "order_id": "{marine_order_id}",
        "status": "16",
        "status_type": "1",
        "create_by": "系统运维"
      },
      "next_step": 5
    },
    {
      "step": 5,
      "operation": "GENERATE_DML",
      "type": "UPDATE",
      "table": "t_marine_order",
      "set": {"status": "16"},
      "where": "marine_order_id = {marine_order_id}",
      "next_step": null
    },
    {
      "step": 10,
      "operation": "RETURN_ERROR",
      "message": "入库单未关联海运单，入库单号: {receipt_order_number}",
      "next_step": null
    },
    {
      "step": 11,
      "operation": "RETURN_ERROR",
      "message": "未找到入库单，入库单号: {receipt_order_number}",
      "next_step": null
    }
  ]
}
```

#### 4.2.2 配置文件支持的特性

1. **条件分支**
   - `on_success.condition`: 条件表达式（比较、成员、逻辑运算）
   - `on_success.next_step`: 条件为真时跳转
   - `on_success.else_step`: 条件为假时跳转
   - `on_failure.next_step`: 查询失败时跳转

2. **条件表达式示例**
   ```python
   "{status} == '10'"                          # 比较运算
   "{marine_order_id} != null"                 # 空值判断
   "{status} in ['10', '11', '12']"           # 成员运算
   "{amount} > 1000 and {vip_level} >= 3"     # 复合逻辑
   ```

3. **操作类型**
   - `QUERY`: 执行查询，将结果存入上下文
   - `GENERATE_DML`: 生成 DML 语句（UPDATE/INSERT/DELETE）
   - `RETURN_SUCCESS`: 返回成功，终止流程
   - `RETURN_ERROR`: 返回错误，附带错误信息

4. **流程控制**
   - 支持非顺序跳转（可跳转到任意步骤）
   - 支持多 DML 语句生成
   - 最大迭代次数保护（100次）

#### 4.2.3 智能配置匹配

**MutationStepsService 核心功能：**

```python
async def match_config_by_content(
    self,
    work_order_content: str,
    llm_service: Any
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    智能匹配配置文件

    1. 加载所有配置文件的 description
    2. 使用 LLM 根据工单内容匹配最合适的配置
    3. 返回匹配的配置类型和完整配置
    """
    configs = self.load_all_configs()

    # 构建 LLM 提示词
    descriptions = []
    for idx, cfg in enumerate(configs):
        descriptions.append(
            f"{idx + 1}. {cfg['work_order_type']}: {cfg['description']}"
        )

    prompt = f"""根据工单内容，选择最匹配的配置。

工单内容：
{work_order_content}

可选配置：
{chr(10).join(descriptions)}

输出 JSON：
{{
    "matched_index": 匹配的配置序号（1-{len(configs)}），
    "confidence": 置信度（0.0-1.0）,
    "reasoning": "匹配理由"
}}
"""

    # 调用 LLM
    result = await llm_service.llm.ainvoke([HumanMessage(content=prompt)])
    matched_data = json.loads(result.content)

    if matched_data["confidence"] >= 0.7:
        matched_config = configs[matched_data["matched_index"] - 1]
        return (matched_config["work_order_type"], matched_config["config"])

    return None
```

#### 4.2.4 工作流程

1. **意图识别** → mutation
2. **智能配置匹配**
   - LLM 根据工单内容分析匹配最佳配置
   - 置信度 >= 0.7 则使用该配置
3. **参数提取**
   - 根据配置的 description 提取所需参数
4. **多步骤查询（支持条件分支）**
   - 从步骤1开始执行，根据配置动态跳转
   - 执行 QUERY 操作，将结果存入上下文
   - 根据 `on_success.condition` 条件判断下一步
   - 支持 `on_failure` 分支处理查询失败
5. **DML 生成**
   - 基于配置的 GENERATE_DML 步骤
   - 替换变量占位符
   - 生成完整的 SQL 语句
6. **输出 DML**
   - 执行 SQL（带实际值）
   - SQL 模板（参数化查询）
   - 参数列表

#### 4.2.5 条件表达式求值器

新增 `ConditionEvaluator` 工具类，用于安全地求值条件表达式：

```python
from work_order_assistant.utils.condition_evaluator import evaluate_condition

# 示例用法
context = {
    "status": "10",
    "marine_order_id": "12345",
    "amount": 1500,
    "vip_level": 5
}

# 比较运算
evaluate_condition("{status} == '10'", context)  # True

# 空值判断
evaluate_condition("{marine_order_id} != null", context)  # True

# 成员运算
evaluate_condition("{status} in ['10', '11', '12']", context)  # True

# 复合逻辑
evaluate_condition("{amount} > 1000 and {vip_level} >= 3", context)  # True
```

**安全特性：**
- 禁止执行危险代码（import、exec、eval等）
- 受限的命名空间，只允许基本运算
- 自动变量替换和类型转换

### 4.3 接口设计

#### 4.3.1 工单提交接口

**接口路径**: `POST /api/v1/work-order/submit`

**请求体示例**:
```json
{
  "content": "查询用户 ID 为 12345 的订单信息",
  "oss_attachments": [
    {
      "filename": "requirement.xlsx",
      "url": "https://oss.example.com/uploads/file.xlsx",
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
  ],
  "cc_emails": ["user@example.com", "manager@example.com"],
  "user": {
    "email": "user@example.com",
    "name": "张三",
    "department": "运营部"
  },
  "metadata": {
    "ticket_id": "WO-2025-001",
    "priority": "medium"
  }
}
```

**成功响应（立即返回）**:
```json
{
  "code": 0,
  "message": "工单已接收，将异步处理并发送邮件通知",
  "data": {
    "task_id": "task-20251010-uuid-12345",
    "status": "accepted",
    "estimated_time": "预计 30-60 秒内完成处理",
    "notify_emails": ["user@example.com", "manager@example.com"],
    "created_at": "2025-10-10T10:30:00Z"
  }
}
```

#### 4.3.2 工单状态查询接口

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
    "email_sent": true,
    "completed_at": "2025-10-10T10:30:45Z"
  }
}
```

#### 4.3.3 邮件发送逻辑

1. **查询操作**:
   - 通过 MCP 执行查询获取数据
   - 将查询结果生成 Excel 附件
   - 发送邮件到 `cc_emails` 列表
   - 邮件标题：`【工单查询结果】{ticket_id}`
   - 邮件内容：查询 SQL、结果摘要、Excel 附件

2. **变更操作**:
   - 生成规范的 DML 语句
   - 发送邮件到运维/开发邮箱
   - 抄送到 `cc_emails` 列表
   - 邮件标题：`【工单 DML 待执行】{ticket_id}`
   - 邮件内容：SQL 语句（语法高亮）、影响范围、风险评估

### 4.4 DML 输出格式

```
============================================================
生成的 DML 语句
============================================================
操作类型: UPDATE
涉及表: ['telco_customer']
风险级别: low
------------------------------------------------------------
【执行 SQL】:
  UPDATE telco_customer SET MonthlyCharges = '80' WHERE customerID = '0002-ORFBO'
------------------------------------------------------------
【SQL 模板】(使用参数化查询):
  UPDATE telco_customer SET MonthlyCharges = ? WHERE customerID = ?
【参数】:
  customerID = 0002-ORFBO
  new_price = 80
------------------------------------------------------------
说明: UPDATE telco_customer
============================================================
```

## 5. 参考资料

- [LangChain 官方文档](https://python.langchain.com/docs/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [阿里云 OSS Python SDK](https://help.aliyun.com/document_detail/32026.html)

## 6. 总结

### 6.1 核心优势

1. **异步处理架构**：接口立即返回，后台异步处理，提升响应速度
2. **LangGraph 工作流**：清晰的状态机模型，易于理解和维护
3. **配置化变更管理**：通过 JSON 配置文件管理不同类型的数据变更操作
4. **智能配置匹配**：LLM 自动匹配最佳配置，无需人工指定工单类型
5. **条件分支流程控制**：类似轻量级 BPM，支持复杂业务逻辑和错误处理
6. **多步骤查询验证**：支持条件分支、非顺序跳转，确保变更安全性
7. **安全可控**：查询自动执行，变更生成 DML 供人工审核

### 6.2 技术亮点

#### 核心创新：配置化流程引擎

- **配置文件驱动**
  - 每种变更类型一个配置文件（JSON 格式）
  - 包含：description、查询步骤、DML 模板、条件分支
  - LLM 智能匹配 + 参数自动提取

- **条件分支支持**
  - 支持条件判断（`on_success`/`on_failure`）
  - 支持非顺序跳转（可跳转到任意步骤）
  - 支持多 DML 语句生成（INSERT + UPDATE）
  - 安全的条件表达式求值器

- **流程引擎特性**
  - 类似轻量级的业务流程引擎（BPM）
  - 配置即流程图，易于理解和维护
  - 支持复杂业务逻辑（VIP客户快速通道等）
  - 最大迭代次数保护，防止死循环

#### 其他特性

- **简化的日志格式**：只保留核心字段（time, lvl, msg），提升可读性
- **完整的 DML 输出**：执行 SQL、SQL 模板、参数列表，便于审核和执行
- **OSS 附件支持**：支持 Excel、CSV、PDF 等多种格式解析
- **邮件通知**：查询结果 Excel 附件、DML 语法高亮
- **状态持久化**：支持任务状态跟踪和错误恢复

### 6.3 创新点总结

1. **配置驱动的变更管理**
   - 不再依赖复杂的提示词工程
   - 配置文件即文档，易于维护
   - 新增变更类型只需添加 JSON 配置

2. **LLM 智能匹配机制**
   - 根据工单内容自动匹配配置
   - 自动提取配置所需参数
   - 置信度控制，确保准确性

3. **条件分支流程引擎**
   - 类似轻量级的业务流程引擎（BPM）
   - 支持条件判断、非顺序跳转、错误处理
   - 支持复杂业务逻辑（VIP客户快速通道等）
   - 配置即流程图，易于理解和维护
   - 安全的表达式求值，防止代码注入

4. **多步骤查询验证**
   - 执行前先查询验证数据
   - 步骤间上下文传递
   - 支持复杂的业务逻辑

---

**文档版本**: v1.0
**最后更新**: 2025-10-25
