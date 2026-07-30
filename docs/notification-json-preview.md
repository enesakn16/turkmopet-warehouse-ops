# Notification JSON preview contract

`warehouse-tasks notify` remains a preview-only command and requires the explicit `--dry-run` safety flag. Machine consumers can request JSON without parsing terminal text:

```bash
warehouse-tasks \
  --database warehouse-tasks.db \
  notify \
  --dry-run \
  --format json
```

The command writes one valid JSON document to standard output. It does not contact an external service and does not create an escalation delivery record.

## Contract

```json
{
  "dry_run": true,
  "format_version": 1,
  "generated_at": "2026-07-26T17:00:00+00:00",
  "notifications": [
    {
      "channel": "console",
      "escalation_level": "URGENT",
      "escalation_owner": "warehouse-manager",
      "message": "Counted stock differs from expected stock.",
      "payload": "[URGENT] task=task-001 owner=warehouse-manager severity=HIGH sku=TVS-001 message=Counted stock differs from expected stock.",
      "severity": "HIGH",
      "sku": "TVS-001",
      "task_id": "task-001"
    }
  ],
  "skipped_delivery_keys": [],
  "summary": {
    "active": 1,
    "previously_delivered": 0
  }
}
```

Rules:

- `format_version` changes only when the machine-readable schema becomes incompatible.
- `generated_at` is an offset-aware ISO 8601 timestamp.
- `notifications` contains only currently active escalation previews.
- `skipped_delivery_keys` contains task/level/channel keys already recorded as delivered.
- `summary.active` equals the number of notification objects.
- `summary.previously_delivered` equals the number of skipped delivery keys.
- `dry_run` is always `true` for this command.
- Repeated previews return active notifications again because previews never persist delivery state.

The default `--format text` output remains available for warehouse operators.