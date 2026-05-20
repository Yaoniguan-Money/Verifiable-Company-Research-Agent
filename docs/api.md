# API Reference

## 1. Overview

当前 API 属于开源 MVP / reference implementation，用于演示可溯源企业公开信息研究流程。后端基于 FastAPI；默认配置使用 `mock + public_sources + local_hashing`，搜索会访问公开网络来源且不需要外部厂商 API key。DeepSeek LLM + Baidu AI Search + DashScope `text-embedding-v4` 是可选真实链路 provider 组合，vector store 仍是 `in_memory/sqlite` 本地工程实现。

所有接口都不是生产级接口，不包含完整鉴权、权限系统、生产级限流或审计。

## 1.1 当前能力边界

- `local_hashing` 仅用于 dev/test，`mock` 仅用于测试；`dashscope` 是可选真实链路语义 embedding provider 示例。
- `in_memory/sqlite` vector store 是本地 MVP，不是生产级向量数据库。
- 真实公司样例只用于链路回归，不代表系统绑定特定企业。
- `official_entry_page` 表示官方入口页，不能作为高置信财务事实支撑；具体官方正文应来自 `official_pdf` 或 `official_disclosure_page`。
- API 输出中的 citations 用于展示可追溯证据链，不等价于生产级事实审计。
- `scripts/verify_real_chain.py` 默认 strict，不接受 `local_hashing` 作为真实语义链路。

## 1.2 Provider 配置口径

默认配置：

```text
LLM_PROVIDER=mock
SEARCH_PROVIDER=public_sources
EMBEDDING_PROVIDER=local_hashing
mock_enabled=true
```

`mock_enabled=true` 只表示 LLM/Embedding 里仍可能有 mock；是否联网搜索应看 `search_network_enabled`。可选真实链路示例可切换到 DeepSeek、Baidu AI Search、DashScope 等 provider。真实链路验收需要本地 `.env` 中配置对应 key，并显式传入待研究公司与问题。具体统计受上游返回波动影响，以本地 `verify_real_chain.py` 实时结果为准。

## 2. Base URL

本地后端默认：

```text
http://127.0.0.1:8000
```

前端 Vite 开发模式默认将 `/api` 代理到该地址。

## 3. Health

### GET `/api/health`

用途：检查服务是否启动。

响应示例：

```json
{
  "status": "ok",
  "app_name": "Verifiable Company Research Agent",
  "version": "0.1.0",
  "env": "dev",
  "compliance_strict_mode": true,
  "db_scheme": "sqlite"
}
```

### GET `/api/health/providers`

用途：查看当前 provider 选择与 key 配置状态（布尔值），用于真实链路验收。

响应示例：

```json
{
  "llm_provider": "mock",
  "search_provider": "public_sources",
  "search_mode": "online_discovery",
  "search_network_enabled": true,
  "embedding_provider": "local_hashing",
  "embedding_model": "local_hashing",
  "embedding_api_key_configured": false,
  "embedding_base_url_configured": false,
  "embedding_base_url_host": null,
  "embedding_dimension_configured": false,
  "embedding_max_batch_size": 10,
  "qianfan_api_key_configured": false,
  "deepseek_api_key_configured": false,
  "baidu_ai_search_api_key_configured": false,
  "mock_enabled": true
}
```

## 4. Research Workflow APIs

### POST `/api/research/tasks`

用途：创建研究任务。

请求示例：

```json
{
  "company_name": "Demo Tech Inc",
  "question": "What changed in R&D spending and key operating risks?",
  "session_id": null
}
```

响应示例：

```json
{
  "task_id": "uuid",
  "status": "created"
}
```

### POST `/api/research/tasks/{task_id}/run`

用途：执行当前 research workflow（可在 mock 或真实 provider 组合下运行）。

响应示例：

```json
{
  "task_id": "uuid",
  "report_id": "uuid",
  "status": "completed",
  "title": "Demo Tech Inc 公开信息研究报告",
  "summary": "# Demo Tech Inc ...",
  "error": null
}
```

### GET `/api/research/tasks/{task_id}`

用途：查询任务状态。

响应示例：

```json
{
  "task_id": "uuid",
  "company_name": "Demo Tech Inc",
  "question": "What changed in R&D spending?",
  "status": "completed",
  "created_at": "2026-04-28T00:00:00",
  "updated_at": "2026-04-28T00:00:01"
}
```

## 5. Report APIs

### GET `/api/research/tasks/{task_id}/report`

用途：读取报告内容、citations 和合规状态。

响应示例：

```json
{
  "task_id": "uuid",
  "title": "Demo Tech Inc 公开信息研究报告（Mock）",
  "content": "# Demo Tech Inc ...",
  "citations": [
    {
      "source_id": "source_uuid",
      "chunk_id": "chunk_uuid",
      "url": "https://example.com/report",
      "title": "Demo source",
      "retrieved_at": "2026-04-28T00:00:00"
    }
  ],
  "compliance_status": "passed"
}
```

## 6. Evidence / Source APIs

### GET `/api/sources/{task_id}`

用途：查询任务下资料来源。

响应示例：

```json
{
  "task_id": "uuid",
  "items": [
    {
      "id": "source_uuid",
      "task_id": "uuid",
      "title": "Demo annual report",
      "url": "https://example.com/report",
      "source_type": "annual_report",
      "published_at": null,
      "retrieved_at": "2026-04-28T00:00:00",
      "raw_content": "...",
      "credibility_score": 0.8,
      "created_at": "2026-04-28T00:00:00"
    }
  ]
}
```

## 7. Fact and Verification APIs

### GET `/api/facts/{task_id}`

用途：查询结构化事实。

响应示例：

```json
{
  "task_id": "uuid",
  "items": [
    {
      "id": "fact_uuid",
      "task_id": "uuid",
      "claim": "2023 R&D expenditure was 100",
      "metric_name": "R&D_expenditure",
      "value": "100",
      "period": "2023",
      "source_id": "source_uuid",
      "chunk_id": "chunk_uuid",
      "confidence": 0.76,
      "created_at": "2026-04-28T00:00:00"
    }
  ]
}
```

### GET `/api/verification/{task_id}`

用途：查询事实验证结果。

响应示例：

```json
{
  "task_id": "uuid",
  "items": [
    {
      "id": "verification_uuid",
      "fact_id": "fact_uuid",
      "task_id": "uuid",
      "status": "verified",
      "confidence": 0.88,
      "supporting_sources": ["source_a", "source_b"],
      "conflicting_sources": [],
      "reason": "同一指标同一期间存在多个独立来源且取值一致",
      "created_at": "2026-04-28T00:00:00"
    }
  ]
}
```

## 8. Chat API

### POST `/api/chat`

用途：围绕已有 task/report 做最小追问，并返回合规状态。

请求示例：

```json
{
  "task_id": "uuid",
  "message": "Can I buy this stock?"
}
```

响应示例：

```json
{
  "task_id": "uuid",
  "message": "Can I buy this stock?",
  "answer": "当前请求涉及投资建议或个性化投融导向信息，已按合规策略拒绝...",
  "compliance_status": "blocked",
  "violations": ["buy"]
}
```

## 9. Memory APIs

当前没有公开 memory HTTP API。

当前已实现的是后端内部温记忆 MVP：

- `MemoryOperation` schema
- `MemoryExtractionCoordinator`
- `_running/_dirty/_watermark` 最小 coalescing
- `user_memories` persistence

这些能力当前主要通过服务层和测试验证，不是面向前端的完整产品功能。

## 10. Current API Limitations

- 无登录注册和权限系统。
- 无生产级错误码体系。
- 无生产级分页、过滤、审计。
- 来源质量仍受上游搜索返回与网页可抓取性影响，不能视为稳定权威来源检索系统。
- `in_memory/sqlite` 不是生产级向量数据库，且当前 API 仍不具备生产级检索评测和服务治理能力。
- 不提供投资建议、目标价、收益承诺或个股推荐。
