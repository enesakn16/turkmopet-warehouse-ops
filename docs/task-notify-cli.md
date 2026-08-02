# Escalation notification preview

Use the task CLI to inspect the notifications that would be produced for currently escalated warehouse tasks:

```bash
warehouse-tasks --database warehouse-tasks.db notify --dry-run
```

The `--dry-run` flag is mandatory. The command prints console notifications only and does not contact an external provider or create delivery records.

Example output:

```text
DRY-RUN [URGENT] task=task-001 owner=warehouse-manager severity=HIGH sku=TVS-001 message=Counted stock differs from expected stock.
NOTIFICATION PREVIEW: 1 active, 0 previously delivered
```

Resolved tasks and tasks without an active escalation level are ignored. Because preview runs do not persist deliveries, repeating the command shows the current queue again and cannot suppress a later real delivery.

A real provider adapter must not be enabled until credentials, retry behavior, rate limits and failure recovery are defined. Automatic merge or external notification delivery is not part of this command.
