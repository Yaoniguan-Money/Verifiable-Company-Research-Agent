"""阶段 3.C：Verification Schema 与状态机约束测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.models.verification import VerificationResult
from app.schemas.verification import (
    VerificationOutput,
    VerificationResultCreate,
    VerificationResultRead,
)
from pydantic import ValidationError


def test_valid_verified_result_can_be_created() -> None:
    obj = VerificationResultCreate.model_validate(
        {
            "fact_id": "fact_1",
            "task_id": "task_1",
            "status": "verified",
            "confidence": 0.91,
            "supporting_sources": ["source_a", "source_b"],
            "conflicting_sources": [],
            "reason": "多来源一致支持该事实",
        }
    )
    assert obj.status.value == "verified"
    assert len(obj.supporting_sources) == 2


def test_valid_conflicted_result_contains_conflicting_sources() -> None:
    obj = VerificationResultCreate.model_validate(
        {
            "fact_id": "fact_1",
            "task_id": "task_1",
            "status": "conflicted",
            "confidence": 0.42,
            "supporting_sources": ["source_a"],
            "conflicting_sources": ["source_b"],
            "reason": "不同来源给出的数值冲突",
        }
    )
    assert obj.status.value == "conflicted"
    assert obj.conflicting_sources == ["source_b"]


def test_valid_insufficient_result_with_reason() -> None:
    obj = VerificationResultCreate.model_validate(
        {
            "fact_id": "fact_2",
            "task_id": "task_1",
            "status": "insufficient",
            "confidence": 0.33,
            "supporting_sources": [],
            "conflicting_sources": [],
            "reason": "仅单一来源或证据不足，无法确认",
        }
    )
    assert obj.status.value == "insufficient"
    assert obj.reason


def test_status_must_be_in_allowed_values() -> None:
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "task_id": "task_1",
                "status": "buy",
                "confidence": 0.8,
                "supporting_sources": [],
                "conflicting_sources": [],
                "reason": "非法状态",
            }
        )


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_confidence_out_of_range_should_fail(bad_confidence: float) -> None:
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "task_id": "task_1",
                "status": "verified",
                "confidence": bad_confidence,
                "supporting_sources": ["source_a"],
                "conflicting_sources": [],
                "reason": "置信度越界",
            }
        )


def test_missing_fact_id_or_task_id_should_fail() -> None:
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "task_id": "task_1",
                "status": "verified",
                "confidence": 0.9,
                "supporting_sources": ["source_a"],
                "conflicting_sources": [],
                "reason": "缺少 fact_id",
            }
        )
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "status": "verified",
                "confidence": 0.9,
                "supporting_sources": ["source_a"],
                "conflicting_sources": [],
                "reason": "缺少 task_id",
            }
        )


def test_reason_is_required_and_non_empty() -> None:
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "task_id": "task_1",
                "status": "verified",
                "confidence": 0.9,
                "supporting_sources": ["source_a"],
                "conflicting_sources": [],
            }
        )
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "task_id": "task_1",
                "status": "insufficient",
                "confidence": 0.2,
                "supporting_sources": [],
                "conflicting_sources": [],
                "reason": "",
            }
        )


def test_sources_fields_are_serializable() -> None:
    obj = VerificationResultCreate.model_validate(
        {
            "fact_id": "fact_1",
            "task_id": "task_1",
            "status": "conflicted",
            "confidence": 0.4,
            "supporting_sources": ["source_a"],
            "conflicting_sources": ["source_b", "source_c"],
            "reason": "序列化测试",
        }
    )
    dumped = obj.model_dump(mode="json")
    assert dumped["supporting_sources"] == ["source_a"]
    assert dumped["conflicting_sources"] == ["source_b", "source_c"]


def test_read_schema_supports_orm_conversion() -> None:
    orm_obj = VerificationResult(
        id="ver_1",
        fact_id="fact_1",
        task_id="task_1",
        status="verified",
        confidence=0.88,
        supporting_sources=["source_a"],
        conflicting_sources=[],
        reason="ORM 转换兼容",
        created_at=datetime.now(timezone.utc),
    )
    read = VerificationResultRead.model_validate(orm_obj)
    assert read.id == "ver_1"
    assert read.status.value == "verified"
    assert read.reason == "ORM 转换兼容"


def test_verification_output_enforces_task_id_consistency() -> None:
    with pytest.raises(ValidationError):
        VerificationOutput.model_validate(
            {
                "task_id": "task_main",
                "results": [
                    {
                        "fact_id": "fact_1",
                        "task_id": "task_other",
                        "status": "insufficient",
                        "confidence": 0.3,
                        "supporting_sources": [],
                        "conflicting_sources": [],
                        "reason": "任务不一致",
                    }
                ],
            }
        )

