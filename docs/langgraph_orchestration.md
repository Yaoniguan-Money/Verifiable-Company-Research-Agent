# LangGraph Orchestration

## Why LangGraph

The current main research flow uses a LangGraph `StateGraph` instead of a service-step loop.
The goal is not to make the system autonomous. The goal is to make workflow state, node
boundaries, conditional branches, and audit decisions explicit while preserving the existing
provider, repository, report, source quality, and compliance behavior.

The project remains an open-source MVP / reference implementation. It is not a production research system.

## Previous Service Workflow Limitation

The old service workflow executed named steps through `WorkflowStepExecutor`. That was simple
and testable, but the orchestration shape was implicit:

- state was mostly a `WorkflowState` log object;
- embedding/retrieval were hidden inside report evidence assembly;
- source quality and compliance decisions were not visible as graph branches;
- adding more branch points would have made the step executor look like a second workflow engine.

## LangGraph-First Architecture

```text
API Router
  -> WorkflowFacade / ResearchWorkflowService
    -> LangGraph StateGraph
      -> Graph Nodes
        -> Domain Services
        -> Providers
        -> Repository
```

`ResearchWorkflowService` now acts as a facade. It still owns task creation, task claiming,
engine selection, failure persistence, report lookup, and API compatibility. The default engine
is `WORKFLOW_ENGINE=langgraph`; `WORKFLOW_ENGINE=service` remains a legacy fallback.

## ResearchGraphState

The LangGraph state carries the main workflow data directly:

- `task_id`
- `company_name`
- `question`
- `sources`
- `evidence_chunks`
- `embedding_results`
- `retrieved_evidence`
- `extracted_facts`
- `verification_results`
- `risk_analysis`
- `report`
- `citations`
- `compliance_decision`
- `status`
- `error`
- `steps`
- `workflow_decisions`
- `source_quality_summary`
- `source_quality_insufficient`
- `compliance_action`

The graph output is converted back to the existing `WorkflowState` shape so current API responses
do not change.

## StateGraph Nodes

```text
load_task_node
  -> collect_sources_node
  -> source_quality_gate_node
  -> record_source_quality_gap_node? 
  -> ingest_chunks_node
  -> embed_chunks_node
  -> retrieve_evidence_node
  -> extract_facts_node
  -> verify_facts_node? / record_evidence_gap_node?
  -> record_verification_risk_node?
  -> analyze_risks_node
  -> build_report_node
  -> compliance_check_node
  -> apply_compliance_rewrite_node? / persist_blocked_result_node? / persist_result_node
```

Node responsibilities stay narrow:

- source collection calls the configured search provider;
- ingestion calls `IngestionService`;
- embedding and retrieval reuse `ReportEvidenceService`, `EmbeddingService`, and `RetrievalService`;
- fact extraction and verification reuse existing deterministic services;
- report generation reuses report evidence, grounding, and assembly services;
- compliance uses the LLM provider compliance boundary and branches on the result;
- persistence remains in the repository/model layer.

## Conditional Branches

`source_quality_insufficient`

The graph calls centralized source quality helpers based on `SourceAuthority`, `SourceLayer`,
and source metadata. If the source set is weak, the graph records a workflow decision and still
continues, but the final report keeps source quality limitations visible. The graph does not
promote low-authority material into high-confidence evidence.

`compliance_action`

After `compliance_check_node`, the graph branches explicitly:

- `passed` -> `persist_result_node`
- `rewrite` -> `apply_compliance_rewrite_node` -> `persist_result_node`
- `blocked` -> `persist_blocked_result_node`

This keeps compliance control visible in the graph rather than hiding it inside a linear service
step.

## Reused Rules

The graph does not duplicate source quality, citation sorting, or fact gate rules:

- source quality helpers live in `app.schemas.common`;
- `official_entry_page` and low-authority fact blocking remain in fact extraction/verification;
- official-body evidence inclusion and citation sorting remain in `ReportEvidenceService`;
- report compliance semantics remain in the LLM provider compliance check boundary.

## Legacy Workflow Role

`WorkflowStepExecutor` is retained as a legacy fallback for `WORKFLOW_ENGINE=service`. It is no
longer the default main path and should not receive new primary orchestration behavior.

## Not An Autonomous Agent

This is a fixed workflow graph. The LLM does not decide which node to run next, does not create
new tools, and does not freely plan the research process. LangGraph is used for orchestration,
state, branches, and audit visibility.

## Still MVP / Reference Implementation

LangGraph-first 编排**不取代**业务能力：语义 embedding 由 `dashscope`/OpenAI-compatible provider 可选接入，但系统仍不包含生产级来源发现体系、vector DB（Chroma/Qdrant）、分布式执行、durable checkpoints、人机复核队列、生产可观测性或生产合规审核流水线。
