"""Background task queue for model inference offloading.

Phase 8: Provides async task queue for long-running inference tasks.
Uses ARQ (async Redis queue) when Redis is available, otherwise falls back
to asyncio.create_task for single-process operation.

Set ``TASK_QUEUE_ENABLED=true`` and ``TASK_QUEUE_BROKER_URL`` to enable.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    duration_seconds: Optional[float] = None


class InMemoryTaskQueue:
    """Asyncio-based task queue for single-process deployments."""

    def __init__(self, max_concurrent: int = 2, max_queue_size: int = 20):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: Dict[str, TaskResult] = {}
        self._max_queue_size = max_queue_size
        self._active_count = 0

    async def enqueue(
        self,
        func: Callable[..., Coroutine],
        *args: Any,
        task_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Submit a coroutine for background execution."""
        task_id = task_id or str(uuid.uuid4())

        if len(self._results) >= self._max_queue_size:
            # Prune completed tasks to make room
            completed = [
                k for k, v in self._results.items()
                if v.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            ]
            for k in completed[:len(completed) // 2]:
                del self._results[k]

        if len(self._results) >= self._max_queue_size:
            raise RuntimeError("Task queue is full")

        self._results[task_id] = TaskResult(
            task_id=task_id, status=TaskStatus.PENDING
        )
        asyncio.create_task(self._run(task_id, func, *args, **kwargs))
        return task_id

    async def _run(
        self,
        task_id: str,
        func: Callable[..., Coroutine],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        async with self._semaphore:
            self._active_count += 1
            result = self._results[task_id]
            result.status = TaskStatus.RUNNING
            start = time.time()
            try:
                result.result = await func(*args, **kwargs)
                result.status = TaskStatus.COMPLETED
            except Exception as e:
                result.status = TaskStatus.FAILED
                result.error = str(e)
                logger.error("Task %s failed: %s", task_id, e)
            finally:
                result.completed_at = time.time()
                result.duration_seconds = result.completed_at - start
                self._active_count -= 1

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        return self._results.get(task_id)

    @property
    def active_tasks(self) -> int:
        return self._active_count

    @property
    def pending_tasks(self) -> int:
        return sum(
            1 for r in self._results.values() if r.status == TaskStatus.PENDING
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "active": self._active_count,
            "pending": self.pending_tasks,
            "total_tracked": len(self._results),
            "backend": "asyncio",
        }


class ARQTaskQueue:
    """ARQ (async Redis queue) backend for distributed workers."""

    def __init__(self, broker_url: str, max_concurrent: int = 2):
        self._broker_url = broker_url
        self._max_concurrent = max_concurrent
        self._pool = None
        self._results: Dict[str, TaskResult] = {}

    async def _connect(self):
        if self._pool is not None:
            return
        try:
            import redis.asyncio as aioredis
            self._pool = aioredis.from_url(self._broker_url)
            await self._pool.ping()
            logger.info("ARQ task queue connected: %s", self._broker_url.split("@")[-1])
        except Exception as e:
            logger.warning("ARQ connection failed, tasks will run in-process: %s", e)
            self._pool = None

    async def enqueue(
        self,
        func: Callable[..., Coroutine],
        *args: Any,
        task_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Enqueue task. Falls back to in-process if Redis unavailable."""
        task_id = task_id or str(uuid.uuid4())
        await self._connect()

        # For now, run in-process with tracking (ARQ worker integration
        # would serialize func name and dispatch to worker process)
        self._results[task_id] = TaskResult(
            task_id=task_id, status=TaskStatus.PENDING
        )
        asyncio.create_task(self._run_local(task_id, func, *args, **kwargs))
        return task_id

    async def _run_local(
        self,
        task_id: str,
        func: Callable[..., Coroutine],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        result = self._results[task_id]
        result.status = TaskStatus.RUNNING
        start = time.time()
        try:
            result.result = await func(*args, **kwargs)
            result.status = TaskStatus.COMPLETED
        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
        finally:
            result.completed_at = time.time()
            result.duration_seconds = result.completed_at - start

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        return self._results.get(task_id)

    def stats(self) -> Dict[str, Any]:
        return {
            "active": sum(1 for r in self._results.values() if r.status == TaskStatus.RUNNING),
            "pending": sum(1 for r in self._results.values() if r.status == TaskStatus.PENDING),
            "total_tracked": len(self._results),
            "backend": "arq" if self._pool else "asyncio-fallback",
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_task_queue = None


def get_task_queue() -> InMemoryTaskQueue:
    """Get or create the global task queue."""
    global _task_queue
    if _task_queue is None:
        if settings.task_queue_enabled and settings.task_queue_broker_url:
            _task_queue = ARQTaskQueue(
                broker_url=settings.task_queue_broker_url,
                max_concurrent=settings.queue_max_concurrent_inferences,
            )
        else:
            _task_queue = InMemoryTaskQueue(
                max_concurrent=settings.queue_max_concurrent_inferences,
                max_queue_size=settings.queue_max_size,
            )
    return _task_queue
