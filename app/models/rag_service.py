"""
RAG (Retrieval-Augmented Generation) Service — Production Healthcare Edition

Indexes past intake sessions as vector embeddings and retrieves
semantically similar cases to enrich SOAP note generation.

Production enhancements (Phase 1):
- Medical-domain embeddings: PubMedBERT for clinical semantic accuracy
- Similarity threshold:      discard low-relevance retrievals
- Clinical-aware chunking:   per-SOAP-section indexing with metadata
- Cross-encoder reranking:   precision boost on top-k candidates
- Retrieval confidence:      scored per result for downstream gating
- PHI-safe indexing:         redact PHI before embedding
"""

import hashlib
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
    Strip PHI from text before it enters the vector store.
    Uses the same patterns as the HIPAA compliance module.
    """
    from app.compliance import redact_phi_text
    return redact_phi_text(text)


def _cosine_similarity_from_distance(distance: float) -> float:
    """
    ChromaDB cosine distance = 1 - cosine_similarity.
    Convert back to similarity score in [0, 1].
    """
    return max(0.0, 1.0 - distance)


def _build_chunk_id(session_id: str, section: str) -> str:
    """Deterministic chunk ID for a session + section pair."""
    return f"{session_id}::{section}"


def _rerank(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Re-score candidates using cross-encoder for higher precision.

    The cross-encoder sees (query, document) pairs and scores them
    jointly — much more accurate than bi-encoder cosine alone.
    """
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
        # Update index size gauge
        try:
            collection = _get_collection()
            RAG_INDEX_SIZE.set(collection.count())
        except Exception:
            pass
    except ImportError:
        pass  # metrics module not available — skip silently


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
) -> None:
    """
    Index a single intake session into the vector store.

    When chunking is enabled (default), each SOAP section is stored as a
    separate document with section-type metadata, enabling section-specific
    retrieval.  The transcript + chief complaint is always indexed as a
    "full" chunk for broad matching.

    PHI is redacted from all text before embedding.
    """
    if not settings.rag_enabled:
        return

    try:
        collection = _get_collection()

        # PHI-safe: redact before embedding
        safe_transcript = _redact_phi_for_embedding(transcript.strip())
        safe_cc = _redact_phi_for_embedding(chief_complaint or "")

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
                })

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(
            f"RAG: indexed session {session_id} "
            f"({len(ids)} chunk{'s' if len(ids) > 1 else ''})"
        )

    except Exception as exc:
        logger.warning(f"RAG: failed to index session {session_id}: {exc}")


def retrieve_similar_sessions(
    transcript: str,
    top_k: Optional[int] = None,
    exclude_id: Optional[str] = None,
    section_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most similar past sessions for a given transcript.

    Pipeline:
      1. Embed query with PubMedBERT
      2. Retrieve initial_retrieval_k candidates from ChromaDB
      3. Filter by similarity threshold
      4. Rerank with cross-encoder (if enabled)
      5. Return top-k with confidence scores

    Returns a list of dicts with keys:
      id, document, metadata, distance, similarity, retrieval_confidence

    Returns an empty list when RAG is disabled, the collection is empty,
    or no results meet the similarity threshold.
    """
    if not settings.rag_enabled:
        return []

    t0 = time.time()
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

        # Build optional metadata filter
        where_filter = None
        if section_filter and section_filter in SOAP_SECTIONS:
            where_filter = {"section_type": section_filter}

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

            # Exclude self-reference
            if exclude_id and session_id == exclude_id:
                continue

            distance = results["distances"][0][i]
            similarity = _cosine_similarity_from_distance(distance)

            # --- Step 2: Apply similarity threshold ---
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

        # --- Step 4: Deduplicate by session (keep best chunk per session) ---
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
            # Confidence tiers: high >= 0.85, medium >= 0.75, low >= threshold
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
        # Remove full chunk and all section chunks
        ids_to_remove = [_build_chunk_id(session_id, "full")]
        for section in SOAP_SECTIONS:
            ids_to_remove.append(_build_chunk_id(session_id, section))
        collection.delete(ids=ids_to_remove)
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

        # Count by section type
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
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


def retrieve_enriched_context(
    transcript: str,
    top_k: Optional[int] = None,
    exclude_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified retrieval that merges session-based RAG with knowledge base
    guidelines (Phase 2 integration).

    Returns a dict with:
      - similar_sessions: list from retrieve_similar_sessions()
      - clinical_guidelines: list from knowledge_base_service
      - has_context: bool indicating whether any context was found
    """
    similar_sessions = retrieve_similar_sessions(
        transcript, top_k=top_k, exclude_id=exclude_id,
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
