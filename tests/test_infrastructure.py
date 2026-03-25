"""Tests for Phase 8-10: Infrastructure, Observability, Batch Processing."""

import asyncio
import pytest
import time
import numpy as np


# =====================================================
# Phase 8: Cache Tests
# =====================================================

class TestLRUCache:
    def test_set_and_get(self):
        from app.cache import _LRUCache
        cache = _LRUCache(maxsize=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_ttl_expiry(self):
        from app.cache import _LRUCache
        cache = _LRUCache(maxsize=10)
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        # Simulate expiry by manipulating internal state
        cache._cache["key1"] = ("value1", time.time() - 1)
        assert cache.get("key1") is None

    def test_eviction(self):
        from app.cache import _LRUCache
        cache = _LRUCache(maxsize=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)
        assert cache.get("a") is None  # evicted
        assert cache.get("d") == 4

    def test_size(self):
        from app.cache import _LRUCache
        cache = _LRUCache(maxsize=10)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size() == 2


class TestCacheService:
    def test_make_key(self):
        from app.cache import CacheService
        key = CacheService.make_key("rag", "query", "headache")
        assert key.startswith("voxdoc:")
        assert len(key) > 10

    def test_make_key_deterministic(self):
        from app.cache import CacheService
        k1 = CacheService.make_key("a", "b")
        k2 = CacheService.make_key("a", "b")
        assert k1 == k2


# =====================================================
# Phase 8: Task Queue Tests
# =====================================================

class TestInMemoryTaskQueue:
    def test_enqueue_and_result(self):
        from app.task_queue import InMemoryTaskQueue, TaskStatus

        queue = InMemoryTaskQueue(max_concurrent=2)

        async def dummy_task():
            return {"answer": 42}

        async def run():
            task_id = await queue.enqueue(dummy_task)
            # Wait for completion
            for _ in range(50):
                result = queue.get_result(task_id)
                if result and result.status == TaskStatus.COMPLETED:
                    return result
                await asyncio.sleep(0.05)
            return queue.get_result(task_id)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"answer": 42}

    def test_stats(self):
        from app.task_queue import InMemoryTaskQueue
        queue = InMemoryTaskQueue()
        stats = queue.stats()
        assert stats["backend"] == "asyncio"
        assert stats["active"] == 0


# =====================================================
# Phase 8: Quantization Tests
# =====================================================

class TestQuantization:
    def test_disabled_returns_none(self):
        from app.quantization import get_quantization_config
        # Default is disabled
        assert get_quantization_config() is None

    def test_vram_estimate_structure(self):
        from app.quantization import estimate_vram_usage
        info = estimate_vram_usage()
        assert "model" in info
        assert "estimated_vram_gb" in info
        assert "quantization_bits" in info
        assert isinstance(info["estimated_vram_gb"], float)


# =====================================================
# Phase 8: Colab Utils Tests
# =====================================================

class TestColabUtils:
    def test_is_colab_environment(self):
        from app.colab_utils import is_colab_environment
        # Not running in Colab
        assert is_colab_environment() is False

    def test_detect_gpu_runtime(self):
        from app.colab_utils import detect_gpu_runtime
        info = detect_gpu_runtime()
        assert "cuda_available" in info
        assert "device_count" in info

    def test_colab_launch_info(self):
        from app.colab_utils import get_colab_launch_info
        info = get_colab_launch_info()
        assert "is_colab" in info
        assert "gpu" in info
        assert "recommended_settings" in info


# =====================================================
# Phase 9: Analytics Tests
# =====================================================

class TestSessionAnalytics:
    def test_record_and_summary(self):
        from app.analytics import SessionAnalytics
        analytics = SessionAnalytics()
        analytics.record_session(
            chief_complaint="headache",
            duration_seconds=120.0,
            soap_quality_score=0.85,
        )
        analytics.record_session(
            chief_complaint="headache",
            duration_seconds=90.0,
        )
        analytics.record_session(chief_complaint="chest pain")
        summary = analytics.get_summary()
        assert summary["total_sessions"] == 3
        assert summary["top_chief_complaints"][0] == ("headache", 2)
        assert summary["avg_session_duration_seconds"] > 0


class TestFeedbackCollector:
    def test_submit_and_scores(self):
        from app.analytics import FeedbackCollector, SOAPFeedback
        collector = FeedbackCollector()
        collector.submit(SOAPFeedback(session_id="s1", field="subjective", rating=1))
        collector.submit(SOAPFeedback(session_id="s2", field="subjective", rating=-1))
        collector.submit(SOAPFeedback(session_id="s3", field="subjective", rating=1))
        scores = collector.get_field_scores()
        assert scores["subjective"]["total"] == 3
        assert scores["subjective"]["positive_pct"] == pytest.approx(66.7, abs=0.1)

    def test_recent(self):
        from app.analytics import FeedbackCollector, SOAPFeedback
        collector = FeedbackCollector()
        collector.submit(SOAPFeedback(session_id="s1", field="plan", rating=1, comment="good"))
        recent = collector.recent()
        assert len(recent) == 1
        assert recent[0]["comment"] == "good"


class TestSIEMExport:
    def test_jsonlines_format(self):
        from app.analytics import export_audit_logs
        logs = [{"action": "login", "username": "admin", "ip_address": "1.2.3.4"}]
        output = export_audit_logs(logs, fmt="jsonlines")
        import json
        parsed = json.loads(output)
        assert parsed["event_type"] == "login"

    def test_cef_format(self):
        from app.analytics import export_audit_logs
        logs = [{"action": "login", "username": "admin"}]
        output = export_audit_logs(logs, fmt="cef")
        assert output.startswith("CEF:0|VoxDoc|")


class TestGrafanaDashboard:
    def test_dashboard_structure(self):
        from app.analytics import generate_grafana_dashboard
        dash = generate_grafana_dashboard()
        assert "dashboard" in dash
        assert "panels" in dash["dashboard"]
        assert len(dash["dashboard"]["panels"]) >= 6


# =====================================================
# Phase 10: Batch Processing Tests
# =====================================================

class TestBatchProcessor:
    def test_create_job(self):
        from app.batch_processor import BatchProcessor, BatchStatus
        processor = BatchProcessor()
        job = processor.create_job(["file1.wav", "file2.wav"])
        assert len(job.items) == 2
        assert job.status == BatchStatus.QUEUED

    def test_cancel_job(self):
        from app.batch_processor import BatchProcessor, BatchStatus
        processor = BatchProcessor()
        job = processor.create_job(["file1.wav"])
        assert processor.cancel_job(job.batch_id) is True
        assert job.status == BatchStatus.CANCELLED

    def test_list_jobs(self):
        from app.batch_processor import BatchProcessor
        processor = BatchProcessor()
        processor.create_job(["a.wav"])
        processor.create_job(["b.wav"])
        jobs = processor.list_jobs()
        assert len(jobs) == 2


class TestSessionLinker:
    def test_link_and_chain(self):
        from app.batch_processor import SessionLinker
        linker = SessionLinker()
        linker.link("visit-1", "visit-2")
        linker.link("visit-2", "visit-3")
        chain = linker.get_chain("visit-3")
        assert chain == ["visit-1", "visit-2", "visit-3"]

    def test_get_parent_and_followups(self):
        from app.batch_processor import SessionLinker
        linker = SessionLinker()
        linker.link("v1", "v2")
        assert linker.get_parent("v2") == "v1"
        assert linker.get_follow_ups("v1") == ["v2"]


class TestAudioQualityCheck:
    def test_good_audio(self):
        from app.batch_processor import check_audio_quality
        # Generate clean sine wave
        sr = 16000
        t = np.linspace(0, 2, sr * 2)
        audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        result = check_audio_quality(audio, sr)
        assert result["quality"] in ("good", "fair")
        assert result["snr_db"] > 0

    def test_empty_audio(self):
        from app.batch_processor import check_audio_quality
        result = check_audio_quality(b"", 16000)
        assert result["quality"] == "empty"
        assert len(result["warnings"]) > 0


# =====================================================
# Config Tests for Phase 8
# =====================================================

class TestPhase8Config:
    def test_database_url_default(self):
        from app.config import settings
        # Default is empty string (falls back to SQLite)
        assert settings.database_url == ""

    def test_redis_url_default(self):
        from app.config import settings
        assert settings.redis_url == ""

    def test_quantization_disabled_by_default(self):
        from app.config import settings
        assert settings.model_quantization_enabled is False

    def test_colab_mode_disabled_by_default(self):
        from app.config import settings
        assert settings.colab_mode is False

    def test_task_queue_disabled_by_default(self):
        from app.config import settings
        assert settings.task_queue_enabled is False
