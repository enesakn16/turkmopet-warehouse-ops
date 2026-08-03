from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .reconciliation import ReconciliationReport
from .routing import route_issue
from .task_store import SQLiteTaskStore
from .tasks import WarehouseTask, assign_task, create_tasks, issue_fingerprint


@dataclass(frozen=True, slots=True)
class TaskSyncResult:
    """Describe the result of synchronizing reconciliation issues into task storage."""

    created_tasks: tuple[WarehouseTask, ...]
    existing_tasks: tuple[WarehouseTask, ...]

    @property
    def created_count(self) -> int:
        return len(self.created_tasks)

    @property
    def existing_count(self) -> int:
        return len(self.existing_tasks)

    @property
    def total_count(self) -> int:
        return self.created_count + self.existing_count


def sync_reconciliation_tasks(
    report: ReconciliationReport,
    store: SQLiteTaskStore,
    *,
    now: datetime | None = None,
) -> TaskSyncResult:
    """Persist and route newly detected issues without overwriting task history.

    Existing tasks are loaded before new tasks are generated. Only newly created
    tasks are routed and written back, so a manual assignment, status and
    resolution history remain untouched when the same issue appears again.
    """

    existing_tasks = store.list_tasks()
    existing_ids = {task.task_id for task in existing_tasks}
    synchronized = create_tasks(report, existing_tasks=existing_tasks, now=now)
    issue_by_task_id = {issue_fingerprint(issue): issue for issue in report.prioritized_issues}

    created_tasks = tuple(
        assign_task(task, route_issue(issue_by_task_id[task.task_id]), now=now)
        for task in synchronized
        if task.task_id not in existing_ids
    )

    if created_tasks:
        store.save_all(created_tasks)

    return TaskSyncResult(
        created_tasks=created_tasks,
        existing_tasks=existing_tasks,
    )
