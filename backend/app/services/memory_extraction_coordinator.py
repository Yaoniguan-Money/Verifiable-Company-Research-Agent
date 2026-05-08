"""Lightweight memory extraction coordinator."""

from __future__ import annotations

from collections.abc import Callable

MIN_NEW_MESSAGES = 4


class MemoryExtractionCoordinator:
    """负责阈值判断与单进程内的最小 coalescing。"""

    def __init__(
        self,
        min_new_messages: int = MIN_NEW_MESSAGES,
        max_coalesced_runs: int = 10,
    ) -> None:
        if min_new_messages < 1:
            raise ValueError("min_new_messages 必须 >= 1")
        if max_coalesced_runs < 1:
            raise ValueError("max_coalesced_runs 必须 >= 1")
        self.min_new_messages = min_new_messages
        self.max_coalesced_runs = max_coalesced_runs
        self._watermark_by_session: dict[str, int] = {}
        self._running_by_session: dict[str, bool] = {}
        self._dirty_by_session: dict[str, bool] = {}
        self._dirty_latest_by_session: dict[str, int] = {}

    def get_watermark(self, session_id: str) -> int:
        return self._watermark_by_session.get(session_id, 0)

    def is_running(self, session_id: str) -> bool:
        return self._running_by_session.get(session_id, False)

    def is_dirty(self, session_id: str) -> bool:
        return self._dirty_by_session.get(session_id, False)

    def should_extract(self, *, session_id: str, latest_message_count: int) -> bool:
        self._validate_latest_message_count(latest_message_count)
        watermark = self.get_watermark(session_id)
        new_messages = latest_message_count - watermark
        return new_messages >= self.min_new_messages

    def mark_extracted(self, *, session_id: str, latest_message_count: int) -> None:
        self._validate_latest_message_count(latest_message_count)
        watermark = self.get_watermark(session_id)
        if latest_message_count < watermark:
            raise ValueError("latest_message_count 不能小于当前 watermark")
        self._watermark_by_session[session_id] = latest_message_count

    def maybe_trigger_extraction(
        self,
        *,
        session_id: str,
        latest_message_count: int,
        on_trigger: Callable[[str, int, int], None] | None = None,
    ) -> bool:
        self._validate_latest_message_count(latest_message_count)
        if self.is_running(session_id):
            if self.should_extract(
                session_id=session_id,
                latest_message_count=latest_message_count,
            ):
                self._mark_dirty(
                    session_id=session_id,
                    latest_message_count=latest_message_count,
                )
            return False

        if not self.should_extract(
            session_id=session_id,
            latest_message_count=latest_message_count,
        ):
            return False

        triggered = False
        current_latest_count = latest_message_count
        coalesced_runs = 0
        self._running_by_session[session_id] = True
        try:
            while self.should_extract(
                session_id=session_id,
                latest_message_count=current_latest_count,
            ):
                if coalesced_runs >= self.max_coalesced_runs:
                    self._mark_dirty(
                        session_id=session_id,
                        latest_message_count=current_latest_count,
                    )
                    break
                self._dirty_by_session[session_id] = False
                self._dirty_latest_by_session.pop(session_id, None)

                previous_watermark = self.get_watermark(session_id)
                new_messages = current_latest_count - previous_watermark
                if on_trigger is not None:
                    on_trigger(session_id, current_latest_count, new_messages)

                self.mark_extracted(
                    session_id=session_id,
                    latest_message_count=current_latest_count,
                )
                triggered = True
                coalesced_runs += 1

                dirty_latest_count = self._dirty_latest_by_session.pop(session_id, None)
                self._dirty_by_session[session_id] = False
                if dirty_latest_count is None:
                    break
                current_latest_count = max(current_latest_count, dirty_latest_count)

            return triggered
        finally:
            self._running_by_session[session_id] = False

    def _mark_dirty(self, *, session_id: str, latest_message_count: int) -> None:
        self._dirty_by_session[session_id] = True
        previous_dirty_latest = self._dirty_latest_by_session.get(session_id, 0)
        self._dirty_latest_by_session[session_id] = max(
            previous_dirty_latest,
            latest_message_count,
        )

    def _validate_latest_message_count(self, latest_message_count: int) -> None:
        if latest_message_count < 0:
            raise ValueError("latest_message_count 不能为负数")
