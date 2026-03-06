"""
API Rate Limiting & Inference Queue System

Provides:
- Per-user/IP sliding window rate limiting
- Async inference queue with concurrency control (semaphore-based)
- Queue position tracking and estimated wait time
"""

import asyncio
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)


# =====================================================
# SLIDING WINDOW RATE LIMITER
# =====================================================

class SlidingWindowRateLimiter:
    """Per-key sliding window rate limiter using in-memory timestamps."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, dict]:
        """
        Check if a request is allowed for the given key.

        Returns:
            (allowed, info) where info contains rate limit headers data.
        """
        now = time.monotonic()
        async with self._lock:
            timestamps = self._requests[key]
            cutoff = now - self.window_seconds
            # Prune expired timestamps
            self._requests[key] = [t for t in timestamps if t > cutoff]
            timestamps = self._requests[key]

            remaining = max(0, self.max_requests - len(timestamps))
            reset_at = (timestamps[0] + self.window_seconds - now) if timestamps else self.window_seconds

            if len(timestamps) >= self.max_requests:
                return False, {
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at)),
                    "Retry-After": str(int(reset_at) + 1),
                }

            timestamps.append(now)
            return True, {
                "X-RateLimit-Limit": str(self.max_requests),
                "X-RateLimit-Remaining": str(remaining - 1),
                "X-RateLimit-Reset": str(int(self.window_seconds)),
            }

    async def cleanup(self):
        """Remove stale entries to prevent memory leaks."""
        now = time.monotonic()
        async with self._lock:
            stale_keys = [
                k for k, v in self._requests.items()
                if not v or v[-1] < now - self.window_seconds
            ]
            for k in stale_keys:
                del self._requests[k]


# =====================================================
# INFERENCE QUEUE
# =====================================================

@dataclass
class QueueTicket:
    """Represents a queued inference request."""
    id: str
    created_at: float = field(default_factory=time.monotonic)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False


class InferenceQueue:
    """
    Async inference queue with semaphore-based concurrency control.

    - Limits concurrent model inference to `max_concurrent` slots.
    - Queues excess requests and tracks their position.
    - Provides estimated wait time based on recent completion times.
    """

    def __init__(self, max_concurrent: int, max_queue_size: int):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._waiting: list[QueueTicket] = []
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._recent_durations: list[float] = []
        self._counter = 0

    @property
    def avg_inference_time(self) -> float:
        if not self._recent_durations:
            return settings.queue_estimated_inference_seconds
        return sum(self._recent_durations) / len(self._recent_durations)

    def _record_duration(self, duration: float):
        self._recent_durations.append(duration)
        # Keep only last N measurements
        if len(self._recent_durations) > 50:
            self._recent_durations = self._recent_durations[-50:]

    async def get_status(self) -> dict:
        async with self._lock:
            return {
                "active_inferences": self._active_count,
                "max_concurrent": self.max_concurrent,
                "queue_length": len(self._waiting),
                "max_queue_size": self.max_queue_size,
                "avg_inference_seconds": round(self.avg_inference_time, 2),
            }

    async def acquire(self, request_id: str, timeout: Optional[float] = None) -> dict:
        """
        Acquire an inference slot, waiting in queue if necessary.

        Returns:
            dict with queue position info (position 0 means running now).

        Raises:
            HTTPException 429 if queue is full.
            HTTPException 408 if wait times out.
        """
        timeout = timeout or settings.queue_timeout_seconds

        # Try to acquire immediately
        if self._semaphore._value > 0:
            await self._semaphore.acquire()
            async with self._lock:
                self._active_count += 1
            return {"position": 0, "estimated_wait_seconds": 0}

        # Check queue capacity
        async with self._lock:
            if len(self._waiting) >= self.max_queue_size:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Queue full. Please try again later.",
                        "queue_length": len(self._waiting),
                        "max_queue_size": self.max_queue_size,
                        "retry_after_seconds": int(self.avg_inference_time),
                    },
                )

            ticket = QueueTicket(id=request_id)
            self._waiting.append(ticket)
            position = len(self._waiting)
            estimated_wait = round(position * self.avg_inference_time, 1)

        logger.info(f"Request {request_id} queued at position {position}")

        # Wait for our turn
        try:
            acquired = False
            start_wait = time.monotonic()

            while not acquired:
                remaining_timeout = timeout - (time.monotonic() - start_wait)
                if remaining_timeout <= 0:
                    break

                try:
                    await asyncio.wait_for(
                        self._semaphore.acquire(),
                        timeout=min(remaining_timeout, 2.0),
                    )
                    acquired = True
                except asyncio.TimeoutError:
                    if ticket.cancelled:
                        raise HTTPException(
                            status_code=status.HTTP_408_REQUEST_TIMEOUT,
                            detail="Request cancelled.",
                        )
                    continue

            if not acquired:
                async with self._lock:
                    if ticket in self._waiting:
                        self._waiting.remove(ticket)
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail={
                        "error": "Queue wait timeout exceeded.",
                        "waited_seconds": round(time.monotonic() - start_wait, 1),
                    },
                )

            async with self._lock:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                self._active_count += 1

            wait_time = round(time.monotonic() - start_wait, 2)
            logger.info(f"Request {request_id} acquired slot after {wait_time}s wait")
            return {"position": 0, "estimated_wait_seconds": 0, "waited_seconds": wait_time}

        except HTTPException:
            raise
        except Exception as e:
            async with self._lock:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
            raise

    async def release(self, duration: Optional[float] = None):
        """Release an inference slot back to the pool."""
        self._semaphore.release()
        async with self._lock:
            self._active_count = max(0, self._active_count - 1)
        if duration is not None:
            self._record_duration(duration)

    async def get_position(self, request_id: str) -> Optional[dict]:
        """Get current queue position for a request."""
        async with self._lock:
            for i, ticket in enumerate(self._waiting):
                if ticket.id == request_id:
                    position = i + 1
                    return {
                        "position": position,
                        "estimated_wait_seconds": round(position * self.avg_inference_time, 1),
                        "queue_length": len(self._waiting),
                    }
        return None


# =====================================================
# GLOBAL INSTANCES
# =====================================================

# Rate limiters for different endpoint tiers
_general_limiter: Optional[SlidingWindowRateLimiter] = None
_inference_limiter: Optional[SlidingWindowRateLimiter] = None
_inference_queue: Optional[InferenceQueue] = None
_cleanup_task: Optional[asyncio.Task] = None


def get_general_limiter() -> SlidingWindowRateLimiter:
    global _general_limiter
    if _general_limiter is None:
        _general_limiter = SlidingWindowRateLimiter(
            max_requests=settings.rate_limit_general_rpm,
            window_seconds=60,
        )
    return _general_limiter


def get_inference_limiter() -> SlidingWindowRateLimiter:
    global _inference_limiter
    if _inference_limiter is None:
        _inference_limiter = SlidingWindowRateLimiter(
            max_requests=settings.rate_limit_inference_rpm,
            window_seconds=60,
        )
    return _inference_limiter


def get_inference_queue() -> InferenceQueue:
    global _inference_queue
    if _inference_queue is None:
        _inference_queue = InferenceQueue(
            max_concurrent=settings.queue_max_concurrent_inferences,
            max_queue_size=settings.queue_max_size,
        )
    return _inference_queue


def _get_rate_limit_key(request: Request) -> str:
    """Derive a rate limit key from the authenticated user or client IP."""
    user = getattr(request.state, "current_user", None)
    if user and hasattr(user, "id"):
        return f"user:{user.id}"
    if request.client:
        return f"ip:{request.client.host}"
    return "anonymous"


async def check_rate_limit(request: Request, tier: str = "general") -> dict:
    """
    Check rate limit for the current request.

    Args:
        request: The FastAPI request.
        tier: "general" or "inference".

    Returns:
        Rate limit header info dict.

    Raises:
        HTTPException 429 if rate limit exceeded.
    """
    if not settings.rate_limiting_enabled:
        return {}

    key = _get_rate_limit_key(request)
    limiter = get_inference_limiter() if tier == "inference" else get_general_limiter()

    allowed, info = await limiter.check(key)
    if not allowed:
        logger.warning(f"Rate limit exceeded for {key} on tier={tier}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded. Please slow down.",
                "retry_after_seconds": int(info.get("Retry-After", 60)),
            },
            headers=info,
        )
    return info


async def _periodic_cleanup():
    """Background task to clean up stale rate limiter entries."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            if _general_limiter:
                await _general_limiter.cleanup()
            if _inference_limiter:
                await _inference_limiter.cleanup()
        except Exception as e:
            logger.debug(f"Rate limiter cleanup error: {e}")


def start_cleanup_task():
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_periodic_cleanup())


def stop_cleanup_task():
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
