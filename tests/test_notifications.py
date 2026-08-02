from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest

from warehouse_ops.notifications import (
    ConsoleEscalationNotifier,
    dispatch_escalation_notifications,
)
from warehouse_ops.task_store import SQLiteTaskStore
from warehouse_ops.tasks import TaskStatus, WarehouseTask


NOW = datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc)


def _overdue_task(*, task_id: str = "task-1", overdue_hours: int = 5) -> WarehouseTask:
    created_at = NOW - timedelta(hours=24 + overdue_hours)
    return WarehouseTask(
        task_id=task_id,
        issue_code="NEGATIVE_STOCK",
        issue_message="Physical stock is below zero.",
        severity="HIGH",
        sku="SKU-1",
        event_id=None,
        location="A-01",
        status=TaskStatus.OPEN,
        assignee=None,
        created_at=created_at,
        updated_at=created_at,
    )


def test_real_console_delivery_is_persisted_and_skipped_on_repeat(tmp_path) -> None:
    stream = StringIO()
    task = _overdue_task()

    with SQLiteTaskStore(tmp_path / "warehouse.db") as store:
        notifier = ConsoleEscalationNotifier(stream=stream, dry_run=False)
        first = dispatch_escalation_notifications(
            (task,), store=store, notifier=notifier, now=NOW
        )
        second = dispatch_escalation_notifications(
            (task,), store=store, notifier=notifier, now=NOW
        )

        assert len(first.delivered) == 1
        assert first.skipped_delivery_keys == ()
        assert second.delivered == ()
        assert second.skipped_delivery_keys == ("task-1:URGENT:console",)
        assert len(store.list_deliveries()) == 1

    assert stream.getvalue().count("[URGENT]") == 1


def test_dry_run_never_suppresses_later_real_delivery(tmp_path) -> None:
    preview_stream = StringIO()
    real_stream = StringIO()
    task = _overdue_task()

    with SQLiteTaskStore(tmp_path / "warehouse.db") as store:
        preview = dispatch_escalation_notifications(
            (task,),
            store=store,
            notifier=ConsoleEscalationNotifier(stream=preview_stream),
            now=NOW,
        )
        actual = dispatch_escalation_notifications(
            (task,),
            store=store,
            notifier=ConsoleEscalationNotifier(stream=real_stream, dry_run=False),
            now=NOW,
        )

        assert len(preview.delivered) == 1
        assert store.list_deliveries() == (actual.delivered[0],)

    assert preview_stream.getvalue().startswith("DRY-RUN ")
    assert not real_stream.getvalue().startswith("DRY-RUN ")


def test_new_escalation_level_creates_a_new_delivery(tmp_path) -> None:
    task = _overdue_task(overdue_hours=5)

    with SQLiteTaskStore(tmp_path / "warehouse.db") as store:
        notifier = ConsoleEscalationNotifier(stream=StringIO(), dry_run=False)
        urgent = dispatch_escalation_notifications(
            (task,), store=store, notifier=notifier, now=NOW
        )
        critical = dispatch_escalation_notifications(
            (task,), store=store, notifier=notifier, now=NOW + timedelta(hours=20)
        )

        assert urgent.delivered[0].escalation_level.value == "URGENT"
        assert critical.delivered[0].escalation_level.value == "CRITICAL"
        assert len(store.list_deliveries()) == 2


def test_on_time_and_resolved_tasks_are_not_notified(tmp_path) -> None:
    on_time = _overdue_task(overdue_hours=-1)
    resolved = replace(on_time, task_id="resolved", status=TaskStatus.RESOLVED)

    with SQLiteTaskStore(tmp_path / "warehouse.db") as store:
        result = dispatch_escalation_notifications(
            (on_time, resolved),
            store=store,
            notifier=ConsoleEscalationNotifier(stream=StringIO(), dry_run=False),
            now=NOW,
        )

        assert result.delivered == ()
        assert store.list_deliveries() == ()


def test_dispatch_rejects_naive_time(tmp_path) -> None:
    with SQLiteTaskStore(tmp_path / "warehouse.db") as store:
        with pytest.raises(ValueError, match="timezone-aware"):
            dispatch_escalation_notifications(
                (_overdue_task(),),
                store=store,
                notifier=ConsoleEscalationNotifier(stream=StringIO()),
                now=datetime(2026, 7, 30, 9, 0),
            )
