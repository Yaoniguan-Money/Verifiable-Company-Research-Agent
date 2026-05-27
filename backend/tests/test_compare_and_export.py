"""对比分析与报告导出 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_compare_endpoint_runs_two_tasks(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/research/compare",
        json={
            "companies": [
                {"company_name": "公司A", "stock_code": "000001"},
                {"company_name": "公司B", "stock_code": "000002"},
            ],
            "question": "比较研发投入",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["tasks"]) == 2


def test_export_markdown(client: TestClient, db: Session) -> None:
    from app.services.research_workflow import ResearchWorkflowService

    service = ResearchWorkflowService(db)
    task = service.create_research_task(company_name="导出测试", question="营收变化")
    service.run_workflow(task.id)
    response = client.get(f"/api/research/tasks/{task.id}/report/export?fmt=md")
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
