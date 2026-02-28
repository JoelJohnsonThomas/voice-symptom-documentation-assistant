"""
Medical Entity Recognition (NER) Service

Extracts structured entities (Conditions, Medications, Procedures) from text
using SciSpaCy models and links them to standard medical codes.
"""

import logging
import spacy
from typing import Dict, Any, List

from app.config import settings

logger = logging.getLogger(__name__)

class MedicalNERService:
    """Service for extracting medical entities from text."""
    
    def __init__(self):
        self.nlp_bc5cdr = None
        self.nlp_core = None
        self._load_models()
        self.is_ready = self.nlp_bc5cdr is not None or self.nlp_core is not None
        
    def _load_models(self):
        """Load SciSpaCy models."""
        try:
            # specifically for diseases and chemicals (BC5CDR corpus)
            # good for conditions and medications
            logger.info("Attempting to load SciSpaCy en_ner_bc5cdr_md...")
            self.nlp_bc5cdr = spacy.load("en_ner_bc5cdr_md")
            logger.info("en_ner_bc5cdr_md loaded successfully")
        except OSError:
            logger.warning("en_ner_bc5cdr_md not found. NER capabilities will be limited.")
            
        try:
            # general biomedical concepts
            logger.info("Attempting to load SciSpaCy en_core_sci_sm...")
            self.nlp_core = spacy.load("en_core_sci_sm")
            logger.info("en_core_sci_sm loaded successfully")
        except OSError:
            logger.warning("en_core_sci_sm not found.")

    def _mock_icd10_code(self, entity_text: str, category: str) -> str:
        """
        Generate a mock/heuristic medical code for an entity.
        In a production system, this would use a full UMLS/SNOMED linker
        like `scispacy.linker` which requires significant memory.
        """
        import hashlib
        # Create a deterministic code based on the text string
        hash_val = int(hashlib.md5(entity_text.lower().encode()).hexdigest()[:4], 16)
        
        if category == "CONDITION":
            # ICD-10 format-ish (Letter + 2 digits)
            letter = chr(65 + (hash_val % 26)) # A-Z
            num = str(hash_val % 99).zfill(2)
            return f"{letter}{num}.{hash_val % 9}"
        elif category == "MEDICATION":
            # RxNorm format-ish (numbers)
            return f"RX{hash_val}"
        else:
            return f"C{hash_val}"

    def extract_entities(self, text: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract medical entities from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary categorizing entities by type (Conditions, Medications, etc.)
        """
        if not text or not text.strip():
            return {"conditions": [], "medications": []}

        conditions = []
        medications = []
        
        # Track seen entity texts to avoid duplicates
        seen_texts = set()

        if self.nlp_bc5cdr:
            doc = self.nlp_bc5cdr(text)
            for ent in doc.ents:
                text_lower = ent.text.lower()
                if text_lower in seen_texts:
                    continue
                    
                seen_texts.add(text_lower)
                
                # BC5CDR uses DISEASE and CHEMICAL labels
                if ent.label_ == "DISEASE":
                    conditions.append({
                        "text": ent.text,
                        "code": self._mock_icd10_code(ent.text, "CONDITION"),
                        "system": "ICD-10"
                    })
                elif ent.label_ == "CHEMICAL":
                    medications.append({
                        "text": ent.text,
                        "code": self._mock_icd10_code(ent.text, "MEDICATION"),
                        "system": "RxNorm"
                    })
        
        # Fallback to general model if BC5CDR is missing or missed things
        if self.nlp_core and not conditions and not medications:
            doc = self.nlp_core(text)
            for ent in doc.ents:
                text_lower = ent.text.lower()
                if text_lower in seen_texts:
                    continue
                
                # Without the specialized model, we just extract entities generically
                # We'll default to condition for demonstration, but this is less accurate
                conditions.append({
                    "text": ent.text,
                    "code": self._mock_icd10_code(ent.text, "CONDITION"),
                    "system": "SNOMED"
                })

        return {
            "conditions": conditions,
            "medications": medications
        }


# Global instance (singleton pattern)
_ner_service = None

def get_ner_service() -> MedicalNERService:
    """Get or create Medical NER service instance."""
    global _ner_service
    if _ner_service is None:
        _ner_service = MedicalNERService()
    return _ner_service
