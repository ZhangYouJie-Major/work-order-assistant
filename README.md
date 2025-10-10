# 工单智能处理助手系统

基于 LangGraph 和 MCP (Model Context Protocol) 的智能工单处理系统，接收审批流系统的工单请求，通过 LLM 理解工单内容，自动识别操作类型（查询/变更），执行相应操作后通过邮件将结果发送给运维人员。

## 核心特性

- ✅ **异步处理架构**：接口立即返回，后台异步处理，提升响应速度
- ✅ **LangGraph 工作流**：清晰的状态机模型，易于理解和维护
- ✅ **智能邮件通知**：自动将处理结果发送给相关人员
- ✅ **提示词工程**：针对不同场景的专用提示词，提升准确性
- ✅ **安全可控**：查询自动执行，变更需人工审核

## 技术栈

- **FastAPI**: 异步 Web 框架
- **LangGraph**: 工作流编排引擎
- **LangChain**: LLM 集成
- **MCP**: Model Context Protocol
- **阿里云 OSS**: 附件存储
- **SMTP**: 邮件发送

## 快速开始

### 1. 安装依赖

```bash
# 安装项目依赖
pip install -e .

# 或使用开发依赖
pip install -e ".[dev]"
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写必要的配置：

```bash
# LLM 配置
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# MCP 配置
MCP_SERVER_URL=http://mcp-server:3000
MCP_API_KEY=mcp-secret-key

# 阿里云 OSS 配置
ALIYUN_OSS_ACCESS_KEY_ID=your-access-key-id
ALIYUN_OSS_ACCESS_KEY_SECRET=your-secret-key
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET_NAME=work-order-attachments

# 邮件配置
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=noreply@example.com
SMTP_PASSWORD=smtp-password
SMTP_FROM=noreply@example.com
EMAIL_OPS_TEAM=ops@example.com,dba@example.com
```

### 3. 启动服务

```bash
# 开发模式
python -m work_order_assistant.main

# 或使用 uvicorn
uvicorn work_order_assistant.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问 API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 使用示例

### 提交工单

```bash
curl -X POST "http://localhost:8000/api/v1/work-order/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "查询用户 ID 为 12345 的订单信息，最近 7 天的，包括订单金额、状态和创建时间",
    "oss_attachments": [],
    "cc_emails": ["user@example.com"],
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
  }'
```

### 查询工单状态

```bash
curl -X GET "http://localhost:8000/api/v1/work-order/{task_id}"
```

### 健康检查

```bash
curl -X GET "http://localhost:8000/health"
```

## 项目结构

```
work-order-assistant/
├── src/work_order_assistant/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置管理
│   ├── api/                       # API 层
│   │   ├── routes/                # 路由
│   │   └── schemas/               # 请求/响应模型
│   ├── workflows/                 # LangGraph 工作流
│   │   ├── state.py               # 状态定义
│   │   ├── work_order_workflow.py # 工作流编排
│   │   └── nodes/                 # 工作流节点
│   ├── services/                  # 业务服务
│   │   ├── llm_service.py         # LLM 服务
│   │   ├── mcp_service.py         # MCP 服务
│   │   ├── oss_service.py         # OSS 服务
│   │   ├── email_service.py       # 邮件服务
│   │   └── prompt_service.py      # 提示词管理
│   ├── models/                    # 数据模型
│   └── utils/                     # 工具函数
├── prompts/                       # 提示词模板
│   ├── base/                      # 基础提示词
│   ├── query/                     # 查询类提示词
│   └── mutation/                  # 变更类提示词
├── pyproject.toml                 # 项目配置
├── .env.example                   # 环境变量示例
└── README.md                      # 本文件
```

## 工作流程

```
工单提交 → 意图识别 → 实体提取 → 条件分支
                                    ├─ 查询：MCP查询 → 发送查询结果邮件
                                    └─ 变更：生成DML → 发送DML审核邮件
```

## 提示词管理

系统支持针对不同场景使用不同的提示词模板：

- `base/intent_recognition.txt`: 意图识别
- `query/general_query.txt`: 通用查询提示词
- `mutation/general_mutation.txt`: 通用变更提示词

你可以在 `prompts/` 目录下添加更多针对特定业务场景的提示词。

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black src/
ruff check src/
```

### 类型检查

```bash
mypy src/
```

## 部署

### Docker 部署

```bash
docker build -t work-order-assistant .
docker run -p 8000:8000 --env-file .env work-order-assistant
```

### Kubernetes 部署

参考 DESIGN.md 中的 Kubernetes 配置示例。

## 许可证

MIT License

## 联系方式

如有问题，请提交 Issue 或联系开发团队。
