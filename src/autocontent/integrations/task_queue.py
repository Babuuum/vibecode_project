from __future__ import annotations

from abc import ABC, abstractmethod


class TaskQueue(ABC):
    @abstractmethod
    def enqueue_generate_draft(self, source_item_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_publish_draft(self, draft_id: int) -> None:
        raise NotImplementedError

class CeleryTaskQueue(TaskQueue):
    def enqueue_generate_draft(self, source_item_id: int) -> None:
        from src.autocontent.worker.tasks import generate_draft_task

        generate_draft_task.delay(source_item_id)

    def enqueue_publish_draft(self, draft_id: int) -> None:
        from src.autocontent.worker.tasks import publish_draft_task

        publish_draft_task.delay(draft_id)
