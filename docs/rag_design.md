# RAG Design（历史设计记录）

## 文档定位

本文保留早期 RAG 工程骨架设计，部分阶段描述是历史状态。当前权威实现口径请以 `README.md`、`docs/provider_boundary.md`、`docs/workflow.md` 和 `docs/architecture.md` 为准。

当前默认搜索使用 `public_sources` 联网公开来源；`local_hashing` / `mock` 仍用于本地 dev/test 的 embedding 与规则化文本路径。DashScope `text-embedding-v4`（OpenAI-compatible）只是可选真实链路语义 embedding provider 示例。向量存储仍是 `in_memory/sqlite` MVP，不宣称生产级检索质量。

## 早期已完成（历史 RAG 骨架）

1. **Evidence Ingestion**  
   `source.raw_content -> evidence_chunks`，并保留 `chunk_metadata`（物理列不变）。

2. **Embedding Adapter**  
   `EmbeddingProvider` 抽象、`MockEmbeddingProvider`、`EmbeddingService`。后续阶段已扩展到 DashScope OpenAI-compatible embedding；mock/local 仍只用于 dev/test。

3. **Vector Store Adapter**  
   `VectorStore` 抽象、`InMemoryVectorStore`（cosine、top_k、task_id 过滤）。

4. **Retrieval Service**  
   `query -> query embedding -> similarity_search -> DB 回查 chunk/source -> RetrievedEvidence`。

5. **最小 Citation Grounding Primitive**  
   `RetrievedEvidence -> Citation`，并提供 grounded section。  
   无证据时明确输出“证据不足”，不伪造 citation。

6. **闭环验证链**  
   提供 `scripts/verify_phase2_rag.py`，串联验证：  
   `ingestion -> embedding -> vector store -> retrieval -> grounding`。  
   该链路用于工程验收。

7. **主报告链路最小接入**  
   `ResearchWorkflowService` 通过 `ReportEvidenceService` 调用 embedding provider、vector store、
   `RetrievalService` 与 `ReportGroundingService`，为报告追加“证据摘要（Grounded）”并合并 citations。

## 未完成（明确边界）

- 生产级通用公开资料发现
- 生产级 LLM/embedding 服务治理
- Chroma / Qdrant 等生产级向量库
- 生产级 report grounding
- QA grounding（多轮问答证据绑定）
- 生产级 RAG 评测与质量体系

## 当前链路接入状态

- `RetrievalService` 与 `ReportGroundingService` 已通过集成测试与验证脚本串联执行。  
- 主报告路径已接入最小 grounding/citation 组装。`local_hashing + SQLite` 能支撑离线持久化检索，但不代表生产级语义 RAG。

## 数据与可追溯性约束

- `evidence_chunks` 物理列继续使用 `chunk_metadata`；对外 schema 兼容 `metadata`。
- `Citation` 必须可回查 `source_id + chunk_id + title/url/retrieved_at`。
- 不将向量本体作为长期方案塞进 `chunk_metadata`。

## 合规口径

系统仍遵守 `docs/compliance.md`，不输出买入/卖出/目标价/收益承诺/个股推荐等表述。  
当前阶段能力用于工程链路验证，不用于真实投资决策。

