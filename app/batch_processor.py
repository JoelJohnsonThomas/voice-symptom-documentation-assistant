"""Batch audio processing service.

Phase 10: Upload a set of audio files → batch-generate SOAP notes.
Tracks progress and supports inter-session linking for follow-up visits.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class BatchStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchItem:
    item_id: str
    filename: str
    status: BatchStatus = BatchStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


@dataclass
class BatchJob:
    batch_id: str
    items: List[BatchItem] = field(default_factory=list)
    status: BatchStatus = BatchStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    linked_session_id: Optional[str] = None  # For inter-session linking

    @property
    def progress(self) -> Dict[str, int]:
        total = len(self.items)
        completed = sum(1 for i in self.items if i.status == BatchStatus.COMPLETED)
        failed = sum(1 for i in self.items if i.status == BatchStatus.FAILED)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "remaining": total - completed - failed,
            "percent": round(completed / total * 100, 1) if total > 0 else 0,
        }


class BatchProcessor:
    """Manages batch audio processing jobs."""

    def __init__(self, max_concurrent: int = 2):
        self._jobs: Dict[str, BatchJob] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def create_job(
        self,
        filenames: List[str],
        linked_session_id: Optional[str] = None,
    ) -> BatchJob:
        """Create a new batch job for the given files."""
        batch_id = str(uuid.uuid4())
        items = [
            BatchItem(item_id=str(uuid.uuid4()), filename=fn)
            for fn in filenames
        ]
        job = BatchJob(
            batch_id=batch_id,
            items=items,
            linked_session_id=linked_session_id,
        )
        self._jobs[batch_id] = job
        return job

    async def process_job(
        self,
        batch_id: str,
        process_fn,
    ) -> BatchJob:
        """Process all items in a batch job.

        Args:
            batch_id: The batch job ID.
            process_fn: Async callable(filename) -> Dict with SOAP result.
        """
        job = self._jobs.get(batch_id)
        if not job:
            raise ValueError(f"Batch job {batch_id} not found")

        job.status = BatchStatus.PROCESSING

        async def _process_item(item: BatchItem):
            async with self._semaphore:
                item.status = BatchStatus.PROCESSING
                item.started_at = time.time()
                try:
                    item.result = await process_fn(item.filename)
                    item.status = BatchStatus.COMPLETED
                except Exception as e:
                    item.status = BatchStatus.FAILED
                    item.error = str(e)
                    logger.error("Batch item %s failed: %s", item.filename, e)
                finally:
                    item.completed_at = time.time()

        tasks = [_process_item(item) for item in job.items]
        await asyncio.gather(*tasks, return_exceptions=True)

        all_done = all(
            i.status in (BatchStatus.COMPLETED, BatchStatus.FAILED) for i in job.items
        )
        if all_done:
            any_success = any(i.status == BatchStatus.COMPLETED for i in job.items)
            job.status = BatchStatus.COMPLETED if any_success else BatchStatus.FAILED
            job.completed_at = time.time()

        return job

    def get_job(self, batch_id: str) -> Optional[BatchJob]:
        return self._jobs.get(batch_id)

    def cancel_job(self, batch_id: str) -> bool:
        job = self._jobs.get(batch_id)
        if not job or job.status in (BatchStatus.COMPLETED, BatchStatus.CANCELLED):
            return False
        job.status = BatchStatus.CANCELLED
        for item in job.items:
            if item.status == BatchStatus.QUEUED:
                item.status = BatchStatus.CANCELLED
        return True

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [
            {
                "batch_id": j.batch_id,
                "status": j.status,
                "progress": j.progress,
                "created_at": j.created_at,
                "linked_session_id": j.linked_session_id,
            }
            for j in jobs[:limit]
        ]


# =====================================================
# Inter-Session Linking
# =====================================================

class SessionLinker:
    """Links follow-up visits to original sessions for longitudinal view."""

    def __init__(self):
        self._links: Dict[str, List[str]] = {}  # parent_id -> [child_ids]
        self._reverse: Dict[str, str] = {}       # child_id -> parent_id

    def link(self, parent_session_id: str, child_session_id: str) -> None:
        if parent_session_id not in self._links:
            self._links[parent_session_id] = []
        if child_session_id not in self._links[parent_session_id]:
            self._links[parent_session_id].append(child_session_id)
        self._reverse[child_session_id] = parent_session_id

    def get_chain(self, session_id: str) -> List[str]:
        """Get the full session chain (root → ... → current)."""
        # Walk up to root
        root = session_id
        while root in self._reverse:
            root = self._reverse[root]
        # Walk down from root
        chain = [root]
        current = root
        while current in self._links:
            children = self._links[current]
            if not children:
                break
            chain.append(children[-1])  # Latest follow-up
            current = children[-1]
        return chain

    def get_follow_ups(self, session_id: str) -> List[str]:
        return self._links.get(session_id, [])

    def get_parent(self, session_id: str) -> Optional[str]:
        return self._reverse.get(session_id)


# =====================================================
# Audio Quality Check
# =====================================================

def check_audio_quality(audio_data, sample_rate: int = 16000) -> Dict[str, Any]:
    """Check audio quality metrics before processing.

    Returns SNR estimate and quality warnings.
    """
    import numpy as np

    if isinstance(audio_data, bytes):
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        audio = np.asarray(audio_data, dtype=np.float32)

    if len(audio) == 0:
        return {"quality": "empty", "snr_db": 0, "warnings": ["No audio data"]}

    # RMS energy
    rms = np.sqrt(np.mean(audio ** 2))
    rms_db = 20 * np.log10(max(rms, 1e-10))

    # Simple SNR estimate: compare top 10% energy frames vs bottom 10%
    frame_size = int(sample_rate * 0.025)  # 25ms frames
    n_frames = max(1, len(audio) // frame_size)
    frame_energies = []
    for i in range(n_frames):
        frame = audio[i * frame_size : (i + 1) * frame_size]
        frame_energies.append(np.mean(frame ** 2))

    frame_energies.sort()
    noise_floor = np.mean(frame_energies[: max(1, n_frames // 10)])
    signal_level = np.mean(frame_energies[-(max(1, n_frames // 10)) :])
    snr_db = 10 * np.log10(max(signal_level / max(noise_floor, 1e-10), 1e-10))

    # Duration
    duration_s = len(audio) / sample_rate

    warnings = []
    if snr_db < 10:
        warnings.append(f"Low SNR ({snr_db:.1f} dB) — noisy environment detected")
    if rms_db < -40:
        warnings.append(f"Very quiet audio ({rms_db:.1f} dB RMS)")
    if duration_s < 1.0:
        warnings.append(f"Very short audio ({duration_s:.1f}s)")
    if duration_s > settings.max_audio_duration_seconds:
        warnings.append(
            f"Audio exceeds max duration ({duration_s:.0f}s > {settings.max_audio_duration_seconds}s)"
        )

    quality = "good"
    if warnings:
        quality = "poor" if snr_db < 5 else "fair"

    return {
        "quality": quality,
        "snr_db": round(snr_db, 1),
        "rms_db": round(rms_db, 1),
        "duration_seconds": round(duration_s, 2),
        "warnings": warnings,
    }


# =====================================================
# Singletons
# =====================================================

_batch_processor: Optional[BatchProcessor] = None
_session_linker: Optional[SessionLinker] = None


def get_batch_processor() -> BatchProcessor:
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = BatchProcessor(
            max_concurrent=settings.queue_max_concurrent_inferences
        )
    return _batch_processor


def get_session_linker() -> SessionLinker:
    global _session_linker
    if _session_linker is None:
        _session_linker = SessionLinker()
    return _session_linker
