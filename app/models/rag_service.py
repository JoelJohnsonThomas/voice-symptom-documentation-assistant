"""
RAG (Retrieval-Augmented Generation) Service

Indexes past intake sessions as vector embeddings and retrieves
semantically similar cases to enrich SOAP note generation.

Design:
- Vector store: ChromaDB (embedded, file-based — no extra server)
- Embeddings:   sentence-transformers (lightweight, CPU-friendly)
- What is indexed:  transcript + chief complaint
- What is retrieved: SOAP sections from similar past cases
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level lazy singletons
_embedding_model = None
_chroma_client = None
_collection = None


def _get_embedding_model():
    """Lazy-load the sentence-transformer embedding model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading RAG embedding model: {settings.rag_embedding_model}")
        _embedding_model = SentenceTransformer(settings.rag_embedding_model)
        logger.info("RAG embedding model loaded")
    return _embedding_model


def _get_collection():
    """Lazy-load ChromaDB client and collection."""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        persist_dir = settings.rag_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
        _collection = _chroma_client.get_or_create_collection(
            name="intake_sessions",
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

    The text embedded is the transcript plus chief complaint so that
    retrieval is driven by the clinical presentation, not the formatting.
    The stored *document* is the SOAP context that will be returned to
    the caller on retrieval.
    """
    if not settings.rag_enabled:
        return

    try:
        collection = _get_collection()

        # Build embedding text
        embed_parts = [transcript.strip()]
        if chief_complaint and chief_complaint not in ("not specified", ""):
            embed_parts.append(f"Chief complaint: {chief_complaint}")
        embed_text = " ".join(embed_parts)

        embedding = _embed(embed_text)

        # Build the document that will be returned on retrieval
        soap_parts: List[str] = []
        if chief_complaint:
            soap_parts.append(f"Chief complaint: {chief_complaint}")
        if soap_subjective:
            soap_parts.append(f"Subjective: {soap_subjective}")
        if soap_objective:
            soap_parts.append(f"Objective: {soap_objective}")
        if soap_assessment:
            soap_parts.append(f"Assessment: {soap_assessment}")
        if soap_plan:
            soap_parts.append(f"Plan: {soap_plan}")
        document = "\n".join(soap_parts) if soap_parts else transcript[:500]

        metadata = {
            "has_soap": bool(soap_subjective),
            "chief_complaint": (chief_complaint or "")[:200],
        }

        collection.upsert(
            ids=[session_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        logger.info(f"RAG: indexed session {session_id}")

    except Exception as exc:
        logger.warning(f"RAG: failed to index session {session_id}: {exc}")


def retrieve_similar_sessions(
    transcript: str,
    top_k: Optional[int] = None,
    exclude_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most similar past sessions for a given transcript.

    Returns a list of dicts with keys: id, document, metadata, distance.
    Returns an empty list when RAG is disabled or the collection is empty.
    """
    if not settings.rag_enabled:
        return []

    try:
        collection = _get_collection()
        total = collection.count()
        if total == 0:
            logger.debug("RAG collection is empty — skipping retrieval")
            return []

        k = min(top_k or settings.rag_top_k, total)
        if k <= 0:
            return []

        # Fetch one extra so we can drop the excluded session if needed
        n_results = min(k + (1 if exclude_id else 0), total)

        query_embedding = _embed(transcript)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        items: List[Dict[str, Any]] = []
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            if exclude_id and doc_id == exclude_id:
                continue
            items.append({
                "id": doc_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
            if len(items) >= k:
                break

        return items

    except Exception as exc:
        logger.warning(f"RAG: retrieval failed: {exc}")
        return []


def remove_session(session_id: str) -> None:
    """Remove a session from the vector store (call when a session is deleted)."""
    if not settings.rag_enabled:
        return
    try:
        collection = _get_collection()
        collection.delete(ids=[session_id])
        logger.info(f"RAG: removed session {session_id}")
    except Exception as exc:
        logger.warning(f"RAG: failed to remove session {session_id}: {exc}")


def get_index_stats() -> Dict[str, Any]:
    """Return statistics about the RAG vector store."""
    if not settings.rag_enabled:
        return {"enabled": False}
    try:
        collection = _get_collection()
        return {
            "enabled": True,
            "indexed_sessions": collection.count(),
            "embedding_model": settings.rag_embedding_model,
            "top_k": settings.rag_top_k,
            "persist_dir": settings.rag_persist_dir,
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


def is_ready() -> bool:
    """Return True when RAG is enabled and the collection is accessible."""
    if not settings.rag_enabled:
        return False
    try:
        _get_collection()
        return True
    except Exception:
        return False
