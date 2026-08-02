from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .notifications import ConsoleEscalationNotifier, dispatch_escalation_notifications
from .task_store import SQLiteTaskStore, TaskStoreError
from .tasks import (
    EscalationLevel,
    TaskStatus,
    TaskTransitionError,
    WarehouseTask,
    assign_task,
    resolve_task,
    start_task,
)


class _SilentEscalationNotifier:
    """Build console-compatible payloads without polluting JSON stdout."""

    channel = "console"
    dry_run = True

    def send(
        self,
        task: WarehouseTask,
        level: EscalationLevel,
        *,
        now: datetime,
    ) -> str:
        del now
        return (
            f"[{level.value}] task={task.task_id} owner={task.escalation_owner} "
            f"severity={task.severity} sku={task.sku or '-'} message={task.issue_message}"
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

    notify_parser = commands.add_parser(
        "notify",
        help="Preview active escalation notifications without external side effects",
    )
    notify_parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="Required safety flag; print notifications without recording delivery",
    )
    notify_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Preview output format (default: text)",
    )
    notify_parser.add_argument(
        "--output",
        help="Atomically replace this file with the JSON preview; requires --format json",
    )

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
    parser.add_argument(
        "--escalated",
        action="store_true",
        help="Include only overdue tasks with an active escalation level",
    )
    parser.add_argument(
        "--escalation-level",
        choices=[level.value for level in EscalationLevel if level is not EscalationLevel.NONE],
        help="Include only tasks at a specific escalation level",
    )


def _require_task(store: SQLiteTaskStore, task_id: str) -> WarehouseTask:
    task = store.get(task_id)
    if task is None:
        raise TaskStoreError(f"Task not found: {task_id}")
    return task


def _filter_tasks(
    tasks: tuple[WarehouseTask, ...],
    *,
    overdue_only: bool,
    escalated_only: bool,
    escalation_level: EscalationLevel | None,
    now: datetime,
) -> tuple[WarehouseTask, ...]:
    filtered = tasks
    if overdue_only:
        filtered = tuple(task for task in filtered if task.is_overdue(now=now))
    if escalated_only:
        filtered = tuple(
            task for task in filtered if task.escalation_level(now=now) is not EscalationLevel.NONE
        )
    if escalation_level is not None:
        filtered = tuple(
            task for task in filtered if task.escalation_level(now=now) is escalation_level
        )
    return filtered


def _overdue_hours(task: WarehouseTask, *, now: datetime) -> str:
    return f"{task.overdue_by(now=now).total_seconds() / 3600:.2f}"


def _print_tasks(tasks: tuple[WarehouseTask, ...], *, now: datetime) -> None:
    if not tasks:
        print("No tasks found.")
        return

    print(
        "task_id | status | severity | overdue | overdue_hours | escalation | "
        "escalation_owner | due_at | assignee | sku | location | issue"
    )
    for task in tasks:
        print(
            " | ".join(
                (
                    task.task_id,
                    task.status.value,
                    task.severity,
                    "yes" if task.is_overdue(now=now) else "no",
                    _overdue_hours(task, now=now),
                    task.escalation_level(now=now).value,
                    task.escalation_owner,
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
                "overdue_hours",
                "escalation_level",
                "escalation_owner",
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
                    "overdue_hours": _overdue_hours(task, now=now),
                    "escalation_level": task.escalation_level(now=now).value,
                    "escalation_owner": task.escalation_owner,
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


def _render_notification_json(
    tasks: tuple[WarehouseTask, ...],
    *,
    now: datetime,
    delivered: tuple,
    skipped_delivery_keys: tuple[str, ...],
) -> str:
    tasks_by_id = {task.task_id: task for task in tasks}
    notifications = []
    for delivery in delivered:
        task = tasks_by_id[delivery.task_id]
        notifications.append(
            {
                "task_id": delivery.task_id,
                "escalation_level": delivery.escalation_level.value,
                "escalation_owner": task.escalation_owner,
                "severity": task.severity,
                "sku": task.sku,
                "message": task.issue_message,
                "channel": delivery.channel,
                "payload": delivery.payload,
            }
        )

    document = {
        "generated_at": now.isoformat(),
        "dry_run": True,
        "format_version": 1,
        "summary": {
            "active": len(delivered),
            "previously_delivered": len(skipped_delivery_keys),
        },
        "notifications": notifications,
        "skipped_delivery_keys": list(skipped_delivery_keys),
    }
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_text_atomically(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database)

    try:
        with SQLiteTaskStore(database) as store:
            if args.command in {"list", "export"}:
                status = TaskStatus(args.status) if args.status else None
                tasks = store.list_tasks(status=status, assignee=args.assignee)
                now = datetime.now(timezone.utc)
                level = EscalationLevel(args.escalation_level) if args.escalation_level else None
                tasks = _filter_tasks(
                    tasks,
                    overdue_only=args.overdue,
                    escalated_only=args.escalated,
                    escalation_level=level,
                    now=now,
                )
                if args.command == "list":
                    _print_tasks(tasks, now=now)
                else:
                    output = Path(args.output)
                    _write_tasks_csv(tasks, output, now=now)
                    print(f"EXPORTED: {len(tasks)} tasks -> {output}")
                return 0

            if args.command == "notify":
                if args.output and args.format != "json":
                    raise ValueError("--output requires --format json")
                now = datetime.now(timezone.utc)
                tasks = store.list_tasks()
                notifier = (
                    _SilentEscalationNotifier()
                    if args.format == "json"
                    else ConsoleEscalationNotifier(dry_run=True)
                )
                result = dispatch_escalation_notifications(
                    tasks,
                    store=store,
                    notifier=notifier,
                    now=now,
                )
                if args.format == "json":
                    document = _render_notification_json(
                        tasks,
                        now=now,
                        delivered=result.delivered,
                        skipped_delivery_keys=result.skipped_delivery_keys,
                    )
                    if args.output:
                        _write_text_atomically(Path(args.output), document)
                    else:
                        print(document, end="")
                else:
                    print(
                        "NOTIFICATION PREVIEW: "
                        f"{len(result.delivered)} active, "
                        f"{len(result.skipped_delivery_keys)} previously delivered"
                    )
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
