from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from .task_store import SQLiteTaskStore, TaskStoreError
from .tasks import (
    TaskStatus,
    TaskTransitionError,
    WarehouseTask,
    assign_task,
    resolve_task,
    start_task,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warehouse-tasks",
        description="List, export and update persisted warehouse reconciliation tasks.",
    )
    parser.add_argument(
        "--database",
        default="warehouse-tasks.db",
        help="SQLite database path (default: warehouse-tasks.db)",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List persisted warehouse tasks")
    _add_task_filters(list_parser)

    export_parser = commands.add_parser(
        "export",
        help="Export persisted warehouse tasks as an Excel-friendly CSV file",
    )
    export_parser.add_argument("output", help="Destination CSV path")
    _add_task_filters(export_parser)

    assign_parser = commands.add_parser("assign", help="Assign an open task")
    assign_parser.add_argument("task_id")
    assign_parser.add_argument("assignee")

    start_parser = commands.add_parser("start", help="Start an assigned task")
    start_parser.add_argument("task_id")

    resolve_parser = commands.add_parser("resolve", help="Resolve an in-progress task")
    resolve_parser.add_argument("task_id")
    resolve_parser.add_argument("--note", required=True, help="Resolution note")

    return parser


def _add_task_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", choices=[status.value for status in TaskStatus])
    parser.add_argument("--assignee", help="Filter tasks by assignee")
    parser.add_argument(
        "--overdue",
        action="store_true",
        help="Include only unresolved tasks that have exceeded their severity SLA",
    )


def _require_task(store: SQLiteTaskStore, task_id: str) -> WarehouseTask:
    task = store.get(task_id)
    if task is None:
        raise TaskStoreError(f"Task not found: {task_id}")
    return task


def _filter_overdue(
    tasks: tuple[WarehouseTask, ...],
    *,
    overdue_only: bool,
    now: datetime,
) -> tuple[WarehouseTask, ...]:
    if not overdue_only:
        return tasks
    return tuple(task for task in tasks if task.is_overdue(now=now))


def _print_tasks(tasks: tuple[WarehouseTask, ...], *, now: datetime) -> None:
    if not tasks:
        print("No tasks found.")
        return

    print("task_id | status | severity | overdue | due_at | assignee | sku | location | issue")
    for task in tasks:
        print(
            " | ".join(
                (
                    task.task_id,
                    task.status.value,
                    task.severity,
                    "yes" if task.is_overdue(now=now) else "no",
                    task.due_at.isoformat(),
                    task.assignee or "-",
                    task.sku or "-",
                    task.location or "-",
                    task.issue_message,
                )
            )
        )


def _write_tasks_csv(
    tasks: tuple[WarehouseTask, ...],
    output: Path,
    *,
    now: datetime,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "task_id",
                "status",
                "severity",
                "due_at",
                "is_overdue",
                "issue_code",
                "issue_message",
                "sku",
                "event_id",
                "location",
                "assignee",
                "created_at",
                "updated_at",
                "resolution_note",
            ),
        )
        writer.writeheader()
        for task in tasks:
            writer.writerow(
                {
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "severity": task.severity,
                    "due_at": task.due_at.isoformat(),
                    "is_overdue": "yes" if task.is_overdue(now=now) else "no",
                    "issue_code": task.issue_code,
                    "issue_message": task.issue_message,
                    "sku": task.sku or "",
                    "event_id": task.event_id or "",
                    "location": task.location or "",
                    "assignee": task.assignee or "",
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                    "resolution_note": task.resolution_note or "",
                }
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database)

    try:
        with SQLiteTaskStore(database) as store:
            if args.command in {"list", "export"}:
                status = TaskStatus(args.status) if args.status else None
                tasks = store.list_tasks(status=status, assignee=args.assignee)
                now = datetime.now(timezone.utc)
                tasks = _filter_overdue(tasks, overdue_only=args.overdue, now=now)
                if args.command == "list":
                    _print_tasks(tasks, now=now)
                else:
                    output = Path(args.output)
                    _write_tasks_csv(tasks, output, now=now)
                    print(f"EXPORTED: {len(tasks)} tasks -> {output}")
                return 0

            task = _require_task(store, args.task_id)
            if args.command == "assign":
                updated = assign_task(task, args.assignee)
            elif args.command == "start":
                updated = start_task(task)
            elif args.command == "resolve":
                updated = resolve_task(task, args.note)
            else:  # pragma: no cover - argparse prevents this path
                raise RuntimeError(f"Unsupported command: {args.command}")

            store.save(updated)
            print(
                f"UPDATED: {updated.task_id} -> {updated.status.value}"
                f" (assignee: {updated.assignee or '-'})"
            )
            return 0
    except (OSError, TaskStoreError, TaskTransitionError, ValueError) as exc:
        print(f"Task operation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
