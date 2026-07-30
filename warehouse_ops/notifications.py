from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, TextIO
import sys

from .tasks import EscalationLevel, WarehouseTask


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    task_id: str
    escalation_level: EscalationLevel
    channel: str
    delivered_at: datetime
    payload: str


@dataclass(frozen=True, slots=True)
class NotificationDispatchResult:
    delivered: tuple[NotificationDelivery, ...]
    skipped_delivery_keys: tuple[str, ...]


class DeliveryStore(Protocol):
    def has_delivery(
        self,
        task_id: str,
        escalation_level: EscalationLevel,
        channel: str,
    ) -> bool: ...

    def record_delivery(self, delivery: NotificationDelivery) -> None: ...


class EscalationNotifier(Protocol):
    channel: str
    dry_run: bool

    def send(
        self,
        task: WarehouseTask,
        level: EscalationLevel,
        *,
        now: datetime,
    ) -> str: ...


class ConsoleEscalationNotifier:
    """Render escalation notifications without contacting an external service."""

    channel = "console"

    def __init__(self, *, stream: TextIO | None = None, dry_run: bool = True) -> None:
        self.stream = stream or sys.stdout
        self.dry_run = dry_run

    def send(
        self,
        task: WarehouseTask,
        level: EscalationLevel,
        *,
        now: datetime,
    ) -> str:
        payload = (
            f"[{level.value}] task={task.task_id} owner={task.escalation_owner} "
            f"severity={task.severity} sku={task.sku or '-'} message={task.issue_message}"
        )
        prefix = "DRY-RUN " if self.dry_run else ""
        print(prefix + payload, file=self.stream)
        return payload


def dispatch_escalation_notifications(
    tasks: tuple[WarehouseTask, ...],
    *,
    store: DeliveryStore,
    notifier: EscalationNotifier,
    now: datetime | None = None,
) -> NotificationDispatchResult:
    """Send each task/level/channel combination at most once.

    Dry-run adapters never create delivery records. This keeps previews honest and
    ensures a later real delivery is not suppressed by an earlier console check.
    """

    timestamp = _require_aware(now or datetime.now(timezone.utc))
    delivered: list[NotificationDelivery] = []
    skipped: list[str] = []

    for task in tasks:
        level = task.escalation_level(now=timestamp)
        if level is EscalationLevel.NONE:
            continue

        delivery_key = f"{task.task_id}:{level.value}:{notifier.channel}"
        if store.has_delivery(task.task_id, level, notifier.channel):
            skipped.append(delivery_key)
            continue

        payload = notifier.send(task, level, now=timestamp)
        delivery = NotificationDelivery(
            task_id=task.task_id,
            escalation_level=level,
            channel=notifier.channel,
            delivered_at=timestamp,
            payload=payload,
        )
        delivered.append(delivery)
        if not notifier.dry_run:
            store.record_delivery(delivery)

    return NotificationDispatchResult(tuple(delivered), tuple(skipped))


def _require_aware(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("Notification delivery times must be timezone-aware.")
    return timestamp
