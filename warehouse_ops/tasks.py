from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Iterable

from .reconciliation import ReconciliationIssue, ReconciliationReport


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class TaskTransitionError(ValueError):
    """Raised when a warehouse task lifecycle transition is invalid."""


SLA_BY_SEVERITY: dict[str, timedelta] = {
    "CRITICAL": timedelta(hours=2),
    "HIGH": timedelta(hours=24),
    "MEDIUM": timedelta(hours=48),
    "LOW": timedelta(hours=120),
}


@dataclass(frozen=True, slots=True)
class WarehouseTask:
    task_id: str
    issue_code: str
    issue_message: str
    severity: str
    sku: str | None
    event_id: str | None
    location: str | None
    status: TaskStatus
    assignee: str | None
    created_at: datetime
    updated_at: datetime
    resolution_note: str | None = None

    @property
    def is_closed(self) -> bool:
        return self.status is TaskStatus.RESOLVED

    @property
    def due_at(self) -> datetime:
        """Return the SLA deadline derived from severity and creation time."""

        try:
            sla = SLA_BY_SEVERITY[self.severity.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported task severity: {self.severity}") from exc
        return self.created_at + sla

    def is_overdue(self, *, now: datetime | None = None) -> bool:
        """Return whether an unresolved task has passed its SLA deadline."""

        if self.is_closed:
            return False
        timestamp = now or _utc_now()
        if timestamp.tzinfo is None:
            raise ValueError("Overdue checks require a timezone-aware datetime.")
        return timestamp > self.due_at


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def issue_fingerprint(issue: ReconciliationIssue) -> str:
    """Return a stable key so the same reconciliation issue does not create duplicate work."""

    raw = "|".join(
        (
            issue.code,
            issue.sku or "",
            issue.event_id or "",
            issue.location or "",
            issue.message,
        )
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def create_tasks(
    report: ReconciliationReport,
    existing_tasks: Iterable[WarehouseTask] = (),
    *,
    now: datetime | None = None,
) -> tuple[WarehouseTask, ...]:
    """Create tasks for newly detected issues while preserving existing task history."""

    timestamp = now or _utc_now()
    existing = {task.task_id: task for task in existing_tasks}
    tasks = list(existing.values())

    for issue in report.prioritized_issues:
        task_id = issue_fingerprint(issue)
        if task_id in existing:
            continue
        tasks.append(
            WarehouseTask(
                task_id=task_id,
                issue_code=issue.code,
                issue_message=issue.message,
                severity=issue.severity.value,
                sku=issue.sku,
                event_id=issue.event_id,
                location=issue.location,
                status=TaskStatus.OPEN,
                assignee=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    return tuple(tasks)


def assign_task(task: WarehouseTask, assignee: str, *, now: datetime | None = None) -> WarehouseTask:
    normalized = assignee.strip()
    if not normalized:
        raise ValueError("Assignee cannot be empty.")
    if task.is_closed:
        raise TaskTransitionError("Resolved tasks cannot be reassigned.")
    return replace(task, assignee=normalized, updated_at=now or _utc_now())


def start_task(task: WarehouseTask, *, now: datetime | None = None) -> WarehouseTask:
    if task.status is not TaskStatus.OPEN:
        raise TaskTransitionError("Only open tasks can be started.")
    if not task.assignee:
        raise TaskTransitionError("Task must be assigned before it can be started.")
    return replace(task, status=TaskStatus.IN_PROGRESS, updated_at=now or _utc_now())


def resolve_task(
    task: WarehouseTask,
    resolution_note: str,
    *,
    now: datetime | None = None,
) -> WarehouseTask:
    note = resolution_note.strip()
    if task.status is not TaskStatus.IN_PROGRESS:
        raise TaskTransitionError("Only in-progress tasks can be resolved.")
    if not note:
        raise ValueError("Resolution note cannot be empty.")
    return replace(
        task,
        status=TaskStatus.RESOLVED,
        resolution_note=note,
        updated_at=now or _utc_now(),
    )
