"""
Clinical Knowledge Base Service (Phase 2.1)

Manages a curated collection of clinical guidelines, protocols, and reference
material in a separate ChromaDB collection.  Retrieved guidelines are merged
with similar-session RAG results to give the LLM authoritative clinical
context alongside experience-based context.

Key design decisions:
- Separate ChromaDB collection from patient sessions (no PHI mixing)
- Guidelines are tagged with source, category, and condition
- Retrieval is merged at the prompt level, not the vector level
- Guidelines are clearly labelled "Clinical Reference" in the prompt
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_guidelines_collection = None
_chroma_client = None


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        persist_dir = settings.knowledge_base_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def _get_guidelines_collection():
    """Lazy-load the clinical guidelines ChromaDB collection."""
    global _guidelines_collection
    if _guidelines_collection is None:
        client = _get_chroma_client()
        _guidelines_collection = client.get_or_create_collection(
            name="clinical_guidelines",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"Knowledge base guidelines collection ready "
            f"({_guidelines_collection.count()} documents)"
        )
    return _guidelines_collection


def _embed(text: str) -> List[float]:
    """Reuse the RAG embedding model for consistency."""
    from app.models.rag_service import _get_embedding_model
    model = _get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


# ---------------------------------------------------------------------------
# Seed data — curated clinical guidelines
# ---------------------------------------------------------------------------

# Compact clinical guidelines covering common triage presentations.
# In production, these would be loaded from a maintained JSON/YAML file
# or fetched from an internal clinical-content API.

SEED_GUIDELINES: List[Dict[str, Any]] = [
    # ── Chest Pain ──
    {
        "id": "guideline-chest-pain-acs",
        "title": "Acute Coronary Syndrome (ACS) — Triage Guidelines",
        "source": "AHA/ACC",
        "category": "cardiology",
        "conditions": ["chest pain", "acute coronary syndrome", "myocardial infarction", "angina"],
        "content": (
            "Patients presenting with chest pain should be evaluated for acute coronary syndrome. "
            "Key red flags: chest pain radiating to left arm, jaw, or back; diaphoresis; nausea; "
            "shortness of breath; history of CAD or risk factors (diabetes, hypertension, smoking, "
            "hyperlipidemia, family history). Immediate actions: 12-lead ECG within 10 minutes, "
            "troponin levels, CBC, BMP, coagulation studies. If STEMI: activate cath lab. "
            "If NSTEMI/unstable angina: antiplatelet therapy, anticoagulation, cardiology consult. "
            "HEART score can stratify risk: History, ECG, Age, Risk factors, Troponin."
        ),
    },
    {
        "id": "guideline-chest-pain-pe",
        "title": "Pulmonary Embolism — Triage Guidelines",
        "source": "ACEP",
        "category": "pulmonology",
        "conditions": ["chest pain", "shortness of breath", "pulmonary embolism", "DVT"],
        "content": (
            "Consider pulmonary embolism in patients with acute chest pain and dyspnea, "
            "especially with risk factors: recent surgery, immobilization, malignancy, oral "
            "contraceptives, prior DVT/PE. Use Wells criteria or PERC rule for risk stratification. "
            "D-dimer for low-risk patients; CT pulmonary angiography for moderate/high risk. "
            "Signs: tachycardia, tachypnea, hypoxia, unilateral leg swelling. "
            "Treatment: anticoagulation with heparin, consider thrombolytics if massive PE."
        ),
    },
    # ── Respiratory ──
    {
        "id": "guideline-asthma-exacerbation",
        "title": "Asthma Exacerbation — Management Guidelines",
        "source": "GINA",
        "category": "pulmonology",
        "conditions": ["asthma", "wheezing", "shortness of breath", "dyspnea", "cough"],
        "content": (
            "Assess severity: mild (talks in sentences), moderate (talks in phrases), severe "
            "(talks in words), life-threatening (drowsy, confused, silent chest). "
            "Initial treatment: SABA (salbutamol) via nebulizer or MDI with spacer, ipratropium "
            "bromide for moderate-severe, systemic corticosteroids (prednisolone 40-50mg). "
            "Assess response at 1 hour. Monitor SpO2, peak flow, respiratory rate. "
            "Admit if: SpO2 < 92%, peak flow < 50% predicted, life-threatening features, "
            "previous near-fatal asthma, inability to speak."
        ),
    },
    {
        "id": "guideline-pneumonia-cap",
        "title": "Community-Acquired Pneumonia — Assessment Guidelines",
        "source": "ATS/IDSA",
        "category": "infectious_disease",
        "conditions": ["pneumonia", "cough", "fever", "shortness of breath", "chest pain"],
        "content": (
            "Diagnosis: productive cough, fever, dyspnea, pleuritic chest pain, crackles on "
            "auscultation. Confirm with chest X-ray. Use CURB-65 for severity: Confusion, "
            "Urea >7mmol/L, Respiratory rate ≥30, Blood pressure <90/60, Age ≥65. "
            "Score 0-1: outpatient. Score 2: short inpatient or supervised outpatient. "
            "Score 3-5: inpatient, consider ICU. Labs: CBC, BMP, blood cultures x2, "
            "sputum culture, Legionella/pneumococcal urine antigens. "
            "Empirical antibiotics: outpatient — amoxicillin or doxycycline; "
            "inpatient — beta-lactam + macrolide or respiratory fluoroquinolone."
        ),
    },
    # ── Headache ──
    {
        "id": "guideline-headache-red-flags",
        "title": "Headache Red Flags — Emergency Assessment",
        "source": "AAN",
        "category": "neurology",
        "conditions": ["headache", "migraine", "head pain", "thunderclap headache"],
        "content": (
            "Red flags (SNOOP mnemonic): Systemic symptoms (fever, weight loss, cancer, HIV), "
            "Neurologic symptoms (confusion, focal deficits, seizures, papilledema), "
            "Onset sudden/thunderclap, Older age (>50, new headache), Pattern change "
            "(progressive worsening, positional). Thunderclap headache: rule out subarachnoid "
            "hemorrhage with non-contrast CT head, followed by LP if CT negative. "
            "New headache with focal deficits: CT/MRI to rule out mass or stroke. "
            "Temporal arteritis in >50: ESR, CRP, temporal artery biopsy. "
            "Primary headaches (migraine, tension, cluster) are diagnoses of exclusion."
        ),
    },
    # ── Abdominal Pain ──
    {
        "id": "guideline-abdominal-pain",
        "title": "Acute Abdominal Pain — Triage Assessment",
        "source": "ACEP",
        "category": "gastroenterology",
        "conditions": ["abdominal pain", "stomach pain", "nausea", "vomiting", "diarrhea"],
        "content": (
            "Assessment by location: RUQ — biliary disease, hepatitis; Epigastric — peptic "
            "ulcer, pancreatitis, ACS; LUQ — splenic pathology; RLQ — appendicitis, ovarian "
            "torsion; LLQ — diverticulitis, ovarian pathology; Diffuse — obstruction, "
            "mesenteric ischemia, peritonitis. Red flags: rigid abdomen, rebound tenderness, "
            "hemodynamic instability, fever >38.5°C, blood in stool. "
            "Workup: CBC, BMP, lipase, LFTs, urinalysis, pregnancy test (females of "
            "childbearing age). CT abdomen/pelvis with contrast for undifferentiated pain. "
            "Surgical consult for signs of peritonitis or obstruction."
        ),
    },
    # ── Fever ──
    {
        "id": "guideline-fever-evaluation",
        "title": "Fever — Systematic Evaluation",
        "source": "IDSA",
        "category": "infectious_disease",
        "conditions": ["fever", "chills", "infection", "sepsis"],
        "content": (
            "Fever ≥38.0°C (100.4°F). Evaluate for source: respiratory (cough, dyspnea), "
            "urinary (dysuria, frequency), abdominal (pain, diarrhea), skin/soft tissue "
            "(erythema, swelling), CNS (headache, neck stiffness, altered mental status). "
            "Screen for sepsis using qSOFA: altered mental status, RR ≥22, SBP ≤100. "
            "If ≥2 qSOFA criteria: suspect sepsis, obtain lactate, blood cultures x2, "
            "begin empiric antibiotics within 1 hour, IV fluid resuscitation 30mL/kg. "
            "Immunocompromised patients (chemotherapy, HIV, transplant): lower threshold "
            "for workup and admission. Neutropenic fever is an emergency."
        ),
    },
    # ── Back Pain ──
    {
        "id": "guideline-back-pain",
        "title": "Low Back Pain — Red Flag Assessment",
        "source": "ACP",
        "category": "musculoskeletal",
        "conditions": ["back pain", "low back pain", "sciatica", "radiculopathy"],
        "content": (
            "Red flags requiring urgent evaluation: cauda equina syndrome (saddle anesthesia, "
            "urinary retention, bilateral leg weakness), spinal infection (fever, IV drug use, "
            "recent procedure), malignancy (history of cancer, unexplained weight loss, "
            "age >50 with new onset), fracture (trauma, osteoporosis, steroid use). "
            "Cauda equina: emergent MRI, surgical decompression. "
            "Without red flags: conservative management — NSAIDs, activity modification, "
            "physical therapy. Imaging not indicated in first 6 weeks unless red flags present. "
            "Radiculopathy with progressive weakness: MRI lumbar spine, neurosurgery referral."
        ),
    },
    # ── Dizziness ──
    {
        "id": "guideline-dizziness-vertigo",
        "title": "Dizziness and Vertigo — Differential Assessment",
        "source": "AAN",
        "category": "neurology",
        "conditions": ["dizziness", "vertigo", "lightheadedness", "syncope", "fainting"],
        "content": (
            "Classify: true vertigo (room spinning — vestibular) vs lightheadedness "
            "(presyncope — cardiovascular/metabolic) vs disequilibrium (unsteadiness — "
            "neurologic/musculoskeletal). HINTS exam for acute vestibular syndrome: "
            "Head Impulse, Nystagmus, Test of Skew — central pattern suggests stroke. "
            "Peripheral causes: BPPV (Dix-Hallpike positive), vestibular neuritis, "
            "Meniere's disease. Central causes: posterior circulation stroke, MS, "
            "cerebellar lesion. Red flags: acute onset with neurologic symptoms, "
            "new headache, cannot walk, vertical nystagmus, skew deviation. "
            "Workup if central suspected: MRI brain with diffusion-weighted imaging."
        ),
    },
    # ── Skin / Rash ──
    {
        "id": "guideline-rash-assessment",
        "title": "Acute Rash — Assessment Guidelines",
        "source": "AAD",
        "category": "dermatology",
        "conditions": ["rash", "skin lesion", "hives", "urticaria", "allergic reaction"],
        "content": (
            "Determine: onset, distribution, morphology (macular, papular, vesicular, "
            "petechial, purpuric), associated symptoms (fever, pruritus, pain). "
            "Emergencies: petechial/purpuric rash with fever (meningococcemia, DIC), "
            "anaphylaxis (urticaria + airway compromise + hypotension), Stevens-Johnson "
            "syndrome/TEN (target lesions, mucosal involvement, skin sloughing >10% BSA). "
            "New medication within 2-6 weeks: suspect drug reaction. "
            "Dermatome distribution with vesicles: herpes zoster. "
            "Widespread urticaria without systemic symptoms: antihistamines, observe. "
            "Cellulitis: warm, erythematous, tender — antibiotics targeting Staph/Strep."
        ),
    },
    # ── Mental Health ──
    {
        "id": "guideline-mental-health-crisis",
        "title": "Mental Health Crisis — Safety Assessment",
        "source": "APA",
        "category": "psychiatry",
        "conditions": ["anxiety", "depression", "suicidal ideation", "panic attack", "mental health"],
        "content": (
            "Suicide risk assessment: ask directly about suicidal ideation, plan, intent, "
            "access to means, prior attempts. Use Columbia Suicide Severity Rating Scale. "
            "High risk: active plan with intent and access to means — do not leave alone, "
            "psychiatric emergency evaluation. Moderate risk: ideation without plan — "
            "safety planning, crisis resources, close follow-up. "
            "Panic attack presentation: reassure, rule out cardiac/pulmonary causes "
            "if first episode or atypical features. "
            "Acute agitation: verbal de-escalation first, consider PO benzodiazepine "
            "or antipsychotic if needed for safety. Document capacity assessment."
        ),
    },
    # ── Diabetes ──
    {
        "id": "guideline-diabetic-emergency",
        "title": "Diabetic Emergencies — DKA and Hypoglycemia",
        "source": "ADA",
        "category": "endocrinology",
        "conditions": ["diabetes", "high blood sugar", "low blood sugar", "DKA", "hyperglycemia", "hypoglycemia"],
        "content": (
            "DKA criteria: glucose >250mg/dL, pH <7.3, bicarbonate <18, positive ketones, "
            "anion gap >12. Treatment: IV fluids (NS 1-1.5L/hr first hour), insulin drip "
            "(0.1-0.14 units/kg/hr), potassium replacement (if K <5.3), monitor glucose "
            "hourly, BMP q2-4h. Transition to subQ insulin when gap closes, patient eating. "
            "Hypoglycemia: glucose <70mg/dL. Mild: 15-20g fast-acting carbs, recheck 15min. "
            "Severe (altered consciousness): IV dextrose 25g (D50) or glucagon 1mg IM. "
            "Identify precipitant: missed meal, excess insulin, new medication, infection."
        ),
    },
    # ── Pediatric Fever ──
    {
        "id": "guideline-pediatric-fever",
        "title": "Pediatric Fever — Age-Based Assessment",
        "source": "AAP",
        "category": "pediatrics",
        "conditions": ["pediatric fever", "child fever", "infant fever", "fever in children"],
        "content": (
            "Neonates (0-28 days): any fever ≥38.0°C requires full sepsis workup (blood, "
            "urine, CSF cultures), empiric antibiotics (ampicillin + gentamicin), admission. "
            "Infants 29-60 days: Rochester/Philadelphia criteria to stratify; low-risk may "
            "be managed with close follow-up, high-risk requires workup and antibiotics. "
            "Infants 61-90 days: urinalysis, consider blood cultures, individualized approach. "
            "Children >3 months: focus on source — URI, otitis media, UTI, pneumonia. "
            "Red flags at any age: petechial rash, bulging fontanelle, inconsolable crying, "
            "lethargy, respiratory distress, poor feeding, immunocompromised status."
        ),
    },
    # ── Allergic Reaction ──
    {
        "id": "guideline-anaphylaxis",
        "title": "Anaphylaxis — Emergency Management",
        "source": "WAO",
        "category": "allergy_immunology",
        "conditions": ["allergic reaction", "anaphylaxis", "swelling", "difficulty breathing", "hives"],
        "content": (
            "Anaphylaxis criteria: acute onset (minutes to hours) involving skin/mucosal "
            "tissue PLUS respiratory compromise OR hypotension. Or: two or more of — "
            "skin symptoms, respiratory symptoms, GI symptoms, hypotension after known "
            "allergen exposure. Immediate management: IM epinephrine 0.3-0.5mg (1:1000) "
            "into anterolateral thigh — FIRST-LINE, do not delay. Repeat q5-15min if needed. "
            "Adjuncts: IV fluids for hypotension, albuterol for bronchospasm, "
            "antihistamines (diphenhydramine + famotidine), methylprednisolone 125mg IV. "
            "Observe minimum 4-6 hours for biphasic reaction. Prescribe epinephrine "
            "auto-injector and allergist referral on discharge."
        ),
    },
    # ── Urinary ──
    {
        "id": "guideline-uti-pyelonephritis",
        "title": "Urinary Tract Infection — Assessment and Management",
        "source": "IDSA",
        "category": "urology",
        "conditions": ["UTI", "urinary tract infection", "dysuria", "urinary frequency", "flank pain"],
        "content": (
            "Uncomplicated cystitis (women): dysuria, frequency, urgency without systemic "
            "symptoms. Treatment: nitrofurantoin 5 days or TMP-SMX 3 days (if local "
            "resistance <20%). Complicated UTI: male sex, pregnancy, structural abnormality, "
            "catheter, immunosuppression, diabetes. Pyelonephritis: fever, flank pain, "
            "CVA tenderness, nausea/vomiting. Workup: UA with culture, CBC, BMP. "
            "Imaging (CT or US) if: no improvement in 48-72 hours, suspected obstruction, "
            "recurrent pyelonephritis. Admission for: sepsis, intractable vomiting, "
            "pregnancy, obstruction, immunocompromised."
        ),
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def initialize_knowledge_base(force_reseed: bool = False) -> Dict[str, Any]:
    """
    Initialize the clinical guidelines knowledge base.

    Seeds the collection with curated guidelines if empty or if force_reseed
    is True.  Safe to call multiple times — uses upsert.

    Returns stats about the knowledge base.
    """
    if not settings.knowledge_base_enabled:
        return {"enabled": False}

    try:
        collection = _get_guidelines_collection()
        current_count = collection.count()

        if current_count > 0 and not force_reseed:
            logger.info(f"Knowledge base already initialized ({current_count} guidelines)")
            return {"enabled": True, "guidelines_count": current_count, "action": "already_initialized"}

        # Seed guidelines
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for guideline in SEED_GUIDELINES:
            gid = guideline["id"]
            # Embed: title + conditions + content for rich semantic matching
            embed_text = (
                f"{guideline['title']}. "
                f"Conditions: {', '.join(guideline['conditions'])}. "
                f"{guideline['content']}"
            )
            ids.append(gid)
            embeddings.append(_embed(embed_text))
            documents.append(
                f"[{guideline['source']}] {guideline['title']}\n\n{guideline['content']}"
            )
            metadatas.append({
                "source": guideline["source"],
                "category": guideline["category"],
                "conditions": ", ".join(guideline["conditions"]),
                "type": "clinical_guideline",
            })

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        final_count = collection.count()
        logger.info(f"Knowledge base seeded with {final_count} clinical guidelines")
        return {
            "enabled": True,
            "guidelines_count": final_count,
            "action": "seeded",
        }

    except Exception as exc:
        logger.error(f"Knowledge base initialization failed: {exc}")
        return {"enabled": True, "error": str(exc)}


def retrieve_guidelines(
    query: str,
    top_k: Optional[int] = None,
    category_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant clinical guidelines for a patient presentation.

    Args:
        query: Patient transcript or chief complaint
        top_k: Max results (default from settings)
        category_filter: Optional category to narrow results (e.g. "cardiology")

    Returns:
        List of guideline dicts with: id, document, metadata, similarity, source
    """
    if not settings.knowledge_base_enabled:
        return []

    try:
        collection = _get_guidelines_collection()
        if collection.count() == 0:
            logger.debug("Knowledge base is empty — call initialize_knowledge_base() first")
            return []

        k = top_k or settings.knowledge_base_guidelines_top_k
        threshold = settings.knowledge_base_guidelines_threshold

        query_embedding = _embed(query)

        where_filter = None
        if category_filter:
            where_filter = {"category": category_filter}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k * 2, collection.count()),  # fetch extra for filtering
            include=["documents", "metadatas", "distances"],
            where=where_filter,
        )

        guidelines = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            similarity = max(0.0, 1.0 - distance)

            if similarity < threshold:
                continue

            guidelines.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": round(similarity, 4),
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "type": "clinical_guideline",
            })

            if len(guidelines) >= k:
                break

        logger.info(
            f"Knowledge base: retrieved {len(guidelines)} guidelines "
            f"(threshold={threshold})"
        )
        return guidelines

    except Exception as exc:
        logger.warning(f"Knowledge base retrieval failed: {exc}")
        return []


def get_knowledge_base_stats() -> Dict[str, Any]:
    """Return statistics about the clinical knowledge base."""
    if not settings.knowledge_base_enabled:
        return {"enabled": False}
    try:
        collection = _get_guidelines_collection()
        return {
            "enabled": True,
            "guidelines_count": collection.count(),
            "available_seed_guidelines": len(SEED_GUIDELINES),
            "persist_dir": settings.knowledge_base_persist_dir,
        }
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}


def add_guideline(
    guideline_id: str,
    title: str,
    content: str,
    source: str,
    category: str,
    conditions: List[str],
) -> Dict[str, Any]:
    """
    Add a custom clinical guideline to the knowledge base.

    Used by admins to expand the knowledge base beyond the seed data.
    """
    if not settings.knowledge_base_enabled:
        return {"error": "Knowledge base is disabled"}

    try:
        collection = _get_guidelines_collection()

        embed_text = (
            f"{title}. Conditions: {', '.join(conditions)}. {content}"
        )
        document = f"[{source}] {title}\n\n{content}"

        collection.upsert(
            ids=[guideline_id],
            embeddings=[_embed(embed_text)],
            documents=[document],
            metadatas=[{
                "source": source,
                "category": category,
                "conditions": ", ".join(conditions),
                "type": "clinical_guideline",
            }],
        )

        logger.info(f"Knowledge base: added guideline '{guideline_id}'")
        return {"status": "indexed", "id": guideline_id}

    except Exception as exc:
        logger.warning(f"Knowledge base: failed to add guideline: {exc}")
        return {"error": str(exc)}


def remove_guideline(guideline_id: str) -> Dict[str, Any]:
    """Remove a guideline from the knowledge base."""
    if not settings.knowledge_base_enabled:
        return {"error": "Knowledge base is disabled"}
    try:
        collection = _get_guidelines_collection()
        collection.delete(ids=[guideline_id])
        logger.info(f"Knowledge base: removed guideline '{guideline_id}'")
        return {"status": "removed", "id": guideline_id}
    except Exception as exc:
        return {"error": str(exc)}
