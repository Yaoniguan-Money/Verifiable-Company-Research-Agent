from __future__ import annotations

from app.compliance.input_guard import evaluate_user_input
from app.compliance.semantic import classify_investment_tone


def test_input_guard_blocks_buy_advice() -> None:
    allowed, msg = evaluate_user_input("这只股票能买吗？给个买入建议")
    assert allowed is False
    assert msg


def test_input_guard_allows_research_question() -> None:
    allowed, _ = evaluate_user_input("近三年研发投入和经营风险如何？")
    assert allowed is True


def test_semantic_classify_rewritable() -> None:
    assert classify_investment_tone("预计目标价将达到200元") == "rewritable"
