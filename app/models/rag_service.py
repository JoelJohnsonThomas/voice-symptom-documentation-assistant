"""
RAG (Retrieval-Augmented Generation) Service — Production Healthcare Edition

Indexes past intake sessions as vector embeddings and retrieves
semantically similar cases to enrich SOAP note generation.

Production enhancements:
  Phase 1:
  - Medical-domain embeddings: PubMedBERT for clinical semantic accuracy
  - Similarity threshold:      discard low-relevance retrievals
  - Clinical-aware chunking:   per-SOAP-section indexing with metadata
  - Cross-encoder reranking:   precision boost on top-k candidates
  - Retrieval confidence:      scored per result for downstream gating
  - PHI-safe indexing:         redact PHI before embedding

  Phase 3:
  - Tenant isolation:          org_id / provider_id scoped retrieval
  - Encrypted vector store:    AES-256-GCM encryption of ChromaDB persistence
  - RAG audit trail:           HIPAA-compliant logging of every retrieval
  - Enhanced PHI verification: double-pass redaction with verification
"""

import hashlib
import json
import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy singletons
# ---------------------------------------------------------------------------
_embedding_model = None
_reranker_model = None
_chroma_client = None
_collection = None

# SOAP section types used for clinical-aware chunking
SOAP_SECTIONS = ("subjective", "objective", "assessment", "plan")


def _get_embedding_model():
    """Lazy-load the medical-domain embedding model (PubMedBERT)."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = settings.rag_embedding_model
        logger.info(f"Loading RAG embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        logger.info("RAG embedding model loaded")
    return _embedding_model


def _get_reranker_model():
    """Lazy-load the cross-encoder reranker model."""
    global _reranker_model
    if _reranker_model is None:
        if not settings.rag_reranker_enabled:
            return None
        from sentence_transformers import CrossEncoder
        model_name = settings.rag_reranker_model
        logger.info(f"Loading RAG reranker model: {model_name}")
        _reranker_model = CrossEncoder(model_name)
        logger.info("RAG reranker model loaded")
    return _reranker_model


def _get_collection():
    """Lazy-load ChromaDB client and collection."""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        persist_dir = settings.rag_persist_dir

        # Phase 3.3: If vector store encryption is enabled, use an encrypted
        # subdirectory that is decrypted on mount.  For embedded ChromaDB we
        # encrypt/decrypt the whole persist dir at startup/shutdown.
        if settings.rag_vector_store_encryption_enabled:
            _ensure_vector_store_decrypted(persist_dir)

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
        _collection = _chroma_client.get_or_create_collection(
            name="intake_sessions_v2",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB collection ready at '{persist_dir}' "
            f"({_collection.count()} documents)"
        )
    return _collection


def _embed(text: str) -> List[float]:
    """Return a normalised embedding vector for the given text."""
    model = _get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def _redact_phi_for_embedding(text: str) -> str:
    """
    Strip PHI from text before it enters the vector store (Phase 3.1).
    Uses enhanced double-pass redaction with verification.
    """
    from app.compliance import redact_for_vector_store
    redacted, verification = redact_for_vector_store(text)
    if not verification["is_clean"]:
        logger.warning(
            f"RAG PHI verification: {verification['phi_count']} patterns "
            f"still detected after redaction: {verification['pattern_types']}"
        )
    return redacted


def _cosine_similarity_from_distance(distance: float) -> float:
    """ChromaDB cosine distance = 1 - cosine_similarity."""
    return max(0.0, 1.0 - distance)


def _build_chunk_id(session_id: str, section: str) -> str:
    """Deterministic chunk ID for a session + section pair."""
    return f"{session_id}::{section}"


def _hash_query(text: str) -> str:
    """SHA-256 hash of query text for audit logging (no PHI in logs)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _rerank(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-score candidates using cross-encoder for higher precision."""
    reranker = _get_reranker_model()
    if reranker is None or not candidates:
        return candidates
    try:
        pairs = [(query, c["document"]) for c in candidates]
        scores = reranker.predict(pairs)
        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates
    except Exception as exc:
        logger.warning(f"RAG: reranking failed, using cosine order: {exc}")
        return candidates


# ---------------------------------------------------------------------------
# Phase 3.2: Tenant isolation helpers
# ---------------------------------------------------------------------------

def _get_tenant_metadata(
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
) -> Dict[str, str]:
    """Build tenant metadata for indexing."""
    return {
        "organization_id": organization_id or settings.default_organization_id,
        "provider_id": provider_id or settings.default_provider_id,
    }


def _build_tenant_filter(
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    extra_filter: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    Build a ChromaDB where-filter that enforces tenant isolation.

    When multi-tenancy is enabled, retrieval is scoped to the requesting
    organization.  Provider-level scoping is optional (for within-org isolation).
    """
    if not settings.multi_tenancy_enabled:
        return extra_filter

    org_id = organization_id or settings.default_organization_id
    conditions = [{"organization_id": org_id}]

    if provider_id:
        conditions.append({"provider_id": provider_id})

    if extra_filter:
        conditions.append(extra_filter)

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ---------------------------------------------------------------------------
# Phase 3.3: Encrypted vector store helpers
# ---------------------------------------------------------------------------

_ENCRYPTED_MARKER = ".encrypted"


def _ensure_vector_store_decrypted(persist_dir: str) -> None:
    """
    Decrypt the vector store directory if it exists in encrypted form.

    Strategy: we store a tarball of the ChromaDB files encrypted with
    AES-256-GCM.  On startup we decrypt into the working directory.
    On shutdown (or periodic flush) we re-encrypt.
    """
    encrypted_path = Path(persist_dir + _ENCRYPTED_MARKER)
    target_path = Path(persist_dir)

    if not encrypted_path.exists():
        return  # No encrypted archive — first run or already decrypted

    try:
        from app.encryption import decrypt_bytes
        import tarfile
        import io

        logger.info("Decrypting vector store...")
        encrypted_data = encrypted_path.read_bytes()
        decrypted_data = decrypt_bytes(encrypted_data)

        # Extract tar archive
        target_path.mkdir(parents=True, exist_ok=True)
        tar_buffer = io.BytesIO(decrypted_data)
        with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
            tar.extractall(path=str(target_path), filter="data")

        logger.info(f"Vector store decrypted to {persist_dir}")

    except Exception as exc:
        logger.error(f"Failed to decrypt vector store: {exc}")
        raise


def encrypt_vector_store() -> Optional[str]:
    """
    Encrypt the vector store directory to an archive file.

    Call this on shutdown or periodically to ensure data-at-rest encryption.
    Returns the path to the encrypted file, or None if encryption is disabled.
    """
    if not settings.rag_vector_store_encryption_enabled:
        return None

    persist_dir = settings.rag_persist_dir
    target_path = Path(persist_dir)
    encrypted_path = Path(persist_dir + _ENCRYPTED_MARKER)

    if not target_path.exists():
        return None

    try:
        from app.encryption import encrypt_bytes
        import tarfile
        import io

        logger.info("Encrypting vector store...")

        # Create tar.gz archive of the directory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            for file_path in target_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(target_path)
                    tar.add(str(file_path), arcname=str(arcname))

        tar_data = tar_buffer.getvalue()
        encrypted_data = encrypt_bytes(tar_data)
        encrypted_path.write_bytes(encrypted_data)

        logger.info(
            f"Vector store encrypted: {len(tar_data)} bytes → "
            f"{len(encrypted_data)} bytes at {encrypted_path}"
        )
        return str(encrypted_path)

    except Exception as exc:
        logger.error(f"Failed to encrypt vector store: {exc}")
        return None


# ---------------------------------------------------------------------------
# Phase 3.4: RAG audit trail
# ---------------------------------------------------------------------------

def _record_rag_audit(
    action: str,
    query_hash: str,
    retrieved_session_ids: List[str],
    similarities: List[float],
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_details: Optional[Dict] = None,
) -> None:
    """
    Record a RAG operation in the audit trail.

    This is logged as a structured JSON entry for HIPAA "minimum necessary"
    documentation.  The query text is NOT logged — only its hash.
    """
    if not settings.rag_audit_enabled:
        return

    try:
        audit_entry = {
            "action": action,
            "query_hash": query_hash,
            "retrieved_session_ids": retrieved_session_ids,
            "similarities": [round(s, 4) for s in similarities],
            "result_count": len(retrieved_session_ids),
            "organization_id": organization_id or settings.default_organization_id,
            "provider_id": provider_id or settings.default_provider_id,
            "user_id": user_id,
            "timestamp": time.time(),
            "threshold": settings.rag_similarity_threshold,
        }
        if extra_details:
            audit_entry["details"] = extra_details

        # Log as structured JSON for downstream SIEM/audit ingestion
        logger.info(f"RAG_AUDIT: {json.dumps(audit_entry)}")

        # Also write to the RAG audit log file for persistent trail
        _append_to_audit_file(audit_entry)

    except Exception as exc:
        logger.warning(f"RAG audit logging failed: {exc}")


def _append_to_audit_file(entry: Dict[str, Any]) -> None:
    """Append an audit entry to the RAG audit log file (JSONL format)."""
    try:
        audit_dir = Path(settings.rag_persist_dir) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)

        # Daily rotation: one file per day
        from datetime import datetime
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        audit_file = audit_dir / f"rag_audit_{date_str}.jsonl"

        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    except Exception as exc:
        logger.debug(f"RAG audit file write failed: {exc}")


def get_rag_audit_logs(
    date: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Read RAG audit logs for compliance review.

    Args:
        date: Date string (YYYY-MM-DD). Defaults to today.
        limit: Max entries to return.

    Returns:
        List of audit entries (most recent first).
    """
    try:
        from datetime import datetime
        audit_dir = Path(settings.rag_persist_dir) / "audit"
        if not audit_dir.exists():
            return []

        date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
        audit_file = audit_dir / f"rag_audit_{date_str}.jsonl"

        if not audit_file.exists():
            return []

        entries = []
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Return most recent first, limited
        entries.reverse()
        return entries[:limit]

    except Exception as exc:
        logger.warning(f"Failed to read RAG audit logs: {exc}")
        return []


# ---------------------------------------------------------------------------
# Metrics helpers (lazy import to avoid circular dependency)
# ---------------------------------------------------------------------------
def _record_retrieval_metrics(
    latency_s: float,
    num_results: int,
    threshold_met: bool,
    similarities: List[float],
):
    """Push RAG-specific metrics to the monitoring system."""
    try:
        from app.metrics import (
            RAG_RETRIEVAL_LATENCY,
            RAG_RETRIEVAL_COUNT,
            RAG_SIMILARITY_SCORE,
            RAG_FALLBACK_COUNT,
            RAG_INDEX_SIZE,
        )
        RAG_RETRIEVAL_LATENCY.observe(latency_s)
        RAG_RETRIEVAL_COUNT.inc(threshold_met="true" if threshold_met else "false")
        for sim in similarities:
            RAG_SIMILARITY_SCORE.observe(sim)
        if not threshold_met:
            RAG_FALLBACK_COUNT.inc()
        try:
            collection = _get_collection()
            RAG_INDEX_SIZE.set(collection.count())
        except Exception:
            pass
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_session(
    session_id: str,
    transcript: str,
    chief_complaint: Optional[str] = None,
    soap_subjective: Optional[str] = None,
    soap_objective: Optional[str] = None,
    soap_assessment: Optional[str] = None,
    soap_plan: Optional[str] = None,
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
) -> None:
    """
    Index a single intake session into the vector store.

    When chunking is enabled (default), each SOAP section is stored as a
    separate document with section-type metadata, enabling section-specific
    retrieval.  The transcript + chief complaint is always indexed as a
    "full" chunk for broad matching.

    PHI is redacted from all text before embedding.
    Tenant metadata (org_id, provider_id) is attached for isolation (Phase 3.2).
    """
    if not settings.rag_enabled:
        return

    try:
        collection = _get_collection()

        # PHI-safe: redact before embedding (Phase 3.1 — verified)
        safe_transcript = _redact_phi_for_embedding(transcript.strip())
        safe_cc = _redact_phi_for_embedding(chief_complaint or "")

        # Phase 3.2: tenant metadata
        tenant_meta = _get_tenant_metadata(organization_id, provider_id)

        # --- Full-session chunk (always indexed) ---
        embed_parts = [safe_transcript]
        if safe_cc and safe_cc not in ("not specified", ""):
            embed_parts.append(f"Chief complaint: {safe_cc}")
        embed_text = " ".join(embed_parts)

        full_doc_parts: List[str] = []
        if safe_cc:
            full_doc_parts.append(f"Chief complaint: {safe_cc}")

        soap_map = {
            "subjective": soap_subjective,
            "objective": soap_objective,
            "assessment": soap_assessment,
            "plan": soap_plan,
        }

        for section, content in soap_map.items():
            if content:
                safe_content = _redact_phi_for_embedding(content)
                full_doc_parts.append(f"{section.title()}: {safe_content}")

        full_document = "\n".join(full_doc_parts) if full_doc_parts else safe_transcript[:500]

        full_metadata = {
            "session_id": session_id,
            "section_type": "full",
            "has_soap": bool(soap_subjective),
            "chief_complaint": (safe_cc or "")[:200],
            **tenant_meta,
        }

        ids = [_build_chunk_id(session_id, "full")]
        embeddings = [_embed(embed_text)]
        documents = [full_document]
        metadatas = [full_metadata]

        # --- Per-section chunks (if chunking enabled) ---
        if settings.rag_chunking_enabled:
            for section, content in soap_map.items():
                if not content:
                    continue
                safe_content = _redact_phi_for_embedding(content)
                section_embed_text = f"{section.title()}: {safe_content}"
                if safe_cc:
                    section_embed_text = f"Chief complaint: {safe_cc}. {section_embed_text}"

                ids.append(_build_chunk_id(session_id, section))
                embeddings.append(_embed(section_embed_text))
                documents.append(f"{section.title()}: {safe_content}")
                metadatas.append({
                    "session_id": session_id,
                    "section_type": section,
                    "has_soap": True,
                    "chief_complaint": (safe_cc or "")[:200],
                    **tenant_meta,
                })

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        # Phase 3.4: Audit the indexing operation
        _record_rag_audit(
            action="index",
            query_hash="N/A",
            retrieved_session_ids=[session_id],
            similarities=[],
            organization_id=tenant_meta["organization_id"],
            provider_id=tenant_meta["provider_id"],
            extra_details={"chunks_indexed": len(ids)},
        )

        logger.info(
            f"RAG: indexed session {session_id} "
            f"({len(ids)} chunk{'s' if len(ids) > 1 else ''}, "
            f"org={tenant_meta['organization_id']})"
        )

    except Exception as exc:
        logger.warning(f"RAG: failed to index session {session_id}: {exc}")


def retrieve_similar_sessions(
    transcript: str,
    top_k: Optional[int] = None,
    exclude_id: Optional[str] = None,
    section_filter: Optional[str] = None,
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most similar past sessions for a given transcript.

    Pipeline:
      1. Embed query with PubMedBERT
      2. Retrieve initial_retrieval_k candidates from ChromaDB
         (scoped to tenant if multi-tenancy enabled — Phase 3.2)
      3. Filter by similarity threshold
      4. Rerank with cross-encoder (if enabled)
      5. Return top-k with confidence scores
      6. Log retrieval to audit trail (Phase 3.4)

    Returns a list of dicts with keys:
      id, document, metadata, distance, similarity, retrieval_confidence
    """
    if not settings.rag_enabled:
        return []

    t0 = time.time()
    query_hash = _hash_query(transcript)

    try:
        collection = _get_collection()
        total = collection.count()
        if total == 0:
            logger.debug("RAG collection is empty — skipping retrieval")
            return []

        k = top_k or settings.rag_top_k
        initial_k = min(settings.rag_initial_retrieval_k, total)
        if initial_k <= 0:
            return []

        # PHI-safe query
        safe_query = _redact_phi_for_embedding(transcript)
        query_embedding = _embed(safe_query)

        # Phase 3.2: Build tenant-scoped filter
        section_where = None
        if section_filter and section_filter in SOAP_SECTIONS:
            section_where = {"section_type": section_filter}

        where_filter = _build_tenant_filter(
            organization_id=organization_id,
            provider_id=provider_id,
            extra_filter=section_where,
        )

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=initial_k,
            include=["documents", "metadatas", "distances"],
            where=where_filter,
        )

        # --- Step 1: Convert to candidates with similarity scores ---
        candidates: List[Dict[str, Any]] = []
        seen_sessions = set()

        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            metadata = results["metadatas"][0][i]
            session_id = metadata.get("session_id", doc_id.split("::")[0])

            if exclude_id and session_id == exclude_id:
                continue

            distance = results["distances"][0][i]
            similarity = _cosine_similarity_from_distance(distance)

            if similarity < settings.rag_similarity_threshold:
                continue

            candidates.append({
                "id": doc_id,
                "session_id": session_id,
                "document": results["documents"][0][i],
                "metadata": metadata,
                "distance": distance,
                "similarity": round(similarity, 4),
            })

        # --- Step 3: Rerank with cross-encoder ---
        if settings.rag_reranker_enabled and len(candidates) > 1:
            candidates = _rerank(safe_query, candidates)

        # --- Step 4: Deduplicate by session ---
        deduped: List[Dict[str, Any]] = []
        for c in candidates:
            sid = c["session_id"]
            if sid not in seen_sessions:
                seen_sessions.add(sid)
                deduped.append(c)
            if len(deduped) >= k:
                break

        # --- Step 5: Compute retrieval confidence ---
        for item in deduped:
            sim = item["similarity"]
            if sim >= 0.85:
                item["retrieval_confidence"] = "high"
            elif sim >= 0.75:
                item["retrieval_confidence"] = "medium"
            else:
                item["retrieval_confidence"] = "low"

        latency = time.time() - t0
        similarities = [c["similarity"] for c in deduped]

        _record_retrieval_metrics(
            latency_s=latency,
            num_results=len(deduped),
            threshold_met=len(deduped) > 0,
            similarities=similarities,
        )

        # Phase 3.4: Audit trail
        _record_rag_audit(
            action="retrieve",
            query_hash=query_hash,
            retrieved_session_ids=[c["session_id"] for c in deduped],
            similarities=similarities,
            organization_id=organization_id,
            provider_id=provider_id,
            user_id=user_id,
            extra_details={
                "candidates_before_filter": len(candidates),
                "latency_s": round(latency, 3),
                "reranker_used": settings.rag_reranker_enabled,
            },
        )

        logger.info(
            f"RAG: retrieved {len(deduped)} results "
            f"(from {len(candidates)} candidates, "
            f"threshold={settings.rag_similarity_threshold}, "
            f"latency={latency:.3f}s)"
        )
        return deduped

    except Exception as exc:
        logger.warning(f"RAG: retrieval failed: {exc}")
        return []


def remove_session(session_id: str) -> None:
    """Remove all chunks for a session from the vector store."""
    if not settings.rag_enabled:
        return
    try:
        collection = _get_collection()
        ids_to_remove = [_build_chunk_id(session_id, "full")]
        for section in SOAP_SECTIONS:
            ids_to_remove.append(_build_chunk_id(session_id, section))
        collection.delete(ids=ids_to_remove)

        _record_rag_audit(
            action="delete",
            query_hash="N/A",
            retrieved_session_ids=[session_id],
            similarities=[],
        )

        logger.info(f"RAG: removed session {session_id} (all chunks)")
    except Exception as exc:
        logger.warning(f"RAG: failed to remove session {session_id}: {exc}")


def get_index_stats() -> Dict[str, Any]:
    """Return statistics about the RAG vector store."""
    if not settings.rag_enabled:
        return {"enabled": False}
    try:
        collection = _get_collection()
        count = collection.count()

        section_counts = {}
        for section in ["full"] + list(SOAP_SECTIONS):
            try:
                result = collection.get(
                    where={"section_type": section},
                    include=[],
                )
                section_counts[section] = len(result["ids"])
            except Exception:
                section_counts[section] = "unknown"

        return {
            "enabled": True,
            "total_chunks": count,
            "chunks_by_section": section_counts,
            "embedding_model": settings.rag_embedding_model,
            "reranker_model": settings.rag_reranker_model if settings.rag_reranker_enabled else "disabled",
            "similarity_threshold": settings.rag_similarity_threshold,
            "top_k": settings.rag_top_k,
            "initial_retrieval_k": settings.rag_initial_retrieval_k,
            "chunking_enabled": settings.rag_chunking_enabled,
            "persist_dir": settings.rag_persist_dir,
            "multi_tenancy_enabled": settings.multi_tenancy_enabled,
            "vector_store_encrypted": settings.rag_vector_store_encryption_enabled,
            "audit_enabled": settings.rag_audit_enabled,
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


def retrieve_enriched_context(
    transcript: str,
    top_k: Optional[int] = None,
    exclude_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified retrieval that merges session-based RAG with knowledge base
    guidelines (Phase 2 integration), scoped to tenant (Phase 3.2).

    Returns a dict with:
      - similar_sessions: list from retrieve_similar_sessions()
      - clinical_guidelines: list from knowledge_base_service
      - has_context: bool indicating whether any context was found
    """
    similar_sessions = retrieve_similar_sessions(
        transcript,
        top_k=top_k,
        exclude_id=exclude_id,
        organization_id=organization_id,
        provider_id=provider_id,
        user_id=user_id,
    )

    clinical_guidelines = []
    try:
        from app.models.knowledge_base_service import retrieve_guidelines
        clinical_guidelines = retrieve_guidelines(transcript)
    except Exception as exc:
        logger.debug(f"RAG: knowledge base retrieval skipped: {exc}")

    return {
        "similar_sessions": similar_sessions,
        "clinical_guidelines": clinical_guidelines,
        "has_context": bool(similar_sessions or clinical_guidelines),
    }


def is_ready() -> bool:
    """Return True when RAG is enabled and the collection is accessible."""
    if not settings.rag_enabled:
        return False
    try:
        _get_collection()
        return True
    except Exception:
        return False
