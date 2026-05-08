# Evaluation and Testing

## 1. Evaluation Goal

本项目测试目标是证明工程链路可运行、关键数据结构可验证、合规边界可回归。测试通过不代表生产级搜索质量、LLM 推理质量、事实审计质量或投资决策能力。

## 2. How to Run Tests

后端测试：

```powershell
.\.venv\Scripts\python -m pytest backend/tests -v
```

前端构建：

```powershell
cd frontend
npm run build
```

可选代码检查：

```powershell
.\.venv\Scripts\python -m ruff check backend
```

## 3. Current Test Coverage

| 模块 | 覆盖文件示例 | 能证明什么 |
|---|---|---|
| ORM / DB | `test_db_models.py` | 表结构、关系、级联、默认用户 |
| Workflow / API | `test_research_api.py`, `test_providers_workflow.py` | 创建/运行/查询任务主链路 |
| LangGraph workflow | `test_langgraph_research_workflow.py` | 可选 LangGraph engine 能复用同一批业务节点跑完整报告链路 |
| Ingestion / Chunking | `test_ingestion_service.py` | source -> chunks |
| Embedding provider | `test_embedding.py` | mock 与 local hashing 的 deterministic embedding id |
| Vector store | `test_vector_store.py` | InMemory / SQLite 写入、相似度查询、task 隔离、持久化 |
| Retrieval | `test_retrieval_service.py`, `test_phase2_rag_pipeline.py` | retrieval 与 evidence 回查 |
| Grounding / Citation | `test_report_grounding.py` | evidence -> citation/grounded section |
| Fact extraction | `test_fact_extraction_service.py` | rule-based facts 抽取 |
| Verification | `test_fact_verification_service.py`, `test_verification_schema.py` | 状态机与 rule-based 验证 |
| Report | `test_report_assembly_service.py`, `test_report_renderer.py` | 报告组合与渲染 |
| Workflow audit / steps | `test_workflow_audit_service.py`, `test_workflow_step_executor.py`, `test_langgraph_research_workflow.py` | workflow 审计决策、step 执行记录、LangGraph 复用同一 step executor |
| Compliance | `test_compliance_rules_struct.py`, `test_chat_guardrail_service.py` | allow/rewrite/refuse 与 chat guardrail |
| Memory | `test_memory_schema.py`, `test_memory_extraction_coordinator.py`, `test_user_memories_persistence.py`, `test_memory_phase5_integration.py` | 温记忆 schema、阈值、coalescing、持久化 |
| Frontend | `npm run build` | React/Vite 项目可构建 |

## 4. What the Tests Prove

- 主链路可以从 task 创建走到 report 落库和读取。
- citations、facts、verification、compliance 字段可被结构化验证。
- RAG 组件边界存在，且 InMemory MVP 可运行。
- Memory MVP 能表达 `ADD/UPDATE/DELETE/NOOP`，并能写入 `user_memories`。
- 前端工程能 build，API client 使用真实 HTTP 路径。

## 5. What the Tests Do Not Prove

- 不证明真实搜索质量。
- 不证明真实 LLM 抽取/总结质量。
- 不证明真实语义 embedding 质量；`local_hashing` 只提供离线词法向量能力。
- 不证明 LangGraph 人工审核、复杂重试、异步队列或分布式执行能力；当前只证明主链路图编排、facts 为空路由和 verification risk 路由可运行。

## 公开资料回归集量化指标

`data/eval/public_company_regression.json` 固化一组公开公司回归样例。  
`data/eval/public_company_regression_fixtures.json` 提供离线 fixture，避免每次评测都实时下载 PDF；这些节选只作为稳定回归样本，不声明为真实最新公开数据。固定真实公司名称只应出现在 `data/eval/*`、`docs/evaluation_cases.md` 和 `scripts/run_public_company_regression.py`。

当前覆盖的核心指标组包括研发投入、营业收入、归母净利润、收入结构、产能、产量和销量等。具体样例名称见 `docs/evaluation_cases.md` 与 `data/eval/*`。

稳定离线评测：

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --json
```

Markdown 汇总输出：

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --format markdown
```

也可以使用等价的 `--markdown` 参数。Markdown 输出包含总览字段 `case_count`、`passed_count`、`average_metric_coverage_ratio`、`total_source_count`、`total_fact_count`；分公司结果包含 `company_name`、`source_count`、`fact_count`、`metric_coverage_ratio`、`missing_metric_groups`、`unexpected_metric_groups` 和 `passed`，便于粘贴到评审记录或回归报告中。`--json` 行为保持不变，仍输出完整结构化 JSON。

前端首页的“公开资料回归评测结果”模块展示同一份离线 fixture 回归摘要的静态快照。该模块只读、本地内置，不调用后端接口，不触发真实搜索；它只说明当前 fixture 回归样本是否稳定通过，不代表真实搜索质量或生产级事实审计能力。

真实联网评测并写入本地缓存：

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --extract --json --cache-file data/eval/public_company_sources_cache.json
```

后续复用缓存时，脚本会优先读取 `--cache-file`，不再重复抓取同一批公开资料。缓存文件通常较大，且可能包含长文本，不建议提交仓库。

脚本会输出：

- `source_count`：公开资料来源数量。
- `fact_count`：抽取到的结构化事实数量。
- `observed_metric_groups`：实际抽到的指标组。
- `missing_metric_groups`：预期但未抽到的指标组。
- `metric_coverage_ratio`：指标组覆盖率。
- `evidence_density`：每个来源平均抽取 facts 数。

默认 `--fail-under 0.7`，用于避免“能跑但没有信息密度”的假通过。当前 fixture 路径应稳定达到 6/6 通过。

PDF/年报表格抽取回归样本已扩充，当前 `backend/tests/test_financial_table_extraction_service.py` 覆盖：

- 金额单位上下文：`单位：元`、`单位：万元`、`单位：千元`、`单位：亿元`。
- 年度横表：`2024年 / 2023年 / 2022年` 列头映射到指标行。
- 期间列头：`本期金额 / 上期金额`，并在表头保留对应年份。
- 分业务收入表：多业务收入行横向披露。
- 研发费用表：研发费用按年度横向披露。
- 产能 / 产量 / 销量表：产品运营指标按年度横向披露。
- 产品类别宽表：同一行同时披露产能、产量、销量和销售收入。

这些样本只增强测试覆盖，未改变表格抽取算法。
- 不证明 Chroma/Qdrant 持久化能力。
- 不证明生产级事实审计准确性。
- 不证明生产级合规系统鲁棒性。
- 不证明浏览器端 E2E 交互稳定性。
- 不证明多进程/分布式并发安全。

## 6. Latest Known Results

2026-04-29 增强 LangGraph verification gate 后最近一次验证：

```text
ruff: All checks passed
backend: 234 passed
frontend: npm run build passed
LangGraph provider tests passed:
- normal path: ExtractFacts -> VerifyFacts -> AnalyzeRisks
- no-fact path: ExtractFacts -> RecordEvidenceGap -> AnalyzeRisks
- verification-risk path: VerifyFacts -> RecordVerificationRisk -> AnalyzeRisks
- workflow audit decisions are rendered into report content when present
- LLM risk-analysis fallback is rendered into report audit content
- workflow audit decisions use structured `WorkflowDecision` schema

2026-04-28 公开资料导入验证摘要仍保留：
DeepSeek provider smoke test passed
Local document workflow smoke test passed:
- sources: 4
- facts: 11
- verifications: 11
- citations: 8
- conflicted verification: 2
Official URL provider tests passed:
- whitelist HTML fetch
- non-whitelisted domain block
Baidu AI Search provider tests passed:
- references -> source import
- reference page body fetch
- snippet fallback
- irrelevant reference filtering
- security-check page fallback
- provider factory key guard
CNINFO / public-source provider tests passed:
- CNINFO stock list resolution
- annual/semiannual report PDF download path
- summary / English / correction report filtering
- annual-report-first sorting for recent multi-year research
- hybrid official-first + search-supplement dedupe
- DeepSeek risk-analysis timeout degradation keeps workflow usable
- known-period facts replace duplicate unknown-period facts from the same source/value
- public-company regression set covers the fixture cases documented in `docs/evaluation_cases.md`
- table-row extraction covers R&D expense, revenue segments, capacity, production and sales volume
- financial table extraction is now isolated in `FinancialTableExtractionService`
- table unit context such as `单位：千元` is supported
- vehicle wide rows can extract capacity / production / sales / sales revenue
- metric-name normalization lets safe aliases such as R&D expense / R&D expenditure verify together
- profit metrics preserve accounting boundaries between net profit / parent net profit / deducted net profit
- fact-value normalization prevents equivalent units such as `亿元 / 万元 / 千元 / 元` and `GWh / MWh` from being treated as conflicts
- verification reason codes explain whether a result came from unit normalization, metric alias normalization, multi-source conflict, single-source insufficiency, or rejection
- question-aware fact relevance separates core facts from supporting facts for R&D, revenue structure, capacity / production / sales, profit and risk-oriented questions
Report renderer tests passed:
- research-question coverage gap section
Chat follow-up tests passed:
- ungrounded LLM answer replacement
Fact extraction tests passed:
- R&D phrasing like “研发投入超200亿”
- separate profit metrics for parent/deducted/net profit
- table rows with year headers such as `项目 2024年 2023年`

轻量真实公开资料 smoke：

```text
$env:SEARCH_PROVIDER='cninfo_announcements'
$env:CNINFO_TOP_K='2'
$env:CNINFO_MAX_SOURCE_CHARS='90000'
.\.venv\Scripts\python scripts\run_public_company_regression.py --extract

case_001 sources=2 facts=98 metric_groups=['R&D_expenditure', 'production_capacity', 'revenue', 'revenue_segment', 'sales_volume']
case_002 sources=2 facts=118 metric_groups=['R&D_expenditure', 'net_profit_parent', 'production_volume', 'revenue', 'revenue_segment']
case_003 sources=2 facts=83 metric_groups=['R&D_expenditure', 'production_capacity', 'production_volume', 'revenue_segment', 'sales_volume']
```

前端构建输出摘要：

```text
vite v5.4.21 building for production...
✓ 32 modules transformed.
✓ built
```

## 7. Future Evaluation Plan

后续若进入生产化方向，应补：

- 扩展真实 provider 回归集到更多行业。
- 固定公开数据集的事实抽取 / 验证评测。
- RAG 检索质量指标。
- 合规对抗测试集。
- 前端 E2E 测试。
- 性能与并发测试。
