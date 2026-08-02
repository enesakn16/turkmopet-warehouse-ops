# Escalation boundary contract

Warehouse task escalation is calculated from the elapsed time after the task's SLA deadline.

| Overdue duration | Escalation level |
|---|---|
| Not overdue | `NONE` |
| More than 0 and less than 4 hours | `WATCH` |
| 4 hours through exactly 24 hours | `URGENT` |
| More than 24 hours | `CRITICAL` |

The boundary distinction is intentional: exactly four hours must enter the urgent queue, while exactly twenty-four hours remains urgent until the duration exceeds twenty-four hours.

All calculations require timezone-aware timestamps. Resolved tasks always return `NONE` and have no active overdue duration.
