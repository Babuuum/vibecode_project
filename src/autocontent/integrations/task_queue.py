from __future__ import annotations

from abc import ABC, abstractmethod


class TaskQueue(ABC):
    @abstractmethod
    def enqueue_generate_draft(self, source_item_id: int) -> None:
        raise NotImplementedError


class CeleryTaskQueue(TaskQueue):
    def enqueue_generate_draft(self, source_item_id: int) -> None:
        from autocontent.worker.tasks import generate_draft_task

        generate_draft_task.delay(source_item_id)
