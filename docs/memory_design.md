# Memory Design

## 1. Design Goal

记忆系统目标是让同一用户/会话内的长期偏好或关注点能够被结构化保存，并为后续交互提供上下文基础。

当前只完成温记忆提取 MVP，不是完整长期记忆平台。

## 2. Three-layer Memory Model

设计上分三层：

| 层级 | 含义 | 当前状态 |
|---|---|---|
| Hot memory | 当前请求/当前上下文中的短期状态 | 主要由请求参数、task、report/facts/verification 承载 |
| Warm memory | 从若干消息中提取的结构化用户偏好/关注点 | 已实现 MVP |
| Cold memory | 长期总结、conversation summaries、历史知识沉淀 | 未实现 |

## 3. Current Implemented Scope

当前已完成：

- `MemoryOperation` schema
- `ADD / UPDATE / DELETE / NOOP` 契约
- `MemoryExtractionOutput`
- `MemoryExtractionCoordinator`
- `MIN_NEW_MESSAGES`
- `_running / _dirty / _watermark` 最小 coalescing
- `user_memories` ORM
- `MemoryPersistenceService`

当前没有完成：

- 真实 LLM 记忆抽取
- 生产级后台任务队列
- Redis / 分布式锁
- 完整用户画像系统
- 冷记忆 / `conversation_summaries`

## 4. Memory Extraction Flow

当前最小流程：

1. 新消息数量进入 coordinator。
2. coordinator 用 `latest_message_count - watermark` 判断是否达到 `MIN_NEW_MESSAGES`。
3. 达到阈值后触发提取回调。
4. 提取结果必须符合 `MemoryOperation` schema。
5. `NOOP` 表示本轮没有长期记忆价值。
6. `ADD/UPDATE/DELETE` 交给 persistence service 处理。

当前测试使用 fake operation / callback 验证闭环，不接真实 LLM。

## 5. Coalescing and Watermark

coordinator 维护：

- `_watermark_by_session`
- `_running_by_session`
- `_dirty_by_session`

语义：

- 未达阈值不触发。
- 达阈值且未 running 时触发。
- 同 session running 时不重复触发，若有新消息达到阈值则置 dirty。
- watermark 防止重复处理旧消息。

当前是进程内内存态，不是分布式并发控制。

## 6. Persistence Boundary

`user_memories` 最小字段：

- `user_id`
- `memory_type`
- `key`
- `value`
- `confidence`
- `reason`
- `is_active`
- `created_at`
- `updated_at`

操作策略：

- `ADD`：新增；若 active 记录已存在则更新以避免重复。
- `UPDATE`：存在则更新；不存在则创建。
- `DELETE`：逻辑失效化 `is_active=False`。
- `NOOP`：不写库。

## 7. Chat / Session Relationship

当前已有 `sessions/messages` 表作为后续多轮上下文基础。warm memory persistence 与 chat 尚未做完整产品化联动。

当前前端 chat 使用真实 `/api/chat`，但不是完整聊天系统，也不是生产级个性化推荐系统。

## 8. Current Limitations

- 不接真实 LLM。
- 不自动生成复杂用户画像。
- 不做跨进程合并。
- 不做生产级队列。
- 不提供投资偏好建议或个性化投顾能力。

## 9. Future Extensions

可能扩展：

- LLM-based memory extraction（需要强 schema 校验）。
- conversation summaries。
- cold memory 检索。
- 分布式 coalescing。
- memory explainability / audit log。
# Memory Layer Update

当前记忆体系显式拆成三层：

- `hot`：当前会话短上下文，来自最近消息，不长期持久化为用户偏好。
- `warm`：用户偏好、关注点、报告风格等可更新记忆，写入 `user_memories`。
- `cold`：可复用企业知识或稳定背景信息，写入 `user_memories`，后续可接向量库检索。

当前已完成 schema、ORM、持久化与读取服务层支持；还没有做复杂的自动晋升策略。  
也就是说，系统已经能区分冷热层，但“从 hot 自动沉淀到 warm/cold”的策略仍是后续工程。
