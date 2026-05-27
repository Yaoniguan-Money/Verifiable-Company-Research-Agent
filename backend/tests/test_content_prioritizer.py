"""ContentPrioritizer regression tests."""

from __future__ import annotations

from app.services.content_prioritizer import ContentPrioritizer
from app.services.question_intent import parse_question_intent


def test_split_sections_keeps_markdown_headings() -> None:
    prioritizer = ContentPrioritizer()
    text = "摘要\n\n# 管理层讨论\n营收增长。\n\n## 研发投入\n研发费用提升。"

    sections = prioritizer._split_sections(text)

    assert [section.heading for section in sections] == ["", "管理层讨论", "研发投入"]
    assert sections[1].text.startswith("# 管理层讨论")
    assert sections[2].text.startswith("## 研发投入")


def test_prioritize_does_not_duplicate_leading_context(monkeypatch) -> None:
    prioritizer = ContentPrioritizer()
    monkeypatch.setattr(prioritizer._settings, "content_prioritizer", "intent_driven")
    intro_tail = "INTRO_TAIL_SHOULD_NOT_REPEAT"
    intro = ("摘要" * 250) + intro_tail
    relevant = "# 研发投入\n" + ("研发费用增长。" * 200)
    text = intro + "\n\n" + relevant

    out = prioritizer.prioritize(
        text,
        "研发投入是多少",
        max_chars=1300,
        intent=parse_question_intent("研发投入是多少"),
    )

    assert out.startswith(intro[:500])
    assert intro_tail not in out
    assert "研发费用" in out


def test_prioritize_none_mode_is_plain_truncation(monkeypatch) -> None:
    prioritizer = ContentPrioritizer()
    monkeypatch.setattr(prioritizer._settings, "content_prioritizer", "none")

    text = "0123456789" * 100

    assert prioritizer.prioritize(text, "任意问题", max_chars=120) == text[:120]
