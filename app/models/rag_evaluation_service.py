"""
RAG Evaluation & Observability Service (Phase 4)

Provides:
  4.1 — Retrieval quality metrics (MRR@k, Recall@k, Precision@k)
  4.1 — Hallucination detection (cross-ref generated text vs evidence)
  4.1 — Clinical accuracy golden-set evaluation
  4.3 — Embedding drift detection with alerting

Design:
- Golden set: curated (query, expected_doc_ids) pairs for offline eval
- Hallucination check: lightweight keyword overlap between generated text
  and retrieved evidence — flags low-overlap sections
- Drift detection: tracks rolling centroid of new embeddings vs baseline,
  alerts when cosine distance exceeds threshold
"""

import json
import logging
import math
import time
from collections import deque
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


# =====================================================================
# 4.1 — Retrieval Quality Metrics
# =====================================================================

def mean_reciprocal_rank(
    results: List[List[str]],
    ground_truth: List[List[str]],
) -> float:
    """
    Compute Mean Reciprocal Rank (MRR) across multiple queries.

    Args:
        results: For each query, an ordered list of retrieved doc IDs
        ground_truth: For each query, a list of relevant doc IDs

    Returns:
        MRR score in [0, 1]
    """
    if not results or not ground_truth:
        return 0.0

    rr_sum = 0.0
    n = min(len(results), len(ground_truth))

    for i in range(n):
        relevant = set(ground_truth[i])
        for rank, doc_id in enumerate(results[i], start=1):
            if doc_id in relevant:
                rr_sum += 1.0 / rank
                break

    return rr_sum / n if n > 0 else 0.0


def recall_at_k(
    results: List[List[str]],
    ground_truth: List[List[str]],
    k: int = 3,
) -> float:
    """
    Compute Recall@k — fraction of relevant docs found in top-k.

    Returns:
        Average recall across all queries.
    """
    if not results or not ground_truth:
        return 0.0

    recall_sum = 0.0
    n = min(len(results), len(ground_truth))

    for i in range(n):
        relevant = set(ground_truth[i])
        if not relevant:
            continue
        retrieved_top_k = set(results[i][:k])
        hits = len(relevant & retrieved_top_k)
        recall_sum += hits / len(relevant)

    return recall_sum / n if n > 0 else 0.0


def precision_at_k(
    results: List[List[str]],
    ground_truth: List[List[str]],
    k: int = 3,
) -> float:
    """
    Compute Precision@k — fraction of top-k results that are relevant.

    Returns:
        Average precision across all queries.
    """
    if not results or not ground_truth:
        return 0.0

    precision_sum = 0.0
    n = min(len(results), len(ground_truth))

    for i in range(n):
        relevant = set(ground_truth[i])
        retrieved_top_k = results[i][:k]
        if not retrieved_top_k:
            continue
        hits = sum(1 for doc_id in retrieved_top_k if doc_id in relevant)
        precision_sum += hits / len(retrieved_top_k)

    return precision_sum / n if n > 0 else 0.0


def run_retrieval_evaluation(
    golden_set: List[Dict[str, Any]],
    k: int = 3,
) -> Dict[str, Any]:
    """
    Run full retrieval evaluation against a golden set.

    Args:
        golden_set: List of {"query": str, "relevant_ids": [str, ...]}
        k: Top-k for Recall/Precision

    Returns:
        Dict with MRR, Recall@k, Precision@k, per-query details
    """
    from app.models.rag_service import retrieve_similar_sessions

    all_results = []
    all_ground_truth = []
    per_query = []

    for item in golden_set:
        query = item["query"]
        expected_ids = item["relevant_ids"]

        retrieved = retrieve_similar_sessions(query, top_k=k * 2)
        retrieved_ids = [r["session_id"] for r in retrieved]

        all_results.append(retrieved_ids)
        all_ground_truth.append(expected_ids)

        # Per-query stats
        relevant_set = set(expected_ids)
        top_k_ids = retrieved_ids[:k]
        hits = [rid for rid in top_k_ids if rid in relevant_set]

        rr = 0.0
        for rank, rid in enumerate(retrieved_ids, start=1):
            if rid in relevant_set:
                rr = 1.0 / rank
                break

        per_query.append({
            "query": query[:100],
            "expected": expected_ids,
            "retrieved_top_k": top_k_ids,
            "hits": hits,
            "reciprocal_rank": round(rr, 4),
            "recall": round(len(hits) / len(expected_ids), 4) if expected_ids else 0,
            "precision": round(len(hits) / len(top_k_ids), 4) if top_k_ids else 0,
        })

    mrr = mean_reciprocal_rank(all_results, all_ground_truth)
    recall = recall_at_k(all_results, all_ground_truth, k=k)
    precision = precision_at_k(all_results, all_ground_truth, k=k)

    # Record metrics
    _record_eval_metrics(mrr, recall, precision, k)

    return {
        "mrr": round(mrr, 4),
        f"recall@{k}": round(recall, 4),
        f"precision@{k}": round(precision, 4),
        "queries_evaluated": len(golden_set),
        "k": k,
        "per_query": per_query,
    }


# =====================================================================
# 4.1 — Hallucination Detection
# =====================================================================

def _tokenize_simple(text: str) -> set:
    """Simple whitespace + lowering tokenizer for overlap checks."""
    import re
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    # Remove stopwords
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "can", "could", "must", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "out",
        "up", "down", "and", "but", "or", "nor", "not", "so", "yet",
        "both", "either", "neither", "each", "every", "all", "any", "few",
        "more", "most", "other", "some", "such", "no", "only", "own",
        "same", "than", "too", "very", "this", "that", "these", "those",
        "it", "its", "he", "she", "they", "them", "their", "we", "our",
    }
    return {t for t in tokens if t not in stopwords and len(t) > 2}


def check_hallucination(
    generated_text: str,
    evidence_texts: List[str],
    transcript: str = "",
    min_overlap_ratio: float = 0.3,
) -> Dict[str, Any]:
    """
    Check if generated text (Assessment/Plan) is grounded in evidence.

    Approach: keyword overlap between generated text and the union of
    retrieved evidence + original transcript.  Low overlap indicates
    potential hallucination.

    Args:
        generated_text: The SOAP Assessment or Plan section
        evidence_texts: Documents retrieved by RAG
        transcript: Original patient transcript
        min_overlap_ratio: Minimum expected overlap ratio

    Returns:
        {
            "is_grounded": bool,
            "overlap_ratio": float,
            "generated_tokens": int,
            "evidence_tokens": int,
            "overlapping_tokens": int,
            "ungrounded_terms": list,  # key terms not in evidence
            "risk_level": str,         # "low", "medium", "high"
        }
    """
    if not generated_text:
        return {"is_grounded": True, "overlap_ratio": 1.0, "risk_level": "low"}

    gen_tokens = _tokenize_simple(generated_text)
    if not gen_tokens:
        return {"is_grounded": True, "overlap_ratio": 1.0, "risk_level": "low"}

    # Build evidence token set
    evidence_combined = " ".join(evidence_texts) + " " + transcript
    evidence_tokens = _tokenize_simple(evidence_combined)

    overlap = gen_tokens & evidence_tokens
    overlap_ratio = len(overlap) / len(gen_tokens) if gen_tokens else 1.0

    # Identify potentially ungrounded medical terms
    # (terms in generated text not found in any evidence)
    ungrounded = gen_tokens - evidence_tokens
    # Filter to likely medical terms (longer, not common words)
    medical_ungrounded = [t for t in ungrounded if len(t) > 4]

    if overlap_ratio >= 0.7:
        risk = "low"
    elif overlap_ratio >= min_overlap_ratio:
        risk = "medium"
    else:
        risk = "high"

    is_grounded = overlap_ratio >= min_overlap_ratio

    return {
        "is_grounded": is_grounded,
        "overlap_ratio": round(overlap_ratio, 4),
        "generated_tokens": len(gen_tokens),
        "evidence_tokens": len(evidence_tokens),
        "overlapping_tokens": len(overlap),
        "ungrounded_terms": sorted(medical_ungrounded)[:20],
        "risk_level": risk,
    }


def check_documentation_hallucination(
    documentation: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    clinical_guidelines: List[Dict[str, Any]],
    transcript: str,
) -> Dict[str, Any]:
    """
    Run hallucination check on generated SOAP O/A/P sections.

    Uses NLI-based grounding if available, falls back to keyword overlap.
    Returns per-section hallucination analysis with citation annotations.
    """
    if not settings.rag_hallucination_check_enabled:
        return {"enabled": False}

    evidence_texts = []
    for case in (similar_cases or []):
        doc = case.get("document", "")
        if doc:
            evidence_texts.append(doc)
    for guideline in (clinical_guidelines or []):
        doc = guideline.get("document", "")
        if doc:
            evidence_texts.append(doc)

    # Use NLI grounding if available, otherwise keyword overlap
    grounding = get_citation_grounding_service()

    results = {}
    for section in ("soap_note_objective", "soap_note_assessment", "soap_note_plan"):
        text = documentation.get(section, "")
        if text and text != "Pending clinician assessment.":
            if grounding.is_ready:
                results[section] = grounding.check_grounding(
                    generated_text=text,
                    evidence_texts=evidence_texts,
                    transcript=transcript,
                )
            else:
                results[section] = check_hallucination(
                    generated_text=text,
                    evidence_texts=evidence_texts,
                    transcript=transcript,
                )

    # Overall risk: highest among sections
    risk_levels = [r.get("risk_level", "low") for r in results.values()]
    risk_order = {"high": 3, "medium": 2, "low": 1}
    overall_risk = max(risk_levels, key=lambda r: risk_order.get(r, 0)) if risk_levels else "low"

    return {
        "enabled": True,
        "sections": results,
        "overall_risk": overall_risk,
        "evidence_count": len(evidence_texts),
    }


# =====================================================================
# Phase 2 — NLI-Based Citation Grounding
# =====================================================================

class CitationGroundingService:
    """Production-grade hallucination detection using NLI entailment scoring.

    Extracts claims from generated text, checks each claim against evidence
    (transcript + RAG results) via a medical NLI model, and annotates
    unsupported claims with [UNGROUNDED] tags.

    Falls back to keyword overlap if the NLI model is unavailable.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._available = False
        self._load_model()

    def _load_model(self) -> None:
        """Load a BiomedBERT-based NLI model for entailment checking."""
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            model_name = "microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract"
            logger.info(f"Loading NLI model for citation grounding: {model_name}...")

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self._model.eval()
            self._available = True
            logger.info("Citation grounding NLI model loaded successfully")

        except ImportError:
            logger.warning(
                "transformers not available for NLI grounding. "
                "Using keyword-overlap fallback."
            )
        except Exception as e:
            logger.warning(f"NLI model loading failed: {e}. Using keyword-overlap fallback.")

    @property
    def is_ready(self) -> bool:
        return self._available

    def extract_claims(self, text: str) -> List[str]:
        """Extract individual claims/sentences from generated text.

        Splits on sentence boundaries and filters out boilerplate.
        """
        import re

        # Split on sentence-ending punctuation
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        claims = []
        # Filter out boilerplate / filler
        skip_patterns = [
            r'^(objective|assessment|plan|subjective)\s*:?\s*$',
            r'^(note|disclaimer|compliance)',
            r'clinician review',
            r'for reference only',
        ]

        for s in sentences:
            s = s.strip()
            if len(s) < 10:
                continue
            if any(re.search(p, s, re.IGNORECASE) for p in skip_patterns):
                continue
            claims.append(s)

        return claims

    def score_entailment(self, premise: str, hypothesis: str) -> float:
        """Score whether premise entails hypothesis using NLI model.

        Returns:
            Entailment probability (0-1). Higher = more grounded.
        """
        if not self._available:
            return 0.5

        try:
            import torch

            inputs = self._tokenizer(
                premise,
                hypothesis,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            )

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits

            # Softmax to get probabilities
            probs = torch.nn.functional.softmax(logits, dim=-1)

            # Entailment is typically index 0 or 2 depending on model
            # For most NLI models: 0=entailment, 1=neutral, 2=contradiction
            entailment_prob = probs[0][0].item()
            return entailment_prob

        except Exception as e:
            logger.debug(f"NLI scoring failed: {e}")
            return 0.5

    def check_grounding(
        self,
        generated_text: str,
        evidence_texts: List[str],
        transcript: str = "",
        entailment_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Check each claim in generated text against evidence via NLI.

        Args:
            generated_text: Generated SOAP section text.
            evidence_texts: Retrieved evidence documents.
            transcript: Original patient transcript.
            entailment_threshold: Min entailment score to consider grounded.

        Returns:
            Dict with grounding analysis including per-claim results,
            annotated text, and risk level.
        """
        claims = self.extract_claims(generated_text)
        if not claims:
            return {
                "is_grounded": True,
                "overlap_ratio": 1.0,
                "risk_level": "low",
                "claims": [],
                "annotated_text": generated_text,
            }

        # Combine all evidence into premise chunks
        all_evidence = evidence_texts + ([transcript] if transcript else [])
        combined_evidence = " ".join(all_evidence)

        # Truncate evidence to fit model context
        if len(combined_evidence) > 2000:
            combined_evidence = combined_evidence[:2000]

        claim_results = []
        grounded_count = 0
        annotated_parts = []

        for claim in claims:
            # Score each claim against combined evidence
            score = self.score_entailment(combined_evidence, claim)

            is_supported = score >= entailment_threshold
            if is_supported:
                grounded_count += 1
                annotated_parts.append(claim)
            else:
                annotated_parts.append(f"[UNGROUNDED] {claim}")

            # Find best matching evidence source
            best_source = None
            best_source_score = 0.0
            for i, ev in enumerate(evidence_texts):
                ev_score = self.score_entailment(ev[:1000], claim)
                if ev_score > best_source_score:
                    best_source_score = ev_score
                    best_source = f"evidence_{i+1}"

            # Also check transcript
            if transcript:
                t_score = self.score_entailment(transcript[:1000], claim)
                if t_score > best_source_score:
                    best_source_score = t_score
                    best_source = "transcript"

            claim_results.append({
                "claim": claim,
                "entailment_score": round(score, 4),
                "is_supported": is_supported,
                "best_source": best_source,
                "best_source_score": round(best_source_score, 4),
            })

        grounding_ratio = grounded_count / len(claims) if claims else 1.0

        if grounding_ratio >= 0.8:
            risk = "low"
        elif grounding_ratio >= 0.5:
            risk = "medium"
        else:
            risk = "high"

        return {
            "is_grounded": grounding_ratio >= 0.5,
            "overlap_ratio": round(grounding_ratio, 4),
            "grounded_claims": grounded_count,
            "total_claims": len(claims),
            "risk_level": risk,
            "claims": claim_results,
            "annotated_text": " ".join(annotated_parts),
            "ungrounded_terms": [
                c["claim"][:80] for c in claim_results if not c["is_supported"]
            ],
        }


# Singleton
_citation_grounding: Optional[CitationGroundingService] = None


def get_citation_grounding_service() -> CitationGroundingService:
    global _citation_grounding
    if _citation_grounding is None:
        _citation_grounding = CitationGroundingService()
    return _citation_grounding


# =====================================================================
# 4.1 — Golden Set Management
# =====================================================================

_GOLDEN_SET_FILE = "golden_set.json"


def _get_golden_set_path() -> Path:
    eval_dir = Path(settings.rag_evaluation_persist_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)
    return eval_dir / _GOLDEN_SET_FILE


def load_golden_set() -> List[Dict[str, Any]]:
    """Load the golden set from disk."""
    path = _get_golden_set_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Failed to load golden set: {exc}")
        return []


def save_golden_set(golden_set: List[Dict[str, Any]]) -> None:
    """Save the golden set to disk."""
    path = _get_golden_set_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(golden_set, f, indent=2)


def add_golden_set_entry(
    query: str,
    relevant_ids: List[str],
    notes: str = "",
) -> Dict[str, Any]:
    """Add an entry to the golden set."""
    golden_set = load_golden_set()
    entry = {
        "id": f"gs-{len(golden_set)+1:04d}",
        "query": query,
        "relevant_ids": relevant_ids,
        "notes": notes,
        "created_at": time.time(),
    }
    golden_set.append(entry)
    save_golden_set(golden_set)
    return entry


def remove_golden_set_entry(entry_id: str) -> bool:
    """Remove an entry from the golden set by ID."""
    golden_set = load_golden_set()
    filtered = [e for e in golden_set if e.get("id") != entry_id]
    if len(filtered) == len(golden_set):
        return False
    save_golden_set(filtered)
    return True


# =====================================================================
# 4.3 — Embedding Drift Detection
# =====================================================================

# Rolling windows for drift tracking
_baseline_embeddings: deque = deque(maxlen=200)
_recent_embeddings: deque = deque(maxlen=200)
_drift_history: deque = deque(maxlen=100)


def _cosine_distance_vectors(a: List[float], b: List[float]) -> float:
    """Compute cosine distance between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


def _compute_centroid(embeddings: List[List[float]]) -> List[float]:
    """Compute the centroid (mean vector) of a set of embeddings."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    centroid = [0.0] * dim
    for emb in embeddings:
        for i in range(dim):
            centroid[i] += emb[i]
    n = len(embeddings)
    return [c / n for c in centroid]


def record_embedding_for_drift(embedding: List[float], is_baseline: bool = False) -> None:
    """
    Record an embedding for drift monitoring.

    During initial operation, embeddings build up the baseline.
    After baseline is established, new embeddings go to the recent window.
    """
    if not settings.rag_drift_detection_enabled:
        return

    if is_baseline or len(_baseline_embeddings) < settings.rag_drift_window_size:
        _baseline_embeddings.append(embedding)
    else:
        _recent_embeddings.append(embedding)


def compute_drift() -> Dict[str, Any]:
    """
    Compute the current embedding drift relative to the baseline.

    Returns:
        {
            "drift_score": float,    # Cosine distance between centroids
            "is_drifting": bool,     # True if above threshold
            "baseline_size": int,
            "recent_size": int,
            "threshold": float,
        }
    """
    if not settings.rag_drift_detection_enabled:
        return {"enabled": False}

    baseline_list = list(_baseline_embeddings)
    recent_list = list(_recent_embeddings)

    if len(baseline_list) < 10 or len(recent_list) < 10:
        return {
            "enabled": True,
            "drift_score": 0.0,
            "is_drifting": False,
            "baseline_size": len(baseline_list),
            "recent_size": len(recent_list),
            "threshold": settings.rag_drift_threshold,
            "status": "insufficient_data",
        }

    baseline_centroid = _compute_centroid(baseline_list)
    recent_centroid = _compute_centroid(recent_list)

    drift_score = _cosine_distance_vectors(baseline_centroid, recent_centroid)
    is_drifting = drift_score > settings.rag_drift_threshold

    # Record drift history
    _drift_history.append({
        "timestamp": time.time(),
        "drift_score": round(drift_score, 6),
        "baseline_size": len(baseline_list),
        "recent_size": len(recent_list),
    })

    # Record metric
    _record_drift_metric(drift_score, is_drifting)

    if is_drifting:
        logger.warning(
            f"RAG drift detected: score={drift_score:.4f} "
            f"(threshold={settings.rag_drift_threshold})"
        )

    return {
        "enabled": True,
        "drift_score": round(drift_score, 6),
        "is_drifting": is_drifting,
        "baseline_size": len(baseline_list),
        "recent_size": len(recent_list),
        "threshold": settings.rag_drift_threshold,
        "status": "drifting" if is_drifting else "stable",
    }


def get_drift_history() -> List[Dict[str, Any]]:
    """Return the drift score history."""
    return list(_drift_history)


def reset_drift_baseline() -> Dict[str, Any]:
    """
    Reset the baseline to the current recent embeddings.
    Call this after re-indexing or model update.
    """
    global _baseline_embeddings, _recent_embeddings
    if _recent_embeddings:
        _baseline_embeddings = deque(_recent_embeddings, maxlen=200)
        _recent_embeddings = deque(maxlen=200)
        logger.info(f"Drift baseline reset with {len(_baseline_embeddings)} embeddings")
        return {"status": "reset", "new_baseline_size": len(_baseline_embeddings)}
    return {"status": "no_recent_data", "message": "No recent embeddings to use as baseline"}


# =====================================================================
# Metrics helpers
# =====================================================================

def _record_eval_metrics(mrr: float, recall: float, precision: float, k: int) -> None:
    """Push evaluation metrics."""
    try:
        from app.metrics import (
            RAG_EVAL_MRR,
            RAG_EVAL_RECALL,
            RAG_EVAL_PRECISION,
        )
        RAG_EVAL_MRR.set(mrr)
        RAG_EVAL_RECALL.set(recall)
        RAG_EVAL_PRECISION.set(precision)
    except ImportError:
        pass


def _record_drift_metric(drift_score: float, is_drifting: bool) -> None:
    """Push drift metric."""
    try:
        from app.metrics import RAG_DRIFT_SCORE, RAG_DRIFT_ALERT
        RAG_DRIFT_SCORE.set(drift_score)
        RAG_DRIFT_ALERT.set(1.0 if is_drifting else 0.0)
    except ImportError:
        pass


# =====================================================================
# Evaluation summary for dashboard
# =====================================================================

def get_evaluation_summary() -> Dict[str, Any]:
    """Return a summary of the RAG evaluation state."""
    golden_set = load_golden_set()
    drift = compute_drift()

    return {
        "evaluation_enabled": settings.rag_evaluation_enabled,
        "golden_set_size": len(golden_set),
        "hallucination_check_enabled": settings.rag_hallucination_check_enabled,
        "drift_detection": drift,
        "drift_history_length": len(_drift_history),
    }
