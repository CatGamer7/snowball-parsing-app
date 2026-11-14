from datetime import datetime, timezone
from itertools import islice
from threading import Lock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from vk.models import VKPost


class CollectionFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["ML_NOT_AVAILABLE", "ML_ERROR", "VK_ERROR", "INTERNAL_ERROR"]
    message: str


class CollectionProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    collection_id: str
    status: Literal["queued", "running", "completed", "failed"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    records_count: int = Field(default=0, ge=0)
    expansion_level: int = Field(default=0, ge=0)
    selected_entities_count: int = Field(default=0, ge=0)
    vk_requests_count: int = Field(default=0, ge=0)
    error: CollectionFailure | None = None
    stop_reason: Literal[
        "max_depth", "no_text_records", "no_new_entities", "no_new_records", "record_limit"
    ] | None = None


class CollectionRecords(BaseModel):
    collection_id: str
    total: int
    offset: int
    limit: int
    items: list[VKPost]


class CollectionJobStore:
    """Состояния заданий в памяти одного процесса бэкенда."""

    def __init__(self):
        self._jobs: dict[str, CollectionProgress] = {}
        self._lock = Lock()
        self._records: dict[str, dict[str, VKPost]] = {}

    def create(self, vk_requests_count: int = 0) -> CollectionProgress:
        job = CollectionProgress(
            collection_id=str(uuid4()),
            status="queued",
            vk_requests_count=vk_requests_count,
        )

        with self._lock:
            self._jobs[job.collection_id] = job
            self._records[job.collection_id] = {}

        return job.model_copy(deep=True)

    def get(self, collection_id: str) -> CollectionProgress | None:
        with self._lock:
            job = self._jobs.get(collection_id)
            return job.model_copy(deep=True) if job is not None else None

    def start(self, collection_id: str) -> None:
        with self._lock:
            job = self._jobs[collection_id]
            if job.status != "queued":
                raise ValueError("Задание уже запущено или завершено")

            self._jobs[collection_id] = job.model_copy(
                update={
                    "status": "running",
                    "started_at": datetime.now(timezone.utc),
                }
            )

    def update_counts(
        self,
        collection_id: str,
        *,
        records_count: int,
        expansion_level: int,
        selected_entities_count: int,
        vk_requests_count: int,
    ) -> None:
        values = {
            "records_count": records_count,
            "expansion_level": expansion_level,
            "selected_entities_count": selected_entities_count,
            "vk_requests_count": vk_requests_count,
        }

        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError("Счётчики должны быть неотрицательными целыми числами")

        with self._lock:
            job = self._jobs[collection_id]
            if job.status != "running":
                raise ValueError("Обновлять можно только выполняющееся задание")

            self._jobs[collection_id] = job.model_copy(update=values)

    def add_records(self, collection_id: str, posts: list[VKPost], *, limit: int) -> None:
        with self._lock:
            job = self._jobs[collection_id]
            if job.status != "running":
                raise ValueError("Добавлять записи можно только в выполняющееся задание")
            records = self._records[collection_id]
            for post in posts:
                if not isinstance(post, VKPost):
                    raise TypeError("Ожидался пост VK")
                if len(records) >= limit:
                    break
                if post.text.strip():
                    records.setdefault(post.key, post.model_copy(deep=True))
            self._jobs[collection_id] = job.model_copy(update={"records_count": len(records)})

    def get_records(
        self, collection_id: str, *, offset: int, limit: int,
    ) -> tuple[int, list[VKPost]] | None:
        with self._lock:
            if collection_id not in self._jobs:
                return None
            records = self._records[collection_id]
            page = list(islice(records.values(), offset, offset + limit))
            return len(records), [post.model_copy(deep=True) for post in page]

    def finish(
        self,
        collection_id: str,
        error: CollectionFailure | None = None,
        *,
        stop_reason: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[collection_id]
            if job.status != "running":
                raise ValueError("Завершать можно только выполняющееся задание")

            self._jobs[collection_id] = job.model_copy(
                update={
                    "status": "failed" if error is not None else "completed",
                    "finished_at": datetime.now(timezone.utc),
                    "error": error,
                    "stop_reason": stop_reason,
                }
            )


job_store = CollectionJobStore()
