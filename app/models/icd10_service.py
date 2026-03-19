"""
ICD-10 Ontology Service (Phase 2.2)

Provides semantic ICD-10 code matching using vector embeddings.  Instead of
exact string lookups, symptoms described in natural language are embedded and
matched against a curated set of ICD-10 code descriptions.

Features:
- Semantic search:  "chest tightness" matches I20.9 (Angina pectoris, unspecified)
- Cross-validation:  validates NER-extracted codes against embedding-matched codes
- Hierarchical:      includes chapter and block context for each code
- Batch lookup:      process multiple symptoms in one call
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_icd10_collection = None


def _get_icd10_collection():
    """Lazy-load the ICD-10 ChromaDB collection."""
    global _icd10_collection
    if _icd10_collection is None:
        import chromadb
        persist_dir = settings.knowledge_base_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=persist_dir)
        _icd10_collection = client.get_or_create_collection(
            name="icd10_codes",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ICD-10 collection ready ({_icd10_collection.count()} codes)"
        )
    return _icd10_collection


def _embed(text: str) -> List[float]:
    """Reuse the RAG embedding model for consistency."""
    from app.models.rag_service import _get_embedding_model
    model = _get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


# ---------------------------------------------------------------------------
# Curated ICD-10 seed data — common triage-relevant codes
# ---------------------------------------------------------------------------
# In production, this would be loaded from the full CMS ICD-10-CM code set
# (~70k codes). This subset covers the most common triage presentations.

ICD10_SEED_CODES: List[Dict[str, str]] = [
    # ── Respiratory ──
    {"code": "J06.9",  "description": "Acute upper respiratory infection, unspecified", "chapter": "X", "block": "J00-J06"},
    {"code": "J18.9",  "description": "Pneumonia, unspecified organism", "chapter": "X", "block": "J09-J18"},
    {"code": "J20.9",  "description": "Acute bronchitis, unspecified", "chapter": "X", "block": "J20-J22"},
    {"code": "J45.20", "description": "Mild intermittent asthma, uncomplicated", "chapter": "X", "block": "J44-J47"},
    {"code": "J45.40", "description": "Moderate persistent asthma, uncomplicated", "chapter": "X", "block": "J44-J47"},
    {"code": "J45.901","description": "Asthma exacerbation, unspecified", "chapter": "X", "block": "J44-J47"},
    {"code": "R05.9",  "description": "Cough, unspecified", "chapter": "XVIII", "block": "R00-R09"},
    {"code": "R06.00", "description": "Dyspnea, unspecified (shortness of breath)", "chapter": "XVIII", "block": "R00-R09"},
    {"code": "R06.2",  "description": "Wheezing", "chapter": "XVIII", "block": "R00-R09"},
    {"code": "J44.1",  "description": "Chronic obstructive pulmonary disease with acute exacerbation", "chapter": "X", "block": "J44-J47"},

    # ── Cardiovascular ──
    {"code": "I20.9",  "description": "Angina pectoris, unspecified (chest pain cardiac)", "chapter": "IX", "block": "I20-I25"},
    {"code": "I21.9",  "description": "Acute myocardial infarction, unspecified (heart attack)", "chapter": "IX", "block": "I20-I25"},
    {"code": "I25.10", "description": "Atherosclerotic heart disease of native coronary artery", "chapter": "IX", "block": "I20-I25"},
    {"code": "I10",    "description": "Essential primary hypertension (high blood pressure)", "chapter": "IX", "block": "I10-I16"},
    {"code": "I26.99", "description": "Pulmonary embolism without acute cor pulmonale", "chapter": "IX", "block": "I26-I28"},
    {"code": "I48.91", "description": "Atrial fibrillation, unspecified", "chapter": "IX", "block": "I30-I52"},
    {"code": "R00.0",  "description": "Tachycardia, unspecified (rapid heartbeat)", "chapter": "XVIII", "block": "R00-R09"},
    {"code": "R00.2",  "description": "Palpitations (heart pounding)", "chapter": "XVIII", "block": "R00-R09"},
    {"code": "R07.9",  "description": "Chest pain, unspecified", "chapter": "XVIII", "block": "R00-R09"},

    # ── Neurological ──
    {"code": "G43.909","description": "Migraine, unspecified, not intractable", "chapter": "VI", "block": "G43-G44"},
    {"code": "G44.1",  "description": "Vascular headache, not elsewhere classified", "chapter": "VI", "block": "G43-G44"},
    {"code": "R51.9",  "description": "Headache, unspecified", "chapter": "XVIII", "block": "R50-R69"},
    {"code": "R42",    "description": "Dizziness and giddiness (vertigo, lightheadedness)", "chapter": "XVIII", "block": "R40-R46"},
    {"code": "R55",    "description": "Syncope and collapse (fainting)", "chapter": "XVIII", "block": "R50-R69"},
    {"code": "G45.9",  "description": "Transient cerebral ischemic attack, unspecified (TIA)", "chapter": "VI", "block": "G45-G46"},
    {"code": "R20.2",  "description": "Paresthesia of skin (numbness, tingling)", "chapter": "XVIII", "block": "R20-R23"},

    # ── Gastrointestinal ──
    {"code": "R10.9",  "description": "Abdominal pain, unspecified (stomach ache)", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "R10.10", "description": "Upper abdominal pain, unspecified (epigastric)", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "R10.30", "description": "Lower abdominal pain, unspecified", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "R11.0",  "description": "Nausea", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "R11.10", "description": "Vomiting, unspecified", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "R19.7",  "description": "Diarrhea, unspecified", "chapter": "XVIII", "block": "R10-R19"},
    {"code": "K21.0",  "description": "Gastroesophageal reflux disease with esophagitis (GERD, acid reflux)", "chapter": "XI", "block": "K20-K31"},
    {"code": "K35.80", "description": "Unspecified acute appendicitis", "chapter": "XI", "block": "K35-K38"},
    {"code": "K57.30", "description": "Diverticulosis of large intestine without perforation", "chapter": "XI", "block": "K55-K64"},
    {"code": "K85.90", "description": "Acute pancreatitis, unspecified", "chapter": "XI", "block": "K80-K87"},

    # ── Musculoskeletal ──
    {"code": "M54.5",  "description": "Low back pain (lumbago)", "chapter": "XIII", "block": "M50-M54"},
    {"code": "M54.2",  "description": "Cervicalgia (neck pain)", "chapter": "XIII", "block": "M50-M54"},
    {"code": "M54.30", "description": "Sciatica, unspecified side (radiating leg pain)", "chapter": "XIII", "block": "M50-M54"},
    {"code": "M79.3",  "description": "Panniculitis, unspecified (soft tissue inflammation)", "chapter": "XIII", "block": "M70-M79"},
    {"code": "M25.50", "description": "Joint pain, unspecified (arthralgia)", "chapter": "XIII", "block": "M20-M25"},

    # ── Infectious / Fever ──
    {"code": "R50.9",  "description": "Fever, unspecified", "chapter": "XVIII", "block": "R50-R69"},
    {"code": "A49.9",  "description": "Bacterial infection, unspecified", "chapter": "I", "block": "A30-A49"},
    {"code": "B34.9",  "description": "Viral infection, unspecified", "chapter": "I", "block": "B25-B34"},
    {"code": "A41.9",  "description": "Sepsis, unspecified organism", "chapter": "I", "block": "A40-A41"},

    # ── Genitourinary ──
    {"code": "N39.0",  "description": "Urinary tract infection, site not specified (UTI)", "chapter": "XIV", "block": "N30-N39"},
    {"code": "N10",    "description": "Acute pyelonephritis (kidney infection)", "chapter": "XIV", "block": "N10-N16"},
    {"code": "R30.0",  "description": "Dysuria (painful urination)", "chapter": "XVIII", "block": "R30-R39"},
    {"code": "R35.0",  "description": "Urinary frequency", "chapter": "XVIII", "block": "R30-R39"},

    # ── Mental Health ──
    {"code": "F41.9",  "description": "Anxiety disorder, unspecified", "chapter": "V", "block": "F40-F48"},
    {"code": "F32.9",  "description": "Major depressive disorder, single episode, unspecified", "chapter": "V", "block": "F30-F39"},
    {"code": "F41.0",  "description": "Panic disorder without agoraphobia (panic attack)", "chapter": "V", "block": "F40-F48"},
    {"code": "R45.851","description": "Suicidal ideation", "chapter": "XVIII", "block": "R40-R46"},

    # ── Endocrine ──
    {"code": "E11.65", "description": "Type 2 diabetes mellitus with hyperglycemia", "chapter": "IV", "block": "E08-E13"},
    {"code": "E10.10", "description": "Type 1 diabetes mellitus with ketoacidosis (DKA)", "chapter": "IV", "block": "E08-E13"},
    {"code": "E16.2",  "description": "Hypoglycemia, unspecified (low blood sugar)", "chapter": "IV", "block": "E15-E16"},

    # ── Allergy / Skin ──
    {"code": "T78.2",  "description": "Anaphylactic shock, unspecified (severe allergic reaction)", "chapter": "XIX", "block": "T66-T78"},
    {"code": "L50.9",  "description": "Urticaria, unspecified (hives)", "chapter": "XII", "block": "L50-L54"},
    {"code": "L03.90", "description": "Cellulitis, unspecified", "chapter": "XII", "block": "L00-L08"},
    {"code": "B02.9",  "description": "Zoster without complication (shingles)", "chapter": "I", "block": "B00-B09"},
    {"code": "L30.9",  "description": "Dermatitis, unspecified (eczema, rash)", "chapter": "XII", "block": "L20-L30"},

    # ── Trauma / Injury ──
    {"code": "S06.0X0A","description": "Concussion without loss of consciousness, initial encounter", "chapter": "XIX", "block": "S00-S09"},
    {"code": "S62.90", "description": "Fracture of unspecified wrist and hand", "chapter": "XIX", "block": "S60-S69"},
    {"code": "S82.90", "description": "Fracture of unspecified lower leg", "chapter": "XIX", "block": "S80-S89"},
    {"code": "T14.90", "description": "Injury, unspecified", "chapter": "XIX", "block": "T07-T14"},

    # ── Pediatric ──
    {"code": "J02.9",  "description": "Acute pharyngitis, unspecified (sore throat)", "chapter": "X", "block": "J00-J06"},
    {"code": "H66.90", "description": "Otitis media, unspecified (ear infection)", "chapter": "VIII", "block": "H65-H75"},
    {"code": "J21.9",  "description": "Acute bronchiolitis, unspecified", "chapter": "X", "block": "J20-J22"},
    {"code": "R56.00", "description": "Simple febrile convulsions (febrile seizure)", "chapter": "XVIII", "block": "R50-R69"},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def initialize_icd10_index(force_reseed: bool = False) -> Dict[str, Any]:
    """
    Initialize the ICD-10 vector index with curated codes.

    Returns stats about the index.
    """
    if not settings.icd10_lookup_enabled:
        return {"enabled": False}

    try:
        collection = _get_icd10_collection()
        current_count = collection.count()

        if current_count > 0 and not force_reseed:
            logger.info(f"ICD-10 index already initialized ({current_count} codes)")
            return {"enabled": True, "code_count": current_count, "action": "already_initialized"}

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for entry in ICD10_SEED_CODES:
            code = entry["code"]
            desc = entry["description"]
            # Embed the description (natural language) for semantic matching
            embed_text = f"{desc} (ICD-10: {code})"

            ids.append(code)
            embeddings.append(_embed(embed_text))
            documents.append(f"{code}: {desc}")
            metadatas.append({
                "code": code,
                "description": desc,
                "chapter": entry.get("chapter", ""),
                "block": entry.get("block", ""),
                "type": "icd10",
            })

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        final_count = collection.count()
        logger.info(f"ICD-10 index seeded with {final_count} codes")
        return {"enabled": True, "code_count": final_count, "action": "seeded"}

    except Exception as exc:
        logger.error(f"ICD-10 initialization failed: {exc}")
        return {"enabled": True, "error": str(exc)}


def lookup_icd10_codes(
    symptom_text: str,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic ICD-10 code lookup for a symptom description.

    Args:
        symptom_text: Natural language symptom (e.g. "sharp chest pain when breathing")
        top_k: Max results

    Returns:
        List of matching ICD-10 codes with similarity scores.
    """
    if not settings.icd10_lookup_enabled:
        return []

    try:
        collection = _get_icd10_collection()
        if collection.count() == 0:
            return []

        k = top_k or settings.icd10_top_k
        threshold = settings.icd10_similarity_threshold

        query_embedding = _embed(symptom_text)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k * 2, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        matches = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            similarity = max(0.0, 1.0 - distance)

            if similarity < threshold:
                continue

            meta = results["metadatas"][0][i]
            matches.append({
                "code": meta["code"],
                "description": meta["description"],
                "chapter": meta.get("chapter", ""),
                "block": meta.get("block", ""),
                "similarity": round(similarity, 4),
                "match_type": "semantic",
            })

            if len(matches) >= k:
                break

        return matches

    except Exception as exc:
        logger.warning(f"ICD-10 lookup failed: {exc}")
        return []


def batch_lookup_icd10(
    symptoms: List[str],
    top_k: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Look up ICD-10 codes for multiple symptoms at once.

    Args:
        symptoms: List of symptom texts
        top_k: Max results per symptom

    Returns:
        Dict mapping each symptom to its matched ICD-10 codes.
    """
    results = {}
    for symptom in symptoms:
        if symptom and symptom.strip() and symptom.lower() != "not specified":
            results[symptom] = lookup_icd10_codes(symptom, top_k=top_k)
    return results


def cross_validate_codes(
    ner_codes: List[Dict[str, str]],
    semantic_codes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Cross-validate NER-extracted codes against semantically matched codes.

    Returns enriched code list with validation status:
    - "validated": code appears in both NER and semantic results
    - "ner_only": code from NER, not confirmed by semantic match
    - "semantic_only": code from semantic match, not in NER results

    This helps clinicians assess code reliability.
    """
    ner_code_set = {c.get("code", "").split(".")[0] for c in ner_codes}  # Compare at category level
    semantic_code_set = {c.get("code", "").split(".")[0] for c in semantic_codes}

    validated = []

    # Process semantic codes
    for code_entry in semantic_codes:
        code_prefix = code_entry["code"].split(".")[0]
        entry = dict(code_entry)
        if code_prefix in ner_code_set:
            entry["validation_status"] = "validated"
            entry["confidence"] = "high"
        else:
            entry["validation_status"] = "semantic_only"
            entry["confidence"] = "medium"
        validated.append(entry)

    # Add NER-only codes not in semantic results
    for ner_code in ner_codes:
        code_prefix = ner_code.get("code", "").split(".")[0]
        if code_prefix not in semantic_code_set:
            validated.append({
                "code": ner_code.get("code", ""),
                "description": ner_code.get("text", ""),
                "system": ner_code.get("system", "ICD-10"),
                "validation_status": "ner_only",
                "confidence": "low",
                "similarity": 0.0,
            })

    return validated


def get_icd10_stats() -> Dict[str, Any]:
    """Return statistics about the ICD-10 index."""
    if not settings.icd10_lookup_enabled:
        return {"enabled": False}
    try:
        collection = _get_icd10_collection()
        return {
            "enabled": True,
            "code_count": collection.count(),
            "seed_codes_available": len(ICD10_SEED_CODES),
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}
