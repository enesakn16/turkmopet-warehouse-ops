from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from warehouse_ops.task_store import SQLiteTaskStore
from warehouse_ops.tasks import TaskStatus, WarehouseTask


CREATED = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)
UPDATED = datetime(2026, 7, 25, 7, 0, tzinfo=timezone.utc)


class SQLiteTaskStoreTests(unittest.TestCase):
    def _task(
        self,
        *,
        task_id: str = "task-1",
        status: TaskStatus = TaskStatus.OPEN,
        assignee: str | None = None,
        resolution_note: str | None = None,
        updated_at: datetime = CREATED,
    ) -> WarehouseTask:
        return WarehouseTask(
            task_id=task_id,
            issue_code="STOCK_VARIANCE",
            issue_message="Physical count differs from expected stock by -4.",
            severity="MEDIUM",
            sku="TVS-FILTER-01",
            event_id=None,
            location="Zemin / A-12",
            status=status,
            assignee=assignee,
            created_at=CREATED,
            updated_at=updated_at,
            resolution_note=resolution_note,
        )

    def test_persists_and_reloads_task_after_reopening_database(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "warehouse.db"
            with SQLiteTaskStore(database) as store:
                store.save(self._task())

            with SQLiteTaskStore(database) as reopened:
                loaded = reopened.get("task-1")

            self.assertEqual(self._task(), loaded)

    def test_updates_mutable_fields_without_overwriting_created_at(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "warehouse.db"
            with SQLiteTaskStore(database) as store:
                store.save(self._task())
                store.save(
                    self._task(
                        status=TaskStatus.IN_PROGRESS,
                        assignee="Enes",
                        updated_at=UPDATED,
                    )
                )
                loaded = store.get("task-1")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(CREATED, loaded.created_at)
            self.assertEqual(UPDATED, loaded.updated_at)
            self.assertEqual(TaskStatus.IN_PROGRESS, loaded.status)
            self.assertEqual("Enes", loaded.assignee)

    def test_filters_tasks_by_status_and_assignee(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "warehouse.db"
            with SQLiteTaskStore(database) as store:
                store.save_all(
                    (
                        self._task(task_id="open-enes", assignee="Enes"),
                        self._task(
                            task_id="progress-enes",
                            status=TaskStatus.IN_PROGRESS,
                            assignee="Enes",
                            updated_at=UPDATED,
                        ),
                        self._task(task_id="open-team", assignee="Depo"),
                    )
                )

                open_tasks = store.list_tasks(status=TaskStatus.OPEN)
                enes_tasks = store.list_tasks(assignee="Enes")
                active_enes = store.list_tasks(
                    status=TaskStatus.IN_PROGRESS,
                    assignee="Enes",
                )

            self.assertEqual({"open-enes", "open-team"}, {task.task_id for task in open_tasks})
            self.assertEqual({"open-enes", "progress-enes"}, {task.task_id for task in enes_tasks})
            self.assertEqual(("progress-enes",), tuple(task.task_id for task in active_enes))

    def test_returns_none_for_unknown_task(self) -> None:
        with TemporaryDirectory() as directory:
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                self.assertIsNone(store.get("missing"))


if __name__ == "__main__":
    unittest.main()
