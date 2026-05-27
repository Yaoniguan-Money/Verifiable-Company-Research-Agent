from __future__ import annotations

from app.services.chat_grounding import GroundedFollowupAnswerBuilder


def test_denial_regex_does_not_false_positive_on_english_phrase_with_data() -> None:
    builder = GroundedFollowupAnswerBuilder()
    answer = "The report summarizes revenue data for 2025 in plain language."
    assert not builder._looks_bad_followup(answer)


def test_denial_regex_catches_report_lacks_data_phrasing() -> None:
    builder = GroundedFollowupAnswerBuilder()
    assert builder._looks_bad_followup("报告中没有研发投入相关数据。")
    assert builder._looks_bad_followup("The report does not contain R&D figures.")
