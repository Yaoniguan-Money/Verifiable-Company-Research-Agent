"""阶段 5B：MemoryOperation schema 测试。"""

from __future__ import annotations

import pytest
from app.schemas.memory import MemoryExtractionOutput, MemoryOperation
from pydantic import ValidationError


def test_valid_add_operation_passes() -> None:
    op = MemoryOperation.model_validate(
        {
            "op": "ADD",
            "memory_type": "user_preference",
            "key": "report_style",
            "value": "简洁",
            "confidence": 0.9,
            "reason": "用户明确偏好简洁回答",
        }
    )
    assert op.op.value == "ADD"
    assert op.key == "report_style"


def test_valid_update_operation_passes() -> None:
    op = MemoryOperation.model_validate(
        {
            "op": "UPDATE",
            "memory_type": "risk_focus",
            "key": "risk_focus",
            "value": "关注现金流风险",
            "confidence": 0.82,
            "reason": "用户更新关注重点",
        }
    )
    assert op.op.value == "UPDATE"
    assert op.value == "关注现金流风险"


def test_valid_delete_operation_passes() -> None:
    op = MemoryOperation.model_validate(
        {
            "op": "DELETE",
            "memory_type": "recent_company",
            "key": "recent_company",
            "reason": "用户表示不再跟踪该公司",
        }
    )
    assert op.op.value == "DELETE"
    assert op.value is None


def test_valid_noop_operation_passes() -> None:
    op = MemoryOperation.model_validate(
        {
            "op": "NOOP",
            "reason": "本轮仅寒暄，无长期记忆价值",
        }
    )
    assert op.op.value == "NOOP"
    assert op.memory_type is None


def test_invalid_op_should_fail() -> None:
    with pytest.raises(ValidationError):
        MemoryOperation.model_validate(
            {
                "op": "UPSERT",
                "reason": "非法操作",
            }
        )


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_confidence_out_of_range_should_fail(bad_confidence: float) -> None:
    with pytest.raises(ValidationError):
        MemoryOperation.model_validate(
            {
                "op": "ADD",
                "memory_type": "user_preference",
                "key": "report_style",
                "value": "详细",
                "confidence": bad_confidence,
                "reason": "置信度越界",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "op": "ADD",
            "memory_type": "user_preference",
            "value": "简洁",
            "reason": "缺 key",
        },
        {
            "op": "ADD",
            "memory_type": "user_preference",
            "key": "report_style",
            "reason": "缺 value",
        },
        {
            "op": "ADD",
            "memory_type": "user_preference",
            "key": "report_style",
            "value": "简洁",
        },
    ],
)
def test_add_missing_key_or_value_or_reason_should_fail(payload: dict) -> None:
    with pytest.raises(ValidationError):
        MemoryOperation.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "op": "DELETE",
            "memory_type": "recent_company",
            "reason": "缺 key",
        },
        {
            "op": "DELETE",
            "memory_type": "recent_company",
            "key": "recent_company",
        },
    ],
)
def test_delete_missing_key_or_reason_should_fail(payload: dict) -> None:
    with pytest.raises(ValidationError):
        MemoryOperation.model_validate(payload)


def test_noop_missing_reason_should_fail() -> None:
    with pytest.raises(ValidationError):
        MemoryOperation.model_validate(
            {
                "op": "NOOP",
            }
        )


def test_operations_empty_should_fail() -> None:
    with pytest.raises(ValidationError):
        MemoryExtractionOutput.model_validate({"operations": []})
