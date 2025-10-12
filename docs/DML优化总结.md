# DML 分支功能优化总结

## 问题背景

原 Mutation 分支架构存在致命缺陷：**无法在生成 DML 之前查询数据库**，导致无法支持"取消海运单"（需要先查询入库单获取 marine_order_id）等常见业务场景。

## 解决方案

引入 **多步骤查询引擎 + 配置驱动的 DML 拼装** 机制：

```
原流程:  entity_extraction → generate_dml ❌
新流程:  entity_extraction → multi_step_query → generate_dml ✅
```

## 核心改进

### 1. 多步骤查询引擎 (`multi_step_query_node`)
- 支持按配置执行 N 轮 SQL 查询
- 步骤间自动传递数据（变量替换）
- 查询结果累积到上下文供 DML 使用

### 2. 配置驱动系统
- 每个工单类型一个 JSON 配置文件
- 定义查询步骤链和 DML 模板
- 无需修改代码即可新增类型

### 3. 智能 DML 生成
- **模式1**: 基于查询结果 + 配置模板拼装（精确）
- **模式2**: LLM 生成（回退兜底）
- 支持 UPDATE/DELETE/INSERT

## 示例：取消海运单

**用户输入**: "取消入库单号 RO20250101 的海运单"

**执行流程**:
1. 识别工单类型: `cancel_marine_order`
2. 加载配置: `configs/mutation_steps/cancel_marine_order.json`
3. 执行查询链:
   ```sql
   -- Step 1: 根据入库单号查询
   SELECT marine_order_id FROM t_receipt_order WHERE receipt_order_no = 'RO20250101'

   -- Step 2: 查询海运单当前状态
   SELECT status FROM t_marine_order WHERE id = 'MO123456'
   ```
4. 拼装 DML:
   ```sql
   UPDATE t_marine_order
   SET status = 'CANCELLED', updated_at = NOW()
   WHERE id = 'MO123456'
   ```

## 技术亮点

### 变量替换机制
配置中使用 `{variable_name}` 格式，自动从上下文替换：
- 字符串自动加引号转义: `{name}` → `'Alice'`
- 数字直接使用: `{price}` → `1999.99`
- 函数保持原样: `NOW()` → `NOW()`

### 风险评估
自动评估 DML 风险等级：
- `HIGH`: 无 WHERE 的 UPDATE/DELETE
- `MEDIUM`: 有条件的 DELETE
- `LOW`: 有条件的 UPDATE、INSERT

### 回退机制
配置不存在时自动回退到 LLM 生成，不会阻塞流程

## 文件清单

### 新增 (6个)
```
src/work_order_assistant/workflows/nodes/multi_step_query.py
src/work_order_assistant/services/mutation_steps_service.py
configs/mutation_steps/schema.json
configs/mutation_steps/cancel_marine_order.json
configs/mutation_steps/update_quotation.json
configs/mutation_steps/delete_expired_records.json
```

### 修改 (5个)
```
src/work_order_assistant/workflows/state.py
src/work_order_assistant/workflows/nodes/__init__.py
src/work_order_assistant/workflows/nodes/entity_extraction.py
src/work_order_assistant/workflows/nodes/generate_dml.py
src/work_order_assistant/workflows/work_order_workflow.py
```

## 如何使用

### 添加新工单类型（3步）

1. **创建配置文件** (`configs/mutation_steps/your_type.json`)
   ```json
   {
     "work_order_type": "your_type",
     "steps": [
       {"step": 1, "operation": "QUERY", "table": "...", ...},
       {"step": 2, "operation": "GENERATE_DML", "type": "UPDATE", ...}
     ]
   }
   ```

2. **更新实体提取提示词**（让 LLM 识别新类型）
   ```json
   {
     "work_order_subtype": "your_type",
     "param1": "value1"
   }
   ```

3. **测试验证**
   - 提交测试工单
   - 查看日志确认流程执行

## 设计原则

1. **配置与代码分离**: 业务逻辑在配置，代码只是执行引擎
2. **步骤解耦**: 每步只关注自己的查询，通过上下文传递数据
3. **渐进式迁移**: 旧类型继续工作，新类型逐步配置
4. **安全优先**: 只生成 DML 不执行，风险评估辅助决策

## 与原设计的对比

| 维度 | 原设计 | 新设计 |
|------|--------|--------|
| 多轮查询 | ❌ 不支持 | ✅ 支持任意步骤 |
| 数据依赖 | ❌ 无法处理 | ✅ 自动传递上下文 |
| 扩展性 | ❌ 需改代码 | ✅ 只需加配置 |
| 精确度 | ⚠️ 依赖 LLM | ✅ 配置驱动精确拼装 |
| 兼容性 | - | ✅ 完全向后兼容 |

## 后续优化方向

1. **配置验证 CLI**: 提供工具检查配置正确性
2. **可视化调试**: 输出步骤执行图
3. **条件路由**: 根据查询结果选择分支
4. **批量 DML**: 支持一次生成多条语句
5. **配置热加载**: 运行时更新无需重启

## 验收标准

- [x] 支持多轮 SQL 查询
- [x] 步骤间数据自动传递
- [x] 基于配置精确生成 DML
- [x] 向后兼容（LLM 回退）
- [x] 风险等级评估
- [x] 完整日志跟踪
- [x] 示例配置文件
- [x] 使用文档

## 快速开始

查看完整使用指南: [`docs/DML_MULTI_STEP_QUERY_GUIDE.md`](./DML_MULTI_STEP_QUERY_GUIDE.md)

---

**结论**: 该优化从根本上解决了 Mutation 分支无法查询数据库的问题，通过配置驱动实现了灵活、精确、可扩展的 DML 生成能力。
