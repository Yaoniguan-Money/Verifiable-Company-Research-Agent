# Workflow Design

## 1. Status

默认研究主流程使用 `WORKFLOW_ENGINE=langgraph`，实现类为 `LangGraphWorkflowEngine`。旧的顺序 service path 被包成 `ServiceWorkflowEngine`，只作为 legacy fallback。

```text
API Router
  -> WorkflowFacade
      -> WorkflowEngine
          -> LangGraphWorkflowEngine
              -> StateGraph
                  -> Graph Nodes
                      -> ResearchDomainServices
                          -> Providers / Repository
```

LangGraph 只负责固定流程编排，不是自主规划 agent。

## 2. Boundary

`WorkflowFacade`:

- 创建任务
- claim 可运行任务
- 清理旧 task outputs
- 调用 `WorkflowEngine.run(task_id)`
- 失败时保存 task failure

`LangGraphWorkflowEngine`:

- 构建 StateGraph
- 定义节点、边和条件分支
- 维护 graph state、step result、workflow decision
- 将业务动作委托给 domain service

`ResearchDomainServices`:

- collect sources
- source quality gate
- ingestion / chunking
- embedding / indexing / retrieval
- fact extraction
- fact verification
- risk analysis
- report grounding / assembly
- compliance check / rewrite / block
- report persistence

Graph node 只做状态映射，例如把 `domain.extract_facts(task_id)` 的结果写回 `state["extracted_facts"]`。

## 3. Main Flow

1. `load_task_node`
2. `collect_sources_node`
3. `source_quality_gate_node`
4. `record_source_quality_gap_node`（条件分支）
5. `ingest_chunks_node`
6. `embed_chunks_node`
7. `retrieve_evidence_node`
8. `extract_facts_node`
9. `verify_facts_node` 或 `record_evidence_gap_node`
10. `record_verification_risk_node`（条件分支）
11. `analyze_risks_node`
12. `build_report_node`
13. `compliance_check_node`
14. `apply_compliance_rewrite_node` / `persist_result_node` / `persist_blocked_result_node`

## 4. Provider Configuration

默认配置是 `mock + public_sources + local_hashing`，其中搜索默认走联网公开来源。DeepSeek、Baidu AI Search、DashScope 是可选真实链路示例配置，不是 workflow 依赖。

Workflow 只认识接口：

- `LLMProvider`
- `SearchProvider`
- `EmbeddingProvider`
- `VectorStore`

切换 provider 应发生在 `Settings` 和 `ProviderFactory`，不应散落在 Application Service、Graph Node 或 Domain Service 的业务判断里。

## 5. Evidence and Citation Flow

证据流从 `Source.raw_content` 开始：

```text
Source
  -> EvidenceChunk
  -> Embedding
  -> VectorStore
  -> RetrievedEvidence
  -> Fact
  -> Verification
  -> Grounded Report + Citation
```

Citation 绑定：

- `source_id`
- `chunk_id`
- `title`
- `url`
- `retrieved_at`

`official_entry_page` 只能说明入口存在；`official_pdf` / `official_disclosure_page` 才能作为高置信事实候选来源。

## 6. Compliance Checkpoints

合规检查落在两个主要出口：

1. workflow 生成报告后检查再保存
2. chat follow-up 输出前检查

禁止输出买卖建议、目标价、收益承诺、个股推荐、个性化投资建议和持仓指导。

## 7. Limitations

- 当前是开源 MVP / reference implementation，不是生产级 agent 编排系统
- 没有人工审核节点
- 没有分布式执行或 graph 状态持久化
- 事实抽取、验证和合规仍偏规则化
- 外部 provider 返回质量会影响最终来源质量
