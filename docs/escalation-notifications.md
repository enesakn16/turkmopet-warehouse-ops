# Escalation notification delivery

Escalation notifications are dispatched from the pure task escalation model. External side effects are isolated behind a notifier adapter.

## Safety rules

- Delivery identity is `(task_id, escalation_level, channel)`.
- A successful real delivery is persisted in SQLite and is not sent again.
- A task may be delivered again after it advances to a new escalation level.
- Dry-run console previews never write delivery records.
- Resolved and on-time tasks are ignored.
- All delivery timestamps must be timezone-aware.

## Dry-run preview

```python
from warehouse_ops import (
    ConsoleEscalationNotifier,
    SQLiteTaskStore,
    dispatch_escalation_notifications,
)

with SQLiteTaskStore("warehouse.db") as store:
    tasks = store.list_tasks()
    result = dispatch_escalation_notifications(
        tasks,
        store=store,
        notifier=ConsoleEscalationNotifier(),
    )
```

The default console notifier prefixes output with `DRY-RUN` and does not suppress a later real delivery.

## Recorded console delivery

```python
notifier = ConsoleEscalationNotifier(dry_run=False)
```

This mode is intended for controlled local validation of the delivery log. Production e-mail, Slack or SMS adapters should use distinct channel names and record a delivery only after the external provider confirms success.
