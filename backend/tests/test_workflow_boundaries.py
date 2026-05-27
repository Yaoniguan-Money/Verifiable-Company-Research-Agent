from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.providers.factory import ProviderFactory
from app.providers.llm import MockLLMProvider
from app.providers.search import LocalDocumentSearchProvider, MockSearchProvider
from app.providers.search.cached import CachedSearchProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.common import TaskStatus
from app.schemas.workflow import WorkflowState
from app.services.research_workflow import WorkflowFacade
from app.services.workflow_audit import WorkflowAuditService
from app.workflows.langgraph_research import LangGraphWorkflowEngine, initial_research_graph_state
from sqlalchemy.orm import Session


class _FakeWorkflowEngine:
    def __init__(self) -> None:
        self.run_calls: list[str] = []

    def run(self, task_id: str) -> WorkflowState:
        self.run_calls.append(task_id)
        return WorkflowState(
            task_id=task_id,
            company_name="Injected Engine Co",
            question="Boundary test",
            status=TaskStatus.COMPLETED,
        )

    def get_status(self, task_id: str) -> WorkflowState | None:
        return WorkflowState(
            task_id=task_id,
            company_name="Injected Engine Co",
            question="Boundary test",
            status=TaskStatus.RUNNING,
        )

    def resume(self, task_id: str) -> WorkflowState:
        return self.run(task_id)


class _FakeGraphDomain:
    def __init__(self) -> None:
        self.collect_calls: list[str] = []

    def collect_sources(self, task_id: str) -> list[object]:
        self.collect_calls.append(task_id)
        return []


def test_workflow_facade_delegates_run_to_workflow_engine(db: Session) -> None:
    engine = _FakeWorkflowEngine()
    facade = WorkflowFacade(db, workflow_engine=engine)
    task = facade.create_research_task(
        company_name="Replaceable Engine Co",
        question="Can the workflow engine be replaced?",
    )

    result = facade.run_workflow(task.id)

    assert result.success is True
    assert engine.run_calls == [task.id]
    assert result.state.company_name == "Injected Engine Co"


def test_workflow_facade_status_uses_injected_engine(db: Session) -> None:
    engine = _FakeWorkflowEngine()
    facade = WorkflowFacade(db, workflow_engine=engine)

    status = facade.get_workflow_status("task_123")

    assert status is not None
    assert status.status == TaskStatus.RUNNING
    assert status.company_name == "Injected Engine Co"


def test_graph_node_calls_domain_service_not_provider(db: Session) -> None:
    class ExplodingSearchProvider(MockSearchProvider):
        def search(self, company_name: str, question: str) -> list[object]:
            raise AssertionError("graph node must not call provider directly")

    fake_domain = _FakeGraphDomain()
    artifacts = ResearchArtifactRepository(db)
    engine = LangGraphWorkflowEngine(
        db=db,
        settings=Settings(_env_file=None),
        artifacts=artifacts,
        search_provider=ExplodingSearchProvider(),
        llm_provider=MockLLMProvider(),
        audit=WorkflowAuditService(artifacts),
        domain_services=fake_domain,  # type: ignore[arg-type]
    )
    state = initial_research_graph_state("task_graph_node")

    next_state = engine.collect_sources_node(state)

    assert fake_domain.collect_calls == ["task_graph_node"]
    assert next_state["sources"] == []
    assert next_state["steps"][-1].step_name == "collect_sources_node"


def test_provider_factory_can_switch_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "local_documents")
    monkeypatch.setenv("LOCAL_DOCUMENTS_DIR", "./data/imports")
    get_settings.cache_clear()

    provider = ProviderFactory().create_search_provider()

    if isinstance(provider, CachedSearchProvider):
        provider = provider.inner
    assert isinstance(provider, LocalDocumentSearchProvider)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("LOCAL_DOCUMENTS_DIR", raising=False)
    get_settings.cache_clear()


def test_default_api_examples_are_company_neutral() -> None:
    root = Path(__file__).resolve().parents[2]
    checked_paths = [
        root / "README.md",
        root / "docs" / "demo_walkthrough.md",
        root / "frontend" / "src" / "components" / "ResearchPanels.tsx",
    ]
    forbidden = (
        "\u5c0f\u7c73",
        "x" + "iaomi",
        "018" + "10",
        "\u817e\u8baf",
        "ten" + "cent",
        "\u6bd4\u4e9a\u8fea",
        "b" + "yd",
    )

    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in checked_paths)

    assert not any(token.lower() in combined for token in forbidden)
