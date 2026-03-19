"""
Drug Interaction Service (Phase 2.3)

Checks for potential drug-drug interactions and contraindications when
medications are mentioned in a patient transcript.  Results are flagged
in the Assessment section for clinician review.

Data source:
- Curated interaction database covering the most clinically significant
  drug-drug interactions (severity: major / moderate / minor).
- In production, this would integrate with a live API such as OpenFDA,
  DrugBank, or RxNorm interaction endpoints.

Design:
- Interactions are stored in-memory (no vector store needed — exact matching)
- Medications are normalised to lowercase generic names
- Supports alias resolution (brand → generic)
- Returns severity-ranked interaction list
"""

import logging
from typing import List, Dict, Any, Optional, Set

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand → Generic alias map (common US brand names)
# ---------------------------------------------------------------------------
BRAND_TO_GENERIC: Dict[str, str] = {
    # Cardiovascular
    "lipitor": "atorvastatin", "crestor": "rosuvastatin", "zocor": "simvastatin",
    "plavix": "clopidogrel", "eliquis": "apixaban", "xarelto": "rivaroxaban",
    "coumadin": "warfarin", "lovenox": "enoxaparin",
    "norvasc": "amlodipine", "lisinopril": "lisinopril",
    "metoprolol": "metoprolol", "lopressor": "metoprolol", "toprol": "metoprolol",
    "lasix": "furosemide", "hctz": "hydrochlorothiazide",
    "coreg": "carvedilol", "digoxin": "digoxin", "lanoxin": "digoxin",
    # Pain / Anti-inflammatory
    "tylenol": "acetaminophen", "advil": "ibuprofen", "motrin": "ibuprofen",
    "aleve": "naproxen", "celebrex": "celecoxib",
    "aspirin": "aspirin", "bayer": "aspirin",
    "percocet": "oxycodone", "vicodin": "hydrocodone", "norco": "hydrocodone",
    "tramadol": "tramadol", "ultram": "tramadol",
    "morphine": "morphine", "fentanyl": "fentanyl", "duragesic": "fentanyl",
    "gabapentin": "gabapentin", "neurontin": "gabapentin",
    "lyrica": "pregabalin",
    # Antibiotics
    "amoxicillin": "amoxicillin", "augmentin": "amoxicillin-clavulanate",
    "zithromax": "azithromycin", "z-pack": "azithromycin",
    "cipro": "ciprofloxacin", "levaquin": "levofloxacin",
    "bactrim": "trimethoprim-sulfamethoxazole", "septra": "trimethoprim-sulfamethoxazole",
    "doxycycline": "doxycycline", "metronidazole": "metronidazole", "flagyl": "metronidazole",
    "keflex": "cephalexin", "clindamycin": "clindamycin",
    # Mental Health
    "zoloft": "sertraline", "lexapro": "escitalopram", "prozac": "fluoxetine",
    "paxil": "paroxetine", "cymbalta": "duloxetine", "effexor": "venlafaxine",
    "wellbutrin": "bupropion", "trazodone": "trazodone",
    "xanax": "alprazolam", "ativan": "lorazepam", "valium": "diazepam",
    "klonopin": "clonazepam", "ambien": "zolpidem",
    "seroquel": "quetiapine", "abilify": "aripiprazole",
    "lithium": "lithium", "lamictal": "lamotrigine",
    # Diabetes
    "metformin": "metformin", "glucophage": "metformin",
    "insulin": "insulin", "lantus": "insulin glargine", "humalog": "insulin lispro",
    "jardiance": "empagliflozin", "ozempic": "semaglutide", "trulicity": "dulaglutide",
    "glipizide": "glipizide", "glyburide": "glyburide",
    # GI
    "omeprazole": "omeprazole", "prilosec": "omeprazole",
    "pantoprazole": "pantoprazole", "protonix": "pantoprazole",
    "nexium": "esomeprazole", "pepcid": "famotidine",
    "ondansetron": "ondansetron", "zofran": "ondansetron",
    # Respiratory
    "albuterol": "albuterol", "ventolin": "albuterol", "proair": "albuterol",
    "prednisone": "prednisone", "prednisolone": "prednisolone",
    "montelukast": "montelukast", "singulair": "montelukast",
    # Allergy
    "benadryl": "diphenhydramine", "zyrtec": "cetirizine", "claritin": "loratadine",
    "flonase": "fluticasone",
    # Other
    "synthroid": "levothyroxine", "levothyroxine": "levothyroxine",
    "epinephrine": "epinephrine", "epipen": "epinephrine",
}


# ---------------------------------------------------------------------------
# Drug interaction database — clinically significant interactions
# ---------------------------------------------------------------------------
# Structure: {frozenset({drug_a, drug_b}): interaction_info}
# Severity: "major" (potentially life-threatening), "moderate" (may require
# intervention), "minor" (minimal clinical significance)

INTERACTION_DB: List[Dict[str, Any]] = [
    # ── Major interactions ──
    {
        "drugs": {"warfarin", "aspirin"},
        "severity": "major",
        "effect": "Increased bleeding risk",
        "mechanism": "Additive anticoagulant/antiplatelet effects",
        "recommendation": "Monitor INR closely; consider GI prophylaxis; assess bleeding risk-benefit",
    },
    {
        "drugs": {"warfarin", "ibuprofen"},
        "severity": "major",
        "effect": "Increased bleeding risk and potential GI hemorrhage",
        "mechanism": "NSAIDs inhibit platelet function and may increase warfarin levels",
        "recommendation": "Avoid combination if possible; use acetaminophen instead for pain",
    },
    {
        "drugs": {"warfarin", "naproxen"},
        "severity": "major",
        "effect": "Increased bleeding risk and potential GI hemorrhage",
        "mechanism": "NSAIDs inhibit platelet function and may increase warfarin levels",
        "recommendation": "Avoid combination if possible; use acetaminophen instead for pain",
    },
    {
        "drugs": {"methotrexate", "trimethoprim-sulfamethoxazole"},
        "severity": "major",
        "effect": "Increased methotrexate toxicity (pancytopenia, mucositis)",
        "mechanism": "TMP-SMX inhibits renal tubular secretion of methotrexate and both are antifolates",
        "recommendation": "Avoid combination; use alternative antibiotic",
    },
    {
        "drugs": {"sertraline", "tramadol"},
        "severity": "major",
        "effect": "Risk of serotonin syndrome (agitation, hyperthermia, clonus, tachycardia)",
        "mechanism": "Additive serotonergic effects",
        "recommendation": "Avoid combination or use with extreme caution; monitor for serotonin syndrome symptoms",
    },
    {
        "drugs": {"fluoxetine", "tramadol"},
        "severity": "major",
        "effect": "Risk of serotonin syndrome",
        "mechanism": "Additive serotonergic effects",
        "recommendation": "Avoid combination or use with extreme caution",
    },
    {
        "drugs": {"escitalopram", "tramadol"},
        "severity": "major",
        "effect": "Risk of serotonin syndrome",
        "mechanism": "Additive serotonergic effects",
        "recommendation": "Avoid combination or use with extreme caution",
    },
    {
        "drugs": {"lithium", "ibuprofen"},
        "severity": "major",
        "effect": "Increased lithium levels — risk of toxicity",
        "mechanism": "NSAIDs reduce renal lithium clearance",
        "recommendation": "Monitor lithium levels closely; consider acetaminophen or reduced lithium dose",
    },
    {
        "drugs": {"lithium", "naproxen"},
        "severity": "major",
        "effect": "Increased lithium levels — risk of toxicity",
        "mechanism": "NSAIDs reduce renal lithium clearance",
        "recommendation": "Monitor lithium levels closely; consider acetaminophen",
    },
    {
        "drugs": {"digoxin", "amiodarone"},
        "severity": "major",
        "effect": "Increased digoxin levels — risk of toxicity (bradycardia, arrhythmia)",
        "mechanism": "Amiodarone inhibits P-glycoprotein and renal clearance of digoxin",
        "recommendation": "Reduce digoxin dose by 50%; monitor digoxin levels and heart rate",
    },
    {
        "drugs": {"clopidogrel", "omeprazole"},
        "severity": "major",
        "effect": "Reduced antiplatelet efficacy of clopidogrel",
        "mechanism": "Omeprazole inhibits CYP2C19, preventing clopidogrel activation",
        "recommendation": "Use pantoprazole or famotidine instead of omeprazole",
    },
    {
        "drugs": {"clopidogrel", "esomeprazole"},
        "severity": "major",
        "effect": "Reduced antiplatelet efficacy of clopidogrel",
        "mechanism": "Esomeprazole inhibits CYP2C19",
        "recommendation": "Use pantoprazole or famotidine instead",
    },
    {
        "drugs": {"oxycodone", "alprazolam"},
        "severity": "major",
        "effect": "Risk of profound sedation, respiratory depression, death",
        "mechanism": "Combined CNS depression from opioid + benzodiazepine",
        "recommendation": "FDA black box warning — avoid concurrent use unless no alternatives",
    },
    {
        "drugs": {"hydrocodone", "alprazolam"},
        "severity": "major",
        "effect": "Risk of profound sedation, respiratory depression, death",
        "mechanism": "Combined CNS depression from opioid + benzodiazepine",
        "recommendation": "FDA black box warning — avoid concurrent use unless no alternatives",
    },
    {
        "drugs": {"morphine", "lorazepam"},
        "severity": "major",
        "effect": "Risk of profound sedation, respiratory depression, death",
        "mechanism": "Combined CNS depression from opioid + benzodiazepine",
        "recommendation": "FDA black box warning — avoid concurrent use unless no alternatives",
    },
    {
        "drugs": {"fentanyl", "diazepam"},
        "severity": "major",
        "effect": "Risk of profound sedation, respiratory depression, death",
        "mechanism": "Combined CNS depression from opioid + benzodiazepine",
        "recommendation": "FDA black box warning — avoid concurrent use unless no alternatives",
    },
    {
        "drugs": {"simvastatin", "clarithromycin"},
        "severity": "major",
        "effect": "Increased risk of rhabdomyolysis",
        "mechanism": "CYP3A4 inhibition increases statin levels",
        "recommendation": "Suspend statin during antibiotic course or use azithromycin instead",
    },
    {
        "drugs": {"ciprofloxacin", "tizanidine"},
        "severity": "major",
        "effect": "Increased tizanidine levels — hypotension, excessive sedation",
        "mechanism": "CYP1A2 inhibition by ciprofloxacin",
        "recommendation": "Combination is contraindicated",
    },
    # ── Moderate interactions ──
    {
        "drugs": {"lisinopril", "potassium"},
        "severity": "moderate",
        "effect": "Risk of hyperkalemia",
        "mechanism": "ACE inhibitors reduce potassium excretion",
        "recommendation": "Monitor serum potassium; avoid potassium supplements unless indicated",
    },
    {
        "drugs": {"metformin", "contrast dye"},
        "severity": "moderate",
        "effect": "Risk of lactic acidosis",
        "mechanism": "Contrast may impair renal function, reducing metformin clearance",
        "recommendation": "Hold metformin 48 hours before/after IV contrast; check renal function",
    },
    {
        "drugs": {"amlodipine", "simvastatin"},
        "severity": "moderate",
        "effect": "Increased statin levels — elevated myopathy risk",
        "mechanism": "CYP3A4 interaction",
        "recommendation": "Limit simvastatin to 20mg/day with amlodipine; consider alternative statin",
    },
    {
        "drugs": {"azithromycin", "warfarin"},
        "severity": "moderate",
        "effect": "Potentially increased INR and bleeding risk",
        "mechanism": "Possible alteration of gut flora affecting vitamin K metabolism",
        "recommendation": "Monitor INR during and shortly after antibiotic course",
    },
    {
        "drugs": {"prednisone", "ibuprofen"},
        "severity": "moderate",
        "effect": "Increased GI bleeding and ulcer risk",
        "mechanism": "Additive GI mucosal damage",
        "recommendation": "Add GI prophylaxis (PPI); use combination for shortest duration possible",
    },
    {
        "drugs": {"prednisone", "naproxen"},
        "severity": "moderate",
        "effect": "Increased GI bleeding and ulcer risk",
        "mechanism": "Additive GI mucosal damage",
        "recommendation": "Add GI prophylaxis (PPI); minimize duration",
    },
    {
        "drugs": {"furosemide", "digoxin"},
        "severity": "moderate",
        "effect": "Hypokalemia-induced digoxin toxicity",
        "mechanism": "Furosemide causes potassium loss, increasing digoxin sensitivity",
        "recommendation": "Monitor potassium and digoxin levels; supplement potassium as needed",
    },
    {
        "drugs": {"sertraline", "alprazolam"},
        "severity": "moderate",
        "effect": "Increased sedation and CNS depression",
        "mechanism": "Additive CNS depressant effects",
        "recommendation": "Use lower benzodiazepine dose; monitor for excessive sedation",
    },
    {
        "drugs": {"levothyroxine", "calcium"},
        "severity": "moderate",
        "effect": "Reduced levothyroxine absorption",
        "mechanism": "Calcium binds levothyroxine in GI tract",
        "recommendation": "Separate administration by at least 4 hours",
    },
    {
        "drugs": {"levothyroxine", "omeprazole"},
        "severity": "moderate",
        "effect": "Reduced levothyroxine absorption",
        "mechanism": "PPI increases gastric pH, impairing levothyroxine dissolution",
        "recommendation": "Monitor TSH; may need levothyroxine dose increase",
    },
    {
        "drugs": {"insulin", "metformin"},
        "severity": "minor",
        "effect": "Additive hypoglycemia risk",
        "mechanism": "Combined glucose-lowering effect",
        "recommendation": "Common and appropriate combination; monitor blood glucose closely",
    },
    {
        "drugs": {"aspirin", "ibuprofen"},
        "severity": "moderate",
        "effect": "Reduced cardioprotective effect of aspirin; increased GI bleeding",
        "mechanism": "Ibuprofen competitively blocks aspirin binding to COX-1 platelets",
        "recommendation": "Take aspirin 30 min before ibuprofen or 8 hours after; consider alternative analgesic",
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_drug_name(name: str) -> str:
    """Normalise a drug name to its generic lowercase form."""
    cleaned = name.lower().strip().rstrip(".")
    # Remove common suffixes
    for suffix in (" tablets", " capsules", " oral", " injection", " cream", " mg"):
        cleaned = cleaned.replace(suffix, "")
    cleaned = cleaned.strip()
    return BRAND_TO_GENERIC.get(cleaned, cleaned)


def _extract_drug_names_from_entities(entities: Dict[str, Any]) -> Set[str]:
    """Extract normalised drug names from NER entity output."""
    medications = entities.get("medications", [])
    drugs = set()
    for med in medications:
        text = med.get("text", "")
        if text:
            drugs.add(_normalise_drug_name(text))
    return drugs


def _extract_drug_names_from_text(text: str) -> Set[str]:
    """
    Simple keyword extraction of medication names from free text.
    Supplements the NER extraction for cases where NER misses common names.
    """
    text_lower = text.lower()
    found = set()
    for name, generic in BRAND_TO_GENERIC.items():
        # Match whole words only
        if f" {name} " in f" {text_lower} " or f" {name}," in f" {text_lower}," or f" {name}." in f" {text_lower}.":
            found.add(generic)
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_interactions(
    medications: List[str],
    min_severity: str = "moderate",
) -> List[Dict[str, Any]]:
    """
    Check for drug-drug interactions among a list of medications.

    Args:
        medications: List of medication names (brand or generic)
        min_severity: Minimum severity to report ("major", "moderate", "minor")

    Returns:
        List of interaction dicts with: drugs, severity, effect, mechanism,
        recommendation, flagged_pair.
    """
    if not settings.drug_interaction_check_enabled:
        return []

    if len(medications) < 2:
        return []

    severity_order = {"major": 3, "moderate": 2, "minor": 1}
    min_level = severity_order.get(min_severity, 2)

    # Normalise all drug names
    normalised = set()
    for med in medications:
        normalised.add(_normalise_drug_name(med))

    interactions = []
    checked_pairs = set()

    for interaction in INTERACTION_DB:
        interaction_drugs = interaction["drugs"]
        severity = interaction["severity"]

        if severity_order.get(severity, 0) < min_level:
            continue

        # Check if any pair of the patient's meds matches this interaction
        matched = interaction_drugs & normalised
        if len(matched) >= 2:
            pair_key = frozenset(matched)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            interactions.append({
                "drugs": sorted(matched),
                "severity": severity,
                "effect": interaction["effect"],
                "mechanism": interaction["mechanism"],
                "recommendation": interaction["recommendation"],
            })

    # Sort by severity (major first)
    interactions.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)

    if interactions:
        logger.info(
            f"Drug interactions: found {len(interactions)} interaction(s) "
            f"among {len(normalised)} medications"
        )

    return interactions


def check_interactions_from_entities(
    entities: Dict[str, Any],
    transcript: Optional[str] = None,
    min_severity: str = "moderate",
) -> List[Dict[str, Any]]:
    """
    Check interactions using NER-extracted entities, optionally supplemented
    by keyword extraction from the transcript.

    Args:
        entities: Output from ner_service.extract_entities()
        transcript: Optional raw transcript for supplementary extraction
        min_severity: Minimum severity to report

    Returns:
        List of interaction dicts.
    """
    drugs = _extract_drug_names_from_entities(entities)

    if transcript:
        drugs |= _extract_drug_names_from_text(transcript)

    if len(drugs) < 2:
        return []

    return check_interactions(list(drugs), min_severity=min_severity)


def get_interaction_db_stats() -> Dict[str, Any]:
    """Return statistics about the drug interaction database."""
    severity_counts = {"major": 0, "moderate": 0, "minor": 0}
    unique_drugs = set()
    for interaction in INTERACTION_DB:
        severity_counts[interaction["severity"]] = severity_counts.get(interaction["severity"], 0) + 1
        unique_drugs |= interaction["drugs"]

    return {
        "enabled": settings.drug_interaction_check_enabled,
        "total_interactions": len(INTERACTION_DB),
        "by_severity": severity_counts,
        "unique_drugs_covered": len(unique_drugs),
        "brand_aliases": len(BRAND_TO_GENERIC),
    }
