from __future__ import annotations

import argparse
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
        description="List and update persisted warehouse reconciliation tasks.",
    )
    parser.add_argument(
        "--database",
        default="warehouse-tasks.db",
        help="SQLite database path (default: warehouse-tasks.db)",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List persisted warehouse tasks")
    list_parser.add_argument("--status", choices=[status.value for status in TaskStatus])
    list_parser.add_argument("--assignee", help="Filter tasks by assignee")

    assign_parser = commands.add_parser("assign", help="Assign an open task")
    assign_parser.add_argument("task_id")
    assign_parser.add_argument("assignee")

    start_parser = commands.add_parser("start", help="Start an assigned task")
    start_parser.add_argument("task_id")

    resolve_parser = commands.add_parser("resolve", help="Resolve an in-progress task")
    resolve_parser.add_argument("task_id")
    resolve_parser.add_argument("--note", required=True, help="Resolution note")

    return parser


def _require_task(store: SQLiteTaskStore, task_id: str) -> WarehouseTask:
    task = store.get(task_id)
    if task is None:
        raise TaskStoreError(f"Task not found: {task_id}")
    return task


def _print_tasks(tasks: tuple[WarehouseTask, ...]) -> None:
    if not tasks:
        print("No tasks found.")
        return

    print("task_id | status | severity | assignee | sku | location | issue")
    for task in tasks:
        print(
            " | ".join(
                (
                    task.task_id,
                    task.status.value,
                    task.severity,
                    task.assignee or "-",
                    task.sku or "-",
                    task.location or "-",
                    task.issue_message,
                )
            )
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database)

    try:
        with SQLiteTaskStore(database) as store:
            if args.command == "list":
                status = TaskStatus(args.status) if args.status else None
                tasks = store.list_tasks(status=status, assignee=args.assignee)
                _print_tasks(tasks)
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
    except (TaskStoreError, TaskTransitionError, ValueError) as exc:
        print(f"Task operation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
