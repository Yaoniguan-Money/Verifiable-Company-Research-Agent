"""工作流进度事件总线。

内存实现 + 进程内单例：SSE 端点轮询此 bus 推送增量事件。
注意：多进程部署时事件不会跨进程同步，需要替换为 Redis Pub/Sub 等外部 broker。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class WorkflowEventBus:
    """线程安全的 in-memory 事件 ring，按 ``task_id`` 分桶。"""

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = Lock()

    def emit(self, task_id: str, event_type: str, **payload: Any) -> None:
        """追加一条事件，时间戳由本地服务器写入。"""
        event = {
            "type": event_type,
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self._lock:
            self._events[task_id].append(event)

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        """返回该 task 当前所有事件的快照副本（避免调用方持有锁内引用）。"""
        with self._lock:
            return list(self._events.get(task_id, []))

    def clear(self, task_id: str) -> None:
        with self._lock:
            self._events.pop(task_id, None)


_bus = WorkflowEventBus()


def get_workflow_event_bus() -> WorkflowEventBus:
    return _bus


def format_sse(event: dict[str, Any]) -> str:
    """格式化为 SSE 协议帧：``data: <json>\\n\\n``。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
