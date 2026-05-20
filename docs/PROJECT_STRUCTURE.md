# Project Structure

This guide is for readers opening the repository for the first time.

## Code Layout

- `backend/app/api`
  FastAPI routes. Keep HTTP concerns here; business decisions live in services/workflows.

- `backend/app/workflows`
  LangGraph-first orchestration. Start with `langgraph_research.py` to see the main graph nodes, conditional branches, and strict failure path.

- `backend/app/services`
  Domain capabilities: ingestion, embedding orchestration, retrieval, fact extraction, fact verification, report grounding/evidence, compliance, and audit notes.

- `backend/app/providers`
  External capability adapters and dev/test providers. `ProviderFactory` is the explicit selection boundary; missing real-provider keys fail instead of falling back to mock.

- `backend/app/repositories`
  Database access for tasks and research artifacts.

- `backend/app/schemas`
  Pydantic contracts shared by API, services, workflow state, and tests.

- `frontend`
  Minimal React/Vite demo UI for task creation, report display, citations, sources, verification, and chat follow-up.

- `scripts`
  Local verification and release hygiene scripts. `verify_real_chain.py` is strict and does not print keys.

- `docs`
  Architecture, workflow, demo, release, evaluation, and historical development notes.

## Recommended Reading Order

1. `README.md`
2. `docs/architecture.md`
3. `docs/workflow.md`
4. `backend/app/workflows/langgraph_research.py`
5. `backend/app/providers/factory.py`
6. `scripts/verify_real_chain.py`
7. `docs/provider_boundary.md`

## Boundaries To Keep In Mind

- This is an open-source MVP / reference implementation, not a production research system.
- The default provider stack is `mock + public_sources + local_hashing`; search uses online public sources by default, while DeepSeek + Baidu AI Search + DashScope embedding remains an optional real-provider smoke example.
- `local_hashing` and `mock` are dev/test providers, not real semantic validation.
- Vector storage remains `in_memory/sqlite`; no Qdrant/Chroma/Milvus is wired in.
- The system does not provide investment advice.
