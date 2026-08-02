from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .notifications import NotificationDelivery
from .tasks import EscalationLevel, TaskStatus, WarehouseTask


class TaskStoreError(RuntimeError):
    """Raised when persisted warehouse task data cannot be read safely."""


class SQLiteTaskStore:
    """Persist warehouse task state using the Python standard-library SQLite driver."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self._connection = sqlite3.connect(self.database)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def __enter__(self) -> "SQLiteTaskStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS warehouse_tasks (
                    task_id TEXT PRIMARY KEY,
                    issue_code TEXT NOT NULL,
                    issue_message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    sku TEXT,
                    event_id TEXT,
                    location TEXT,
                    status TEXT NOT NULL CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
                    assignee TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    resolution_note TEXT
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_warehouse_tasks_status ON warehouse_tasks(status)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_warehouse_tasks_assignee ON warehouse_tasks(assignee)"
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS escalation_deliveries (
                    task_id TEXT NOT NULL,
                    escalation_level TEXT NOT NULL
                        CHECK (escalation_level IN ('WATCH', 'URGENT', 'CRITICAL')),
                    channel TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (task_id, escalation_level, channel)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_escalation_deliveries_delivered_at
                ON escalation_deliveries(delivered_at)
                """
            )

    def save(self, task: WarehouseTask) -> None:
        """Insert or update a task without losing its immutable creation timestamp."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO warehouse_tasks (
                    task_id, issue_code, issue_message, severity, sku, event_id,
                    location, status, assignee, created_at, updated_at, resolution_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    issue_code = excluded.issue_code,
                    issue_message = excluded.issue_message,
                    severity = excluded.severity,
                    sku = excluded.sku,
                    event_id = excluded.event_id,
                    location = excluded.location,
                    status = excluded.status,
                    assignee = excluded.assignee,
                    updated_at = excluded.updated_at,
                    resolution_note = excluded.resolution_note
                """,
                self._serialize(task),
            )

    def save_all(self, tasks: Iterable[WarehouseTask]) -> None:
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO warehouse_tasks (
                    task_id, issue_code, issue_message, severity, sku, event_id,
                    location, status, assignee, created_at, updated_at, resolution_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    issue_code = excluded.issue_code,
                    issue_message = excluded.issue_message,
                    severity = excluded.severity,
                    sku = excluded.sku,
                    event_id = excluded.event_id,
                    location = excluded.location,
                    status = excluded.status,
                    assignee = excluded.assignee,
                    updated_at = excluded.updated_at,
                    resolution_note = excluded.resolution_note
                """,
                [self._serialize(task) for task in tasks],
            )

    def get(self, task_id: str) -> WarehouseTask | None:
        row = self._connection.execute(
            "SELECT * FROM warehouse_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return self._deserialize(row) if row else None

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        assignee: str | None = None,
    ) -> tuple[WarehouseTask, ...]:
        clauses: list[str] = []
        parameters: list[str] = []

        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if assignee is not None:
            clauses.append("assignee = ?")
            parameters.append(assignee)

        query = "SELECT * FROM warehouse_tasks"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC, task_id ASC"

        rows = self._connection.execute(query, parameters).fetchall()
        return tuple(self._deserialize(row) for row in rows)

    def has_delivery(
        self,
        task_id: str,
        escalation_level: EscalationLevel,
        channel: str,
    ) -> bool:
        row = self._connection.execute(
            """
            SELECT 1 FROM escalation_deliveries
            WHERE task_id = ? AND escalation_level = ? AND channel = ?
            """,
            (task_id, escalation_level.value, channel),
        ).fetchone()
        return row is not None

    def record_delivery(self, delivery: NotificationDelivery) -> None:
        """Persist a successful delivery once for its task, level and channel."""

        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO escalation_deliveries (
                        task_id, escalation_level, channel, delivered_at, payload
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        delivery.task_id,
                        delivery.escalation_level.value,
                        delivery.channel,
                        delivery.delivered_at.isoformat(),
                        delivery.payload,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise TaskStoreError(
                "Escalation delivery already exists or contains invalid data."
            ) from exc

    def list_deliveries(self) -> tuple[NotificationDelivery, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM escalation_deliveries
            ORDER BY delivered_at ASC, task_id ASC
            """
        ).fetchall()
        try:
            return tuple(
                NotificationDelivery(
                    task_id=row["task_id"],
                    escalation_level=EscalationLevel(row["escalation_level"]),
                    channel=row["channel"],
                    delivered_at=datetime.fromisoformat(row["delivered_at"]),
                    payload=row["payload"],
                )
                for row in rows
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskStoreError("Stored escalation delivery data is invalid.") from exc

    @staticmethod
    def _serialize(task: WarehouseTask) -> tuple[object, ...]:
        return (
            task.task_id,
            task.issue_code,
            task.issue_message,
            task.severity,
            task.sku,
            task.event_id,
            task.location,
            task.status.value,
            task.assignee,
            task.created_at.isoformat(),
            task.updated_at.isoformat(),
            task.resolution_note,
        )

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> WarehouseTask:
        try:
            return WarehouseTask(
                task_id=row["task_id"],
                issue_code=row["issue_code"],
                issue_message=row["issue_message"],
                severity=row["severity"],
                sku=row["sku"],
                event_id=row["event_id"],
                location=row["location"],
                status=TaskStatus(row["status"]),
                assignee=row["assignee"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                resolution_note=row["resolution_note"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskStoreError("Stored warehouse task data is invalid.") from exc
