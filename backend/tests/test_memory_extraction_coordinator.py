"""阶段 5C：MemoryExtractionCoordinator 骨架测试。"""

from __future__ import annotations

import pytest
from app.services.memory_extraction_coordinator import (
    MIN_NEW_MESSAGES,
    MemoryExtractionCoordinator,
)


def test_not_reach_threshold_should_not_trigger() -> None:
    coordinator = MemoryExtractionCoordinator()
    triggered: list[tuple[str, int, int]] = []

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES - 1,
        on_trigger=lambda sid, latest, new: triggered.append((sid, latest, new)),
    )

    assert not did_trigger
    assert triggered == []
    assert coordinator.get_watermark("s1") == 0


def test_reach_threshold_should_trigger() -> None:
    coordinator = MemoryExtractionCoordinator()
    triggered: list[tuple[str, int, int]] = []

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, latest, new: triggered.append((sid, latest, new)),
    )

    assert did_trigger
    assert triggered == [("s1", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES)]
    assert coordinator.get_watermark("s1") == MIN_NEW_MESSAGES


def test_after_marked_new_messages_below_threshold_should_not_trigger_again() -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[tuple[str, int, int]] = []

    first = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
    )
    second = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES + 2,
        on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
    )

    assert first
    assert not second
    assert events == [("s1", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES)]
    assert coordinator.get_watermark("s1") == MIN_NEW_MESSAGES


def test_invalid_latest_message_count_should_fail() -> None:
    coordinator = MemoryExtractionCoordinator()
    with pytest.raises(ValueError):
        coordinator.should_extract(session_id="s1", latest_message_count=-1)


def test_same_session_running_reentry_should_be_coalesced_and_drained() -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[tuple[str, int, int]] = []
    reentered = False

    def callback(session_id: str, latest_count: int, new_messages: int) -> None:
        nonlocal reentered
        events.append((session_id, latest_count, new_messages))
        if reentered:
            return
        reentered = True
        reentry = coordinator.maybe_trigger_extraction(
            session_id=session_id,
            latest_message_count=latest_count + MIN_NEW_MESSAGES,
            on_trigger=lambda *_: events.append(("unexpected", 0, 0)),
        )
        assert not reentry

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=callback,
    )

    assert did_trigger
    assert events == [
        ("s1", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES),
        ("s1", MIN_NEW_MESSAGES * 2, MIN_NEW_MESSAGES),
    ]
    assert not coordinator.is_dirty("s1")
    assert not coordinator.is_running("s1")
    assert coordinator.get_watermark("s1") == MIN_NEW_MESSAGES * 2


def test_continuous_dirty_should_stop_at_max_coalesced_runs() -> None:
    coordinator = MemoryExtractionCoordinator(max_coalesced_runs=2)
    events: list[int] = []

    def callback(session_id: str, latest_count: int, _: int) -> None:
        events.append(latest_count)
        coordinator.maybe_trigger_extraction(
            session_id=session_id,
            latest_message_count=latest_count + MIN_NEW_MESSAGES,
            on_trigger=lambda *_: events.append(-1),
        )

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=callback,
    )

    assert did_trigger
    assert events == [MIN_NEW_MESSAGES, MIN_NEW_MESSAGES * 2]
    assert coordinator.is_dirty("s1")
    assert not coordinator.is_running("s1")
    assert coordinator.get_watermark("s1") == MIN_NEW_MESSAGES * 2


def test_different_sessions_should_not_pollute_each_other() -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[tuple[str, int, int]] = []

    coordinator.maybe_trigger_extraction(
        session_id="s1",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
    )
    coordinator.maybe_trigger_extraction(
        session_id="s2",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
    )

    assert events == [
        ("s1", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES),
        ("s2", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES),
    ]
    assert coordinator.get_watermark("s1") == MIN_NEW_MESSAGES
    assert coordinator.get_watermark("s2") == MIN_NEW_MESSAGES
    assert not coordinator.is_running("s1")
    assert not coordinator.is_running("s2")


def test_watermark_should_not_rollback() -> None:
    coordinator = MemoryExtractionCoordinator()
    coordinator.mark_extracted(session_id="s1", latest_message_count=MIN_NEW_MESSAGES)

    with pytest.raises(ValueError):
        coordinator.mark_extracted(session_id="s1", latest_message_count=MIN_NEW_MESSAGES - 1)
