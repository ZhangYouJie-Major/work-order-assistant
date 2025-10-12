# DML 多步骤查询功能 - 使用指南

## 概述

本优化实现了 **Mutation 分支的多步骤 SQL 查询 + 动态 DML 拼装**能力，解决了原架构无法支持复杂变更操作（如"取消海运单"需要先查询关联数据）的问题。

## 架构变化

### 原架构（问题）
```
entity_extraction → generate_dml
                        ↓
                    (直接生成DML，无法查询数据库)
```

### 新架构（优化后）
```
entity_extraction → multi_step_query → generate_dml
                        ↓                    ↓
                (多轮查询获取数据)    (基于查询结果拼装DML)
```

## 核心组件

### 1. 多步骤查询引擎 (`multi_step_query_node`)
- 位置: `src/work_order_assistant/workflows/nodes/multi_step_query.py`
- 功能:
  - 按步骤顺序执行多轮 SQL 查询
  - 支持步骤间数据传递（变量替换）
  - 累积查询结果供 DML 生成使用

### 2. 配置加载服务 (`MutationStepsService`)
- 位置: `src/work_order_assistant/services/mutation_steps_service.py`
- 功能:
  - 加载工单类型对应的查询步骤配置
  - 验证配置格式
  - 提取 DML 生成步骤

### 3. DML 生成节点 (`generate_dml_node`) - 已升级
- 位置: `src/work_order_assistant/workflows/nodes/generate_dml.py`
- 功能:
  - **模式1**: 基于查询步骤配置 + 查询结果生成 DML
  - **模式2**: 回退到 LLM 生成（无配置时）
  - 支持 UPDATE/DELETE/INSERT 三种 DML 类型

### 4. 工作流编排 - 已更新
- 位置: `src/work_order_assistant/workflows/work_order_workflow.py`
- 变化: Mutation 路径插入 `multi_step_query` 节点

## 配置文件格式

### 配置目录
```
configs/mutation_steps/
  ├── schema.json                    # JSON Schema 定义
  ├── cancel_marine_order.json       # 取消海运单
  ├── update_quotation.json          # 修改报价单
  └── delete_expired_records.json    # 删除过期记录
```

### 配置示例：取消海运单

```json
{
  "work_order_type": "cancel_marine_order",
  "description": "取消海运单 - 根据入库单号查询并取消关联的海运单",
  "steps": [
    {
      "step": 1,
      "operation": "QUERY",
      "table": "t_receipt_order",
      "where": "receipt_order_no = {receipt_order_no}",
      "output_fields": ["marine_order_id", "receipt_order_no"]
    },
    {
      "step": 2,
      "operation": "QUERY",
      "table": "t_marine_order",
      "where": "id = {marine_order_id}",
      "output_fields": ["status", "id", "marine_order_no"]
    },
    {
      "step": 3,
      "operation": "GENERATE_DML",
      "type": "UPDATE",
      "table": "t_marine_order",
      "set": {
        "status": "CANCELLED",
        "updated_at": "NOW()",
        "cancel_reason": "{cancel_reason}"
      },
      "where": "id = {marine_order_id}"
    }
  ],
  "final_sql_template": "UPDATE t_marine_order SET status = 'CANCELLED', updated_at = NOW(), cancel_reason = ? WHERE id = ?"
}
```

## 执行流程示例

### 场景：用户提交"取消入库单号为 RO20250101 的海运单"

#### 步骤 1: 意图识别
- 识别为 `mutation` 类型

#### 步骤 2: 实体提取
- 提取实体:
  ```json
  {
    "receipt_order_no": "RO20250101",
    "work_order_subtype": "cancel_marine_order",
    "cancel_reason": "客户要求取消"
  }
  ```
- 加载配置: `configs/mutation_steps/cancel_marine_order.json`

#### 步骤 3: 多步骤查询 (`multi_step_query_node`)

**执行步骤 1: 查询入库单**
```sql
SELECT marine_order_id, receipt_order_no
FROM t_receipt_order
WHERE receipt_order_no = 'RO20250101'
```
结果:
```json
{
  "marine_order_id": "MO123456",
  "receipt_order_no": "RO20250101"
}
```

**执行步骤 2: 查询海运单**
```sql
SELECT status, id, marine_order_no
FROM t_marine_order
WHERE id = 'MO123456'
```
结果:
```json
{
  "status": "ACTIVE",
  "id": "MO123456",
  "marine_order_no": "MRN2025010001"
}
```

**上下文累积**:
```json
{
  "receipt_order_no": "RO20250101",
  "marine_order_id": "MO123456",
  "status": "ACTIVE",
  "id": "MO123456",
  "marine_order_no": "MRN2025010001",
  "cancel_reason": "客户要求取消"
}
```

#### 步骤 4: 生成 DML (`generate_dml_node`)

基于配置的步骤 3 和上下文，生成:
```sql
UPDATE t_marine_order
SET status = 'CANCELLED',
    updated_at = NOW(),
    cancel_reason = '客户要求取消'
WHERE id = 'MO123456'
```

#### 步骤 5: 发送 DML 邮件
将生成的 DML 发送给 DBA 审核

## 变量替换机制

### 支持的变量格式
- `{variable_name}` - 自动从上下文中查找值
- 自动处理类型:
  - 字符串: 添加单引号并转义 (`'value'`)
  - 数字: 直接使用 (`123`)
  - 特殊函数: 保持原样 (`NOW()`, `NULL`)

### 示例
配置:
```json
{
  "set": {
    "status": "CANCELLED",
    "price": "{new_price}",
    "updated_at": "NOW()"
  }
}
```

上下文:
```json
{
  "new_price": 1999.99
}
```

生成结果:
```sql
SET status = 'CANCELLED', price = 1999.99, updated_at = NOW()
```

## 如何添加新的工单类型

### 步骤 1: 创建配置文件
在 `configs/mutation_steps/` 下创建 `your_type.json`:

```json
{
  "work_order_type": "your_type",
  "description": "你的工单类型描述",
  "steps": [
    {
      "step": 1,
      "operation": "QUERY",
      "table": "your_table",
      "where": "some_field = {some_value}",
      "output_fields": ["field1", "field2"]
    },
    {
      "step": 2,
      "operation": "GENERATE_DML",
      "type": "UPDATE",
      "table": "your_table",
      "set": {
        "field": "{new_value}"
      },
      "where": "id = {id}"
    }
  ]
}
```

### 步骤 2: 更新实体提取提示词
确保 LLM 能够识别并返回:
```json
{
  "work_order_subtype": "your_type",
  "some_value": "extracted_value"
}
```

### 步骤 3: 测试
提交测试工单，检查日志确认流程正确执行

## 关键设计决策

### 1. 为什么分离配置和代码？
- **灵活性**: 新增工单类型无需修改代码
- **可维护性**: 配置文件便于 DBA 审查
- **可测试性**: 可独立测试配置正确性

### 2. 为什么保留 LLM 回退？
- **渐进式迁移**: 旧工单类型可继续使用
- **兜底方案**: 配置不存在时不会失败
- **灵活应对**: 非标准场景由 LLM 处理

### 3. 为什么在节点间传递上下文？
- **步骤解耦**: 每步只关注自己的查询
- **数据传递**: 通过上下文自动传递结果
- **可扩展**: 支持任意长度的查询链

## 风险评估

系统会自动评估 DML 风险等级:

- **HIGH**: 无 WHERE 条件的 UPDATE/DELETE
- **MEDIUM**: 有条件的 DELETE
- **LOW**: 有条件的 UPDATE、所有 INSERT

风险等级会包含在发送给 DBA 的邮件中

## 文件清单

### 新增文件
- `src/work_order_assistant/workflows/nodes/multi_step_query.py`
- `src/work_order_assistant/services/mutation_steps_service.py`
- `configs/mutation_steps/schema.json`
- `configs/mutation_steps/cancel_marine_order.json`
- `configs/mutation_steps/update_quotation.json`
- `configs/mutation_steps/delete_expired_records.json`

### 修改文件
- `src/work_order_assistant/workflows/state.py` (新增字段)
- `src/work_order_assistant/workflows/nodes/__init__.py` (导出新节点)
- `src/work_order_assistant/workflows/nodes/entity_extraction.py` (加载配置)
- `src/work_order_assistant/workflows/nodes/generate_dml.py` (双模式生成)
- `src/work_order_assistant/workflows/work_order_workflow.py` (更新流程)

## 日志跟踪

关键日志点:
1. `[{task_id}] Loading mutation steps config for: {work_order_subtype}`
2. `[{task_id}] Executing {N} query steps`
3. `[{task_id}] Step {N} SQL: {sql}`
4. `[{task_id}] Using multi-step query result to generate DML`
5. `[{task_id}] DML generated: {type} on {table}`

## 下一步优化建议

1. **配置验证工具**: 提供命令行工具验证配置格式
2. **可视化调试**: 输出步骤执行流程图
3. **配置热加载**: 支持运行时更新配置
4. **多表 DML**: 支持一次生成多个 DML 语句
5. **条件路由**: 根据查询结果动态选择后续步骤

## 常见问题

### Q: 如何调试配置不生效？
A: 检查日志中是否有 "No config found" 警告，确认 `work_order_subtype` 值与配置文件名匹配

### Q: 如何处理查询无结果的情况？
A: 系统会在日志中记录 "Query returned no rows"，后续步骤会因缺少变量而保持原模板

### Q: 是否支持事务？
A: 当前仅生成 DML，不执行。执行权限在 DBA，可手动包装事务

### Q: 如何支持复杂 WHERE 条件？
A: 在配置中使用标准 SQL 语法，支持 AND/OR/IN 等操作符

---

**作者备注**: 此架构设计遵循"配置驱动 + 代码通用"的原则，实现了 Mutation 路径的灵活扩展能力。
