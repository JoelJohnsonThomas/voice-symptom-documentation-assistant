"""
MedGemma Service - Medical Documentation Generation

COMPLIANCE NOTICE:
This service generates ADMINISTRATIVE DOCUMENTATION ONLY.
It does NOT provide clinical triage, urgency assessment, or medical advice.
All outputs are flagged for mandatory clinician review.
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor
from typing import Dict, Any, Optional, List, Tuple
import json
import io
import logging

from app.config import settings
from app.compliance import build_compliance_notice, build_compliance_metadata

logger = logging.getLogger(__name__)


class MedGemmaService:
    """Service for medical documentation generation using MedGemma 1.5."""
    
    def __init__(self):
        """Initialize MedGemma model and processor."""
        self.device = settings.device
        self.model = None
        self.tokenizer = None
        self.vision_model = None
        self.vision_processor = None
        self._load_model()
        if settings.enable_image_analysis:
            self._load_vision_model()
    
    def _load_model(self):
        """Load MedGemma model from Hugging Face."""
        try:
            logger.info(f"Loading MedGemma model on device: {self.device}")
            
            # Use bfloat16 on GPU for better numerical stability (recommended for MedGemma)
            # float16 can cause empty output issues with this model
            if settings.enable_gpu and torch.cuda.is_available():
                dtype = torch.bfloat16
                logger.info("Using bfloat16 precision on GPU for numerical stability")
            else:
                # Use float32 on CPU
                dtype = torch.float32
                logger.info("Using float32 precision on CPU")
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                settings.medgemma_model,
                token=settings.hf_token if settings.hf_token else None
            )
            
            # Load model with appropriate settings (Phase 8: quantization support)
            from app.quantization import get_quantization_config
            quant_config = get_quantization_config()

            load_kwargs = {
                "torch_dtype": dtype,
                "token": settings.hf_token if settings.hf_token else None,
                "low_cpu_mem_usage": True,
            }
            if quant_config is not None:
                load_kwargs["quantization_config"] = quant_config
                load_kwargs["device_map"] = "auto"
                logger.info("Loading MedGemma with %d-bit quantization", settings.model_quantization_bits)
            elif settings.enable_gpu and torch.cuda.is_available():
                load_kwargs["device_map"] = "auto"

            self.model = AutoModelForCausalLM.from_pretrained(
                settings.medgemma_model, **load_kwargs
            )
            
            # Manual device placement if not using device_map
            if not (settings.enable_gpu and torch.cuda.is_available()):
                self.model = self.model.to("cpu")
                self.device = "cpu"
                logger.info("MedGemma running on CPU (GPU disabled or unavailable)")
            else:
                logger.info(f"MedGemma running on GPU with device_map=auto")
            
            self.model.eval()
            
            logger.info(f"MedGemma model loaded successfully on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load MedGemma model: {e}")
            raise
    
    def _load_vision_model(self):
        """Load MedGemma multimodal vision model for image analysis."""
        try:
            logger.info(f"Loading MedGemma vision model: {settings.medgemma_vision_model}")
            
            if settings.enable_gpu and torch.cuda.is_available():
                dtype = torch.bfloat16
            else:
                dtype = torch.float32
            
            self.vision_processor = AutoProcessor.from_pretrained(
                settings.medgemma_vision_model,
                token=settings.hf_token if settings.hf_token else None
            )
            
            self.vision_model = AutoModelForCausalLM.from_pretrained(
                settings.medgemma_vision_model,
                torch_dtype=dtype,
                device_map="auto" if settings.enable_gpu and torch.cuda.is_available() else None,
                token=settings.hf_token if settings.hf_token else None,
                low_cpu_mem_usage=True
            )
            
            if not (settings.enable_gpu and torch.cuda.is_available()):
                self.vision_model = self.vision_model.to("cpu")
            
            self.vision_model.eval()
            logger.info("MedGemma vision model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load vision model: {e}")
            logger.warning("Image analysis will be unavailable")
            self.vision_model = None
            self.vision_processor = None
    
    def _extract_json_from_response(self, text: str) -> str:
        """
        Extract JSON from model response, handling various formats.
        
        Args:
            text: Raw model response
            
        Returns:
            Extracted JSON string
        """
        import re
        
        # Remove prompt echo if present (common with instruction models)
        # The model often echoes the entire prompt before generating
        if "RESPOND ONLY WITH THE JSON OBJECT" in text:
            # Split after this marker and take everything after
            parts = text.split("RESPOND ONLY WITH THE JSON OBJECT")
            if len(parts) > 1:
                # Take the response part (after the prompt)
                text = parts[-1]
                logger.info(f"Removed prompt echo, remaining text length: {len(text)}")
        
        # Try to extract JSON from markdown code fence
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            logger.info("Found JSON in markdown code fence")
            return json_match.group(1).strip()
        
        # Try to find JSON object using non-greedy matching
        # Look for { followed by anything (non-greedy) followed by }
        # This should match the first complete JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            logger.info("Found JSON using non-greedy pattern matching")
            return json_match.group(0).strip()
        
        # Last resort: try greedy matching from first { to last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = text[first_brace:last_brace + 1]
            logger.info(f"Found JSON using brace positions: {first_brace} to {last_brace}")
            return json_str.strip()
        
        logger.warning("No JSON pattern found in response")
        # Return as-is if no pattern found
        return text.strip()

    def _safe_log_generated_text(self, label: str, text: str, max_chars: int = 200):
        """Log generated model text safely without exposing PHI by default."""
        if settings.allow_phi_logging:
            logger.info(f"{label} (length={len(text)}): {text[:max_chars]}...")
        else:
            logger.info(f"{label} generated (length={len(text)}). Content redacted.")

    def _calibrate_confidence_score(
        self,
        base_score: float,
        evidence_hits: int = 0,
        uncertainty_penalties: int = 0
    ) -> float:
        """
        Calibrate a confidence score into [0, 1] using simple evidence/penalty factors.
        """
        calibrated = base_score + (0.04 * min(evidence_hits, 3)) - (0.06 * uncertainty_penalties)
        return round(max(0.05, min(0.99, calibrated)), 2)

    def _build_confidence_record(self, score: float, rationale: str) -> Dict[str, Any]:
        """Build standardized confidence metadata for one extracted field."""
        if score >= 0.80:
            level = "high_confidence"
            color = "green"
            verification_text = "High confidence"
            needs_verification = False
        elif score >= 0.55:
            level = "moderate_confidence"
            color = "yellow"
            verification_text = "Needs quick verification"
            needs_verification = True
        else:
            level = "low_confidence"
            color = "red"
            verification_text = "Needs verification"
            needs_verification = True

        return {
            "score": round(score, 2),
            "level": level,
            "color": color,
            "verification_text": verification_text,
            "needs_verification": needs_verification,
            "calibration": "rule_based_v1",
            "rationale": rationale,
        }

    def _flatten_confidence_records(
        self,
        confidence_map: Dict[str, Any],
        parent: str = ""
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Flatten nested confidence map to (field_path, record) tuples."""
        flattened = []
        for key, value in confidence_map.items():
            path = f"{parent}.{key}" if parent else key
            if isinstance(value, dict) and "score" in value and "color" in value:
                flattened.append((path, value))
            elif isinstance(value, dict):
                flattened.extend(self._flatten_confidence_records(value, path))
        return flattened

    def _build_confidence_summary(self, confidence_map: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize confidence metadata across all extracted fields."""
        records = self._flatten_confidence_records(confidence_map)
        if not records:
            return {
                "overall_score": 0.0,
                "color_breakdown": {"green": 0, "yellow": 0, "red": 0},
                "high_confidence_fields": [],
                "needs_verification_fields": [],
                "calibration": "rule_based_v1",
            }

        color_breakdown = {"green": 0, "yellow": 0, "red": 0}
        for _, record in records:
            color_breakdown[record["color"]] += 1

        return {
            "overall_score": round(sum(r["score"] for _, r in records) / len(records), 2),
            "color_breakdown": color_breakdown,
            "high_confidence_fields": [path for path, record in records if record["color"] == "green"],
            "needs_verification_fields": [
                path for path, record in records if record["needs_verification"]
            ],
            "calibration": "rule_based_v1",
        }

    def _build_field_confidence(
        self,
        has_confirmed_symptoms: bool,
        used_transcript_fallback: bool,
        time_match_type: str,
        has_location: bool,
        has_context: bool,
    ) -> Dict[str, Any]:
        """Create calibrated confidence map for extracted documentation fields."""
        chief_base = 0.76 if has_confirmed_symptoms else 0.58
        chief_score = self._calibrate_confidence_score(
            chief_base,
            evidence_hits=2 if has_confirmed_symptoms else 1,
            uncertainty_penalties=1 if used_transcript_fallback else 0,
        )

        symptoms_score = self._calibrate_confidence_score(
            0.82 if has_confirmed_symptoms else 0.30,
            evidence_hits=2 if has_confirmed_symptoms else 0,
            uncertainty_penalties=0 if has_confirmed_symptoms else 1,
        )

        if time_match_type == "numeric":
            time_base, time_hits = 0.78, 2
        elif time_match_type == "relative":
            time_base, time_hits = 0.66, 1
        else:
            time_base, time_hits = 0.28, 0

        onset_score = self._calibrate_confidence_score(
            time_base,
            evidence_hits=time_hits,
            uncertainty_penalties=0 if time_match_type != "none" else 1,
        )
        duration_score = self._calibrate_confidence_score(
            time_base,
            evidence_hits=time_hits,
            uncertainty_penalties=0 if time_match_type != "none" else 1,
        )

        location_score = self._calibrate_confidence_score(
            0.74 if has_location else 0.28,
            evidence_hits=1 if has_location else 0,
            uncertainty_penalties=0 if has_location else 1,
        )

        context_score = self._calibrate_confidence_score(
            0.72 if has_context else 0.28,
            evidence_hits=1 if has_context else 0,
            uncertainty_penalties=0 if has_context else 1,
        )

        return {
            "chief_complaint": self._build_confidence_record(
                chief_score,
                "Derived from transcript symptom mapping and fallback rules."
            ),
            "symptom_details": {
                "symptoms_mentioned": self._build_confidence_record(
                    symptoms_score,
                    "Matched against transcript using rule-based symptom lexicon."
                ),
                "onset": self._build_confidence_record(
                    onset_score,
                    "Extracted from time expressions in transcript."
                ),
                "duration": self._build_confidence_record(
                    duration_score,
                    "Extracted from numeric/relative duration patterns."
                ),
                "location": self._build_confidence_record(
                    location_score,
                    "Extracted from anatomical location regex patterns."
                ),
                "quality": self._build_confidence_record(
                    self._calibrate_confidence_score(0.22, uncertainty_penalties=1),
                    "Quality descriptor is often unspecified in source transcript."
                ),
                "severity_description": self._build_confidence_record(
                    self._calibrate_confidence_score(0.22, uncertainty_penalties=1),
                    "Severity descriptor is often unspecified in source transcript."
                ),
                "associated_symptoms": self._build_confidence_record(
                    self._calibrate_confidence_score(0.24, uncertainty_penalties=1),
                    "Associated symptom links require clinician confirmation."
                ),
                "aggravating_factors": self._build_confidence_record(
                    context_score,
                    "Derived from activity/context phrases in transcript."
                ),
                "alleviating_factors": self._build_confidence_record(
                    self._calibrate_confidence_score(0.22, uncertainty_penalties=1),
                    "Alleviating factors are often not explicitly stated."
                ),
            },
            "soap_note_subjective": self._build_confidence_record(
                self._calibrate_confidence_score(
                    0.75 if has_confirmed_symptoms else 0.60,
                    evidence_hits=1 if has_confirmed_symptoms else 0,
                    uncertainty_penalties=0 if has_confirmed_symptoms else 1,
                ),
                "Generated from validated extracted symptom fields."
            ),
        }
    
    def _extract_fields_from_text(self, text: str, transcript: str) -> Dict[str, Any]:
        """
        Extract fields ONLY from original transcript with AI output as context.
        PREVENTS HALLUCINATIONS by validating against source.
        
        Args:
            text: Raw model response (may contain markdown)
            transcript: Original patient transcript
            
        Returns:
            Dictionary with extracted documentation fields
        """
        import re
        
        # Clean inputs
        transcript_clean = transcript.lower().strip()
        
        # Symptom mapping: canonical name -> variations to search for
        # CRITICAL: Ordered by specificity (longer/more specific terms first)
        symptom_map = {
            # General illness phrases (capture vague descriptions)
            'feeling sick': ['feeling sick', 'feel sick', 'feels sick', 'felt sick', 'i am sick', "i'm sick",
                            'not feeling well', "don't feel well", "doesn't feel well", 'feeling unwell',
                            'under the weather', 'coming down with something', 'got sick'],
            'feeling weak': ['feeling weak', 'feel weak', 'feeling faint', 'weak', 'malaise'],
            'not feeling right': ['not feeling right', "something's wrong", 'feel off', 'feeling off',
                                  'something wrong', 'not right', 'feel bad', 'feeling bad', 'felt bad'],
            
            # Multi-word symptoms (check first - more specific)
            'shortness of breath': ['shortness of breath', 'short of breath', 'difficulty breathing', 
                                    'hard to breathe', "can't breathe", "can't catch my breath"],
            'sore throat': ['sore throat', 'throat pain', 'throat hurts', 'scratchy throat'],
            'back pain': ['back pain', 'back hurts', 'backache', 'lower back'],
            'stomach ache': ['stomach ache', 'stomach pain', 'tummy trouble', 'abdominal pain', 
                            'belly pain', 'stomach hurts'],
            'chest pain': ['chest pain', 'chest discomfort', 'chest tightness', 'chest hurts'],
            'leg pain': ['leg pain', 'pain in leg', 'legs hurt', 'leg hurts', 'sore legs'],
            'arm pain': ['arm pain', 'pain in arm', 'arms hurt', 'arm hurts', 'sore arms'],
            'foot pain': ['foot pain', 'feet hurt', 'pain in foot', 'sore feet'],
            'eye pain': ['eye pain', 'eyes hurt', 'pain in eye', 'sore eyes'],
            'ear pain': ['ear pain', 'earache', 'ear hurts'],
            'joint pain': ['joint pain', 'joints hurt', 'arthritis', 'joint ache'],
            'body aches': ['body aches', 'achy all over', 'everything hurts', 'muscle aches'],
            'muscle weakness': ['muscle weakness', 'weak muscles', 'muscles feel weak'],
            'vision problems': ['blurry vision', 'vision blurry', 'blurry', "can't see", 'blurred vision', 'blurred'],
            
            # Single-word primary symptoms
            'headache': ['headache', 'head pain', 'migraine', 'my head hurts', 'head hurts'],
            'nausea': ['nausea', 'sick to stomach', 'queasy', 'nauseated', 'sick to my stomach'],
            'vomiting': ['vomiting', 'vomit', 'throwing up', 'threw up'],
            'fever': ['fever', 'temperature', 'febrile', 'running a fever'],
            'chills': ['chills', 'chilly', 'shivering'],
            'cold': ['cold', 'common cold', 'caught a cold', 'have a cold', 'got a cold'],
            'runny nose': ['runny nose', 'nose running', 'running nose', 'sneezing', 'sniffles'],
            'cough': ['cough', 'coughing'],
            'dizziness': ['dizzy', 'dizziness', 'lightheaded', 'light headed', 'room spinning'],
            'fatigue': ['fatigue', 'tired', 'exhausted', 'no energy', 'feeling weak'],
            'rash': ['rash', 'skin rash', 'itchy rash', 'hives'],
            'congestion': ['congestion', 'congested', 'stuffy nose', 'blocked nose'],
            'diarrhea': ['diarrhea', 'loose stools', 'watery stools'],
            'numbness': ['numbness', 'numb', 'tingling', 'pins and needles'],
            'fainting': ['fainting', 'passed out', 'fainted', 'blacked out', 'fainting spells'],
            'itching': ['itching', 'itchy', 'scratching'],
            'swelling': ['swelling', 'swollen', 'puffy'],
            'bleeding': ['bleeding', 'blood', 'coughing blood'],
            'pain': ['pain', 'painful', 'hurts', 'hurting', 'sore', 'ache'],
        }
        
        # CRITICAL: Extract symptoms from TRANSCRIPT ONLY using word boundaries
        confirmed_symptoms = []
        for symptom, variations in symptom_map.items():
            for variation in variations:
                # Use word boundaries to prevent substring matches
                # This prevents "ache" from matching within "headache"
                if re.search(rf'\b{re.escape(variation)}\b', transcript_clean):
                    confirmed_symptoms.append(symptom)
                    break  # Found this symptom, move to next
        
        # Remove generic 'pain' if a more specific pain type is present
        specific_pain_types = ['back pain', 'chest pain', 'ear pain', 'joint pain', 'stomach ache', 
                               'headache', 'sore throat']
        if 'pain' in confirmed_symptoms:
            for specific in specific_pain_types:
                if specific in confirmed_symptoms:
                    confirmed_symptoms.remove('pain')
                    break
        
        # Build chief complaint from confirmed symptoms
        # FALLBACK: If no symptoms detected, use the cleaned transcript (patient's own words)
        if confirmed_symptoms:
            chief_complaint = ", ".join(confirmed_symptoms[:3])
        else:
            # Use original transcript as chief complaint if it's short enough
            if len(transcript.strip()) <= 100:
                chief_complaint = transcript.strip().capitalize()
            else:
                chief_complaint = transcript.strip()[:100].capitalize() + "..."
        
        # Word-to-number mapping for duration parsing
        # Only convert unambiguous number words, keep "few/several/couple" as-is
        word_to_num = {
            'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
            'a': '1', 'an': '1'
        }
        
        # Convert spelled-out numbers in transcript for duration matching
        transcript_for_time = transcript_clean
        for word, num in word_to_num.items():
            transcript_for_time = re.sub(rf'\b{word}\b', num, transcript_for_time)
        
        # Extract timing information from TRANSCRIPT (not AI output)
        duration = "not specified"
        onset = "not specified"
        time_match_type = "none"
        
        # Enhanced time patterns (now work with converted numbers)
        time_patterns = [
            (r'for\s+(?:the\s+)?past\s+(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)', 'duration'),
            (r'for\s+(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)', 'duration'),  # Simple "for 20 minutes"
            (r'(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)\s+ago', 'onset'),
            (r'since\s+(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)', 'duration'),
            (r'past\s+(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)', 'duration'),
            (r'last\s+(\d+)\s*(minute|minutes|day|days|hour|hours|week|weeks|month|months)', 'duration'),
            # Standalone duration without "for"
            (r'(\d+)\s*(minute|minutes|month|months|year|years|week|weeks)', 'duration'),
        ]
        
        # Relative time patterns (yesterday, this morning, meals, etc.)
        relative_patterns = [
            # Yesterday variants
            (r'since\s+(yesterday\s*(?:morning|afternoon|evening|night)?)', 'since yesterday'),
            (r'started\s+(yesterday)', 'since yesterday'),
            # Today/morning variants
            (r'since\s+(this\s+morning)', 'since this morning'),
            (r'since\s+(morning)', 'since morning'),  # without "this"
            (r'started\s+(this\s+morning)', 'since this morning'),
            (r'(this\s+morning)', 'this morning'),  # standalone
            # Time of day variants (without "this")
            (r'since\s+(evening|afternoon|tonight|today)', 'since today'),
            # Night variants
            (r'since\s+(last\s+night)', 'since last night'),
            (r'started\s+(last\s+night)', 'since last night'),
            (r'since\s+(night)', 'since last night'),  # assume last night
            # Meal-based timing - preserve actual word
            (r'since\s+(breakfast|lunch|dinner|noon)', 'since CAPTURED'),
            # Duration without numbers (preserve literal)
            (r'for\s+(months|years|weeks)', 'chronic'),
            (r'for\s+((?:several|few|couple)\s+(?:days|weeks|hours|months))', 'duration'),
            (r'(all\s+day|all\s+night)', 'all day'),
        ]
        
        # Contextual patterns (when walking, when standing, etc.)
        context_patterns = [
            r'when\s+(walking|standing|sitting|lying\s+down|exercising|climbing\s+stairs)',
            r'(at\s+rest)',
            r'(radiating\s+to\s+\w+)',
        ]
        
        # Try numeric patterns first
        for pattern, match_type in time_patterns:
            match = re.search(pattern, transcript_for_time)
            if match:
                num_val = match.group(1)
                unit = match.group(2)
                # Ensure proper plural form
                if int(num_val) != 1 and not unit.endswith('s'):
                    unit += 's'
                elif int(num_val) == 1 and unit.endswith('s'):
                    unit = unit[:-1]  # Remove trailing 's' for singular
                duration = f"{num_val} {unit}"
                onset = f"{duration} ago"
                time_match_type = "numeric"
                break
        
        # If no numeric match, try relative patterns
        if duration == "not specified":
            for pattern, onset_value in relative_patterns:
                match = re.search(pattern, transcript_clean)
                if match:
                    captured_value = match.group(1)
                    # Handle CAPTURED placeholder for meal-based timing
                    if onset_value == 'since CAPTURED':
                        onset = f"since {captured_value}"
                    else:
                        onset = onset_value
                    duration = captured_value
                    time_match_type = "relative"
                    break
        
        # Build SOAP note from VALIDATED information only - more narrative style
        soap_parts = []
        if confirmed_symptoms:
            soap_parts.append(f"Patient reports {chief_complaint}")
        else:
            soap_parts.append("Patient describes symptoms")
        
        if duration != "not specified":
            # Handle different onset types for natural phrasing
            if onset == "chronic":
                soap_parts.append(f"present for {duration}")
            elif onset == "all day":
                soap_parts.append("present all day")
            elif onset.startswith("since"):
                soap_parts.append(f"{onset}")
            else:
                soap_parts.append(f"with onset {onset}")
        
        # Extract context (when walking, radiating to, etc.)
        context = "not specified"
        for pattern in context_patterns:
            match = re.search(pattern, transcript_clean)
            if match:
                context = match.group(1) if match.lastindex else match.group(0)
                # Add proper phrasing for context in SOAP note
                if context.startswith("at ") or context.startswith("radiating"):
                    soap_parts.append(context)
                else:
                    soap_parts.append(f"when {context}")
                break
        
        # Extract location if mentioned
        location = "not specified"
        location_patterns = [
            r'in\s+(?:my\s+)?(knees|knee|legs|leg|arms|arm|back|chest|head|stomach|neck|shoulders|shoulder|hips|hip)',
            r'on\s+(?:my\s+)?(arms|arm|legs|leg|face|back|chest|hands|hand|feet|foot)',
            r'(left|right)\s+(arm|leg|side|eye|ear)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, transcript_clean)
            if match:
                location = match.group(0).replace('my ', '')
                # Add location to SOAP note
                soap_parts.append(location)
                break
        
        soap_note = ", ".join(soap_parts) + "."
        soap_note = soap_note[0].upper() + soap_note[1:]  # Capitalize first letter

        symptom_details = {
            "symptoms_mentioned": confirmed_symptoms if confirmed_symptoms else ["not specified"],
            "onset": onset,
            "duration": duration,
            "location": location,
            "quality": "not specified",
            "severity_description": "not specified",
            "associated_symptoms": [],  # Only add truly associated symptoms, not main complaint
            "aggravating_factors": context if context != "not specified" else "not specified",
            "alleviating_factors": "not specified"
        }

        field_confidence = self._build_field_confidence(
            has_confirmed_symptoms=bool(confirmed_symptoms),
            used_transcript_fallback=not bool(confirmed_symptoms),
            time_match_type=time_match_type,
            has_location=location != "not specified",
            has_context=context != "not specified",
        )
        confidence_summary = self._build_confidence_summary(field_confidence)
        
        return {
            "chief_complaint": chief_complaint,
            "symptom_details": symptom_details,
            "soap_note_subjective": soap_note,
            "field_confidence": field_confidence,
            "confidence_summary": confidence_summary,
            "parsing_method": "transcript_validated",
            "ai_output_used": False  # We are NOT using AI output for symptom extraction
        }
    
    def _validate_output(self, documentation: Dict, original_transcript: str) -> tuple[bool, str]:
        """
        Validate documentation output before returning.
        Returns: (is_valid, error_message)
        """
        # Check 1: Chief complaint not empty placeholder
        cc = documentation.get("chief_complaint", "")
        if not cc or cc == "not specified":
            return False, "Failed to extract chief complaint"
        
        # Check 2: SOAP note not truncated or malformed
        soap = documentation.get("soap_note_subjective", "")
        if len(soap) < 10:
            return False, "SOAP note too short"
        if any(marker in soap for marker in ["...", "1.**", "2.**", "Here's the"]):
            return False, "SOAP note contains artifacts or truncation markers"
        
        # Check 3: Symptoms were extracted from transcript (validation already done during extraction)
        # Since we use transcript-only extraction with word boundaries, 
        # symptoms are guaranteed to come from the transcript.
        # Skip re-validation that would fail on synonym mappings (e.g., "chest discomfort" -> "chest pain")
        
        return True, ""
    
    def generate_followup_questions(self, transcript: str, detected_language: str = "en") -> List[str]:
        """
        Generate 2-3 targeted follow-up questions for missing clinical information.

        Returns:
            List of patient-friendly question strings (2-3 items).
            Falls back to generic questions if the model fails.
        """
        from app.prompts.documentation_prompts import create_followup_questions_prompt

        try:
            prompt_content = create_followup_questions_prompt(transcript, language=detected_language)
            messages = [{"role": "user", "content": prompt_content}]
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            inputs = self.tokenizer(prompt, return_tensors="pt", padding=True).to(self.model.device)

            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    repetition_penalty=settings.medgemma_repetition_penalty,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

            generated_ids = outputs[0][inputs.input_ids.shape[1]:]
            decoded = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
            self._safe_log_generated_text("Follow-up questions response", decoded)

            json_str = self._extract_json_from_response(decoded)
            data = json.loads(json_str)
            questions = data.get("questions", [])
            if isinstance(questions, list) and 2 <= len(questions) <= 3:
                return [str(q) for q in questions]

            # If the list is longer than 3, trim; if shorter, fall through to fallback
            if isinstance(questions, list) and len(questions) > 3:
                return [str(q) for q in questions[:3]]

        except Exception as e:
            logger.warning(f"Follow-up question generation failed, using fallback: {e}")

        return self._symptom_aware_fallback_questions(transcript)

    def _symptom_aware_fallback_questions(self, transcript: str) -> List[str]:
        """
        Return clinically relevant follow-up questions derived from symptom keywords
        in the transcript.  Mirrors real triage nurse prioritisation:
        demographics → red-flag associated symptoms → severity/progression → history.
        """
        t = transcript.lower()

        def has(*words: str) -> bool:
            return any(w in t for w in words)

        if has("fever", "temperature", "febrile", "hot", "running a temperature"):
            return [
                "How old are you, and have you measured your temperature? If so, what was it?",
                "Do you have any other symptoms such as a stiff neck, rash, difficulty breathing, or sensitivity to light?",
                "Have you taken anything for the fever (like paracetamol or ibuprofen), and did it help?",
            ]

        if has("chest pain", "chest discomfort", "chest tightness", "chest hurts", "chest pressure"):
            return [
                "Does the pain spread to your arm, jaw, shoulder, or back?",
                "Are you also experiencing shortness of breath, sweating, or nausea?",
                "Do you have a history of heart disease, high blood pressure, or diabetes?",
            ]

        if has("headache", "head pain", "migraine", "head hurts", "my head"):
            return [
                "Did the headache come on very suddenly (like a thunderclap), or did it build up gradually?",
                "Are you also experiencing fever, stiff neck, sensitivity to light, or any vision changes?",
                "On a scale of 1 to 10, how bad is the headache — and is it the worst headache you have ever had?",
            ]

        if has("shortness of breath", "short of breath", "difficulty breathing",
               "hard to breathe", "can't breathe", "breathless"):
            return [
                "How old are you, and did this come on suddenly or has it been getting gradually worse?",
                "Are you also experiencing chest pain, wheezing, or swelling in your legs or ankles?",
                "Do you have a history of asthma, COPD, heart problems, or any recent illness?",
            ]

        if has("stomach", "abdominal", "belly", "tummy", "nausea", "vomit", "diarrhea", "bowel"):
            return [
                "Where exactly is the pain — upper abdomen, lower abdomen, or all over — and does it move anywhere?",
                "Have you had any vomiting, diarrhoea, or noticed any blood in your stool or vomit?",
                "For women: when was your last menstrual period, and is there any chance you could be pregnant?",
            ]

        if has("dizzy", "dizziness", "lightheaded", "light-headed", "faint", "passed out", "blacked out"):
            return [
                "How old are you, and did you actually lose consciousness, or did you just feel like you might faint?",
                "Were you standing up when it started, and do you have a history of heart problems or low blood pressure?",
                "Are you also experiencing palpitations, chest pain, or shortness of breath?",
            ]

        if has("back pain", "back hurts", "backache", "lower back", "upper back"):
            return [
                "Does the pain travel down your leg, and if so, do you have any numbness or tingling in the leg or foot?",
                "Did the pain start after an injury or heavy lifting, or did it come on by itself?",
                "Are you having any difficulty with bladder or bowel control?",
            ]

        if has("rash", "hives", "itchy skin", "skin rash"):
            return [
                "Where on your body is the rash, and when did it first appear?",
                "Have you recently started any new medications, eaten anything unusual, or been exposed to new products or environments?",
                "Are you also experiencing difficulty breathing, or any swelling of your face, lips, or throat?",
            ]

        if has("cough", "coughing"):
            return [
                "How old are you, and is the cough dry or are you bringing up mucus? If mucus, what colour is it?",
                "Are you also experiencing fever, shortness of breath, or chest pain when you cough?",
                "Have you been around anyone who is sick, or have you recently travelled anywhere?",
            ]

        if has("pain", "ache", "hurts", "sore", "discomfort"):
            return [
                "How old are you, and on a scale of 1 to 10, how would you rate the pain right now?",
                "Is the pain constant or does it come and go — and does anything make it better or worse?",
                "Do you have any relevant medical history or are you taking any medications for this?",
            ]

        if has("swelling", "swollen", "swelled", "puffed", "puffy"):
            return [
                "Where exactly is the swelling, and when did you first notice it?",
                "Did the swelling start after an injury, or did it come on by itself?",
                "Is the swollen area red, warm, or painful to the touch?",
            ]

        if has("burn", "burning", "urination", "urine", "pee", "peeing", "uti"):
            return [
                "How often are you needing to urinate, and do you feel an urgent need to go?",
                "Have you noticed any blood in your urine, or does it look cloudy or smell unusual?",
                "Do you have any fever, lower back pain, or chills along with this?",
            ]

        if has("tired", "fatigue", "exhausted", "weak", "no energy", "low energy", "sleepy"):
            return [
                "How long have you been feeling this way, and did it start suddenly or gradually?",
                "Have you noticed any changes in your weight, appetite, or sleep patterns recently?",
                "Are you also experiencing any shortness of breath, dizziness, or unusually heavy periods?",
            ]

        if has("anxiety", "anxious", "panic", "stressed", "nervous", "worry", "worried"):
            return [
                "How long have you been feeling this way, and can you describe what the anxiety feels like for you?",
                "Have you experienced any heart racing, difficulty breathing, or trouble sleeping?",
                "Is there anything specific that triggers these feelings, or do they seem to come on without a clear reason?",
            ]

        if has("eye", "vision", "blurry", "blind", "seeing"):
            return [
                "Is the problem in one eye or both, and when did it start?",
                "Are you also experiencing any eye pain, redness, discharge, or sensitivity to light?",
                "Have you had any recent injury to your eye or face, or do you wear contact lenses?",
            ]

        if has("ear", "hearing", "deaf", "earache", "ear pain", "ringing"):
            return [
                "Is the problem in one ear or both, and when did it first start?",
                "Do you have any discharge from the ear, fever, or dizziness along with this?",
                "Have you been swimming recently, had a cold, or been exposed to very loud noise?",
            ]

        if has("throat", "sore throat", "swallow", "tonsil", "hoarse", "voice"):
            return [
                "How long have you had the sore throat, and is it getting worse or staying the same?",
                "Do you also have a fever, swollen glands in your neck, or a rash anywhere on your body?",
                "Are you having any difficulty swallowing liquids, or does it feel like something is stuck in your throat?",
            ]

        if has("joint", "knee", "elbow", "wrist", "ankle", "hip", "shoulder", "arthritis"):
            return [
                "Which joint is affected, and did this start after an injury or come on by itself?",
                "Is the joint swollen, red, or warm to the touch?",
                "Does the stiffness or pain change throughout the day — for example, is it worse in the morning?",
            ]

        if has("bleed", "bleeding", "blood", "cut", "wound"):
            return [
                "Where is the bleeding coming from, and how long has it been going on?",
                "Are you taking any blood-thinning medications such as aspirin or warfarin?",
                "How much blood have you lost — for example, are you soaking through bandages or pads?",
            ]

        if has("numb", "numbness", "tingling", "pins and needles"):
            return [
                "Where exactly are you feeling the numbness or tingling, and when did it start?",
                "Is it constant or does it come and go — and is it on one side of your body or both?",
                "Do you have any weakness in the affected area, or any difficulty with speech or balance?",
            ]

        if has("skin", "itch", "bump", "lump", "mole", "spot", "lesion"):
            return [
                "Where on your body is it, and when did you first notice it?",
                "Has it changed in size, shape, or colour since you first noticed it?",
                "Is it painful, itchy, or bleeding — and do you have any similar spots elsewhere?",
            ]

        if has("sleep", "insomnia", "can't sleep", "waking up", "snoring"):
            return [
                "How long have you been having trouble sleeping, and what specifically happens — difficulty falling asleep, staying asleep, or waking too early?",
                "Do you snore, gasp, or stop breathing during sleep (has anyone told you)?",
                "Are you consuming caffeine, alcohol, or using screens close to bedtime?",
            ]

        # Transcript-aware generic fallback — reference what the patient said
        # Extract first few words of the transcript for context
        words = transcript.strip().split()
        symptom_summary = " ".join(words[:12]) + ("..." if len(words) > 12 else "")
        return [
            f"You mentioned \"{symptom_summary}\" — how long have you been experiencing this, and is it getting better, worse, or staying the same?",
            "On a scale of 1 to 10, how would you rate the severity of your symptoms right now?",
            "Do you have any other medical conditions, allergies, or medications you are currently taking?",
        ]

    def generate_documentation(self, transcript: str, image_findings: Optional[str] = None, detected_language: str = "en", similar_cases: Optional[List[Dict[str, Any]]] = None, followup_qa: Optional[List[Dict[str, str]]] = None, clinical_guidelines: Optional[List[Dict[str, Any]]] = None, drug_interactions: Optional[List[Dict[str, Any]]] = None, icd10_suggestions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generate structured symptom documentation from transcript.
        
        COMPLIANCE: This does NOT perform triage or clinical assessment.
        It only extracts and structures information from the patient's statement.
        
        Args:
            transcript: Patient's symptom report (text)
            image_findings: Optional description from image analysis
            
        Returns:
            Dictionary with structured documentation
        """
        try:
            logger.info("Generating documentation...")
            
            # Import prompt here to avoid circular dependency
            from app.prompts.documentation_prompts import (
                create_documentation_prompt,
                create_documentation_with_image_prompt
            )
            
            # Create prompt content — use image-aware prompt if image findings available
            if image_findings:
                logger.info("Including image findings in documentation prompt")
                prompt_content = create_documentation_with_image_prompt(transcript, image_findings, language=detected_language, followup_qa=followup_qa)
            else:
                prompt_content = create_documentation_prompt(transcript, language=detected_language, followup_qa=followup_qa)
            
            # MedGemma 1.5 is a chat model - use chat template
            messages = [
                {"role": "user", "content": prompt_content}
            ]
            
            # Apply chat template
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            
            self._safe_log_generated_text("MedGemma prompt", prompt)
            
            # Tokenize input
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True
            ).to(self.model.device)
            
            # Generate with greedy decoding (stable on GPU with bfloat16)
            # We use conversational output and extract data via text parsing
            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=512,  # Increased to avoid truncation
                    do_sample=False,  # Greedy is stable
                    repetition_penalty=settings.medgemma_repetition_penalty,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode output (skip the input prompt)
            generated_ids = outputs[0][inputs.input_ids.shape[1]:]
            decoded = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
            
            self._safe_log_generated_text("MedGemma response", decoded)
            
            # Extract documentation from conversational text
            documentation = self._extract_fields_from_text(decoded, transcript)
            
            # CRITICAL: Validate output before returning
            is_valid, error_msg = self._validate_output(documentation, transcript)
            if not is_valid:
                logger.warning(f"Documentation validation failed: {error_msg}")
                # Return safe fallback - just the transcript
                fallback = {
                    "chief_complaint": "not specified",
                    "symptom_details": {"symptoms_mentioned": ["not specified"]},
                    "soap_note_subjective": f"Patient statement: {transcript}",
                    "soap_note_objective": "Pending clinician assessment.",
                    "soap_note_assessment": "Pending clinician assessment.",
                    "soap_note_plan": "Pending clinician assessment.",
                    "field_confidence": {
                        "chief_complaint": self._build_confidence_record(0.25, "Validation failed fallback."),
                        "symptom_details": {
                            "symptoms_mentioned": self._build_confidence_record(0.25, "Validation failed fallback."),
                        },
                        "soap_note_subjective": self._build_confidence_record(0.30, "Validation failed fallback."),
                    },
                    "confidence_summary": {
                        "overall_score": 0.27,
                        "color_breakdown": {"green": 0, "yellow": 0, "red": 3},
                        "high_confidence_fields": [],
                        "needs_verification_fields": [
                            "chief_complaint",
                            "symptom_details.symptoms_mentioned",
                            "soap_note_subjective",
                        ],
                        "calibration": "rule_based_v1",
                    },
                    "validation_failed": True,
                    "validation_error": error_msg,
                    "requires_clinician_review": True,
                    "compliance_notice": build_compliance_notice(),
                    "compliance_metadata": build_compliance_metadata(),
                }
                return fallback
            
            # Generate O, A, P sections using MedGemma
            try:
                oap_sections = self.generate_soap_sections(transcript, documentation, detected_language=detected_language, similar_cases=similar_cases, clinical_guidelines=clinical_guidelines, drug_interactions=drug_interactions, icd10_suggestions=icd10_suggestions)
                documentation.update(oap_sections)
            except Exception as oap_err:
                logger.warning(f"O/A/P generation failed, using defaults: {oap_err}")
                documentation["soap_note_objective"] = "Pending clinician assessment."
                documentation["soap_note_assessment"] = "Pending clinician assessment."
                documentation["soap_note_plan"] = "Pending clinician assessment."
            
            # Ensure compliance fields are present
            documentation["requires_clinician_review"] = True
            documentation["compliance_notice"] = build_compliance_notice()
            documentation["compliance_metadata"] = build_compliance_metadata()
            
            # Remove any urgency/severity fields if present (compliance)
            documentation.pop("urgency", None)
            documentation.pop("severity", None)
            documentation.pop("risk_level", None)
            documentation.pop("recommended_actions", None)
            
            return documentation
            
        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            raise
    
    def generate_soap_sections(self, transcript: str, subjective_data: dict, detected_language: str = "en", similar_cases: Optional[List[Dict[str, Any]]] = None, clinical_guidelines: Optional[List[Dict[str, Any]]] = None, drug_interactions: Optional[List[Dict[str, Any]]] = None, icd10_suggestions: Optional[List[Dict[str, Any]]] = None) -> dict:
        """
        Generate Objective, Assessment, and Plan SOAP sections.
        
        Uses already-validated Subjective data as context to generate
        the remaining three SOAP sections via MedGemma.
        
        Args:
            transcript: Original patient statement
            subjective_data: Dict with chief_complaint, symptom_details, etc.
            
        Returns:
            Dict with soap_note_objective, soap_note_assessment, soap_note_plan
        """
        import re
        
        from app.prompts.documentation_prompts import create_soap_oap_prompt
        
        prompt_content = create_soap_oap_prompt(transcript, subjective_data, language=detected_language, similar_cases=similar_cases, clinical_guidelines=clinical_guidelines, drug_interactions=drug_interactions, icd10_suggestions=icd10_suggestions)
        
        # Use chat template
        messages = [{"role": "user", "content": prompt_content}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        inputs = self.tokenizer(
            prompt, return_tensors="pt", padding=True
        ).to(self.model.device)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                repetition_penalty=settings.medgemma_repetition_penalty,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        generated_ids = outputs[0][inputs.input_ids.shape[1]:]
        decoded = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        
        self._safe_log_generated_text("MedGemma OAP response", decoded)
        
        # Parse the three sections from model output
        result = self._parse_soap_sections(decoded)
        
        return result
    
    def _parse_soap_sections(self, text: str) -> dict:
        """
        Parse Objective, Assessment, and Plan sections from model output.
        
        Looks for section headers (OBJECTIVE:, ASSESSMENT:, PLAN:) and
        extracts the text following each header.
        
        Args:
            text: Raw model output text
            
        Returns:
            Dict with soap_note_objective, soap_note_assessment, soap_note_plan
        """
        import re
        
        defaults = {
            "soap_note_objective": "Pending clinician assessment.",
            "soap_note_assessment": "Pending clinician assessment.",
            "soap_note_plan": "Pending clinician assessment."
        }
        
        if not text or len(text.strip()) < 10:
            logger.warning("SOAP O/A/P output too short, using defaults")
            return defaults
        
        # Try to extract each section using header patterns
        section_map = {
            "soap_note_objective": [r'OBJECTIVE:\s*(.+?)(?=ASSESSMENT:|$)',
                                    r'O:\s*(.+?)(?=A:|ASSESSMENT:|$)'],
            "soap_note_assessment": [r'ASSESSMENT:\s*(.+?)(?=PLAN:|$)',
                                     r'A:\s*(.+?)(?=P:|PLAN:|$)'],
            "soap_note_plan": [r'PLAN:\s*(.+?)$',
                               r'P:\s*(.+?)$']
        }
        
        result = {}
        for key, patterns in section_map.items():
            extracted = None
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    # Clean up any trailing whitespace or artifacts
                    extracted = re.sub(r'\s+', ' ', extracted).strip()
                    if len(extracted) > 10:  # Minimum viable content
                        break
                    else:
                        extracted = None
            
            if extracted:
                result[key] = extracted
                self._safe_log_generated_text(f"Parsed {key}", extracted, max_chars=80)
            else:
                result[key] = defaults[key]
                logger.warning(f"Could not extract {key}, using default")
        
        return result
    
    def is_ready(self) -> bool:
        """Check if the model is loaded and ready."""
        return self.model is not None and self.tokenizer is not None
    
    def is_vision_ready(self) -> bool:
        """Check if the vision model is loaded and ready."""
        return self.vision_model is not None and self.vision_processor is not None
    
    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze an uploaded medical image using MedGemma vision model.
        
        COMPLIANCE: Provides DESCRIPTIVE OBSERVATIONS ONLY.
        Does NOT diagnose or recommend treatments.
        
        Args:
            image_bytes: Raw image file bytes
            
        Returns:
            Dictionary with image analysis results
        """
        from PIL import Image
        from app.prompts.documentation_prompts import create_image_analysis_prompt
        
        if not self.is_vision_ready():
            raise RuntimeError("Vision model not loaded. Image analysis unavailable.")
        
        try:
            logger.info("Analyzing uploaded image...")
            
            # Open image from bytes
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            logger.info(f"Image opened: {image.size[0]}x{image.size[1]}")
            
            # Create analysis prompt
            prompt_text = create_image_analysis_prompt()
            
            # Build multimodal message for the vision model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt_text}
                    ]
                }
            ]
            
            # Process with AutoProcessor (handles both text + image)
            inputs = self.vision_processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt"
            ).to(self.vision_model.device)
            
            # Generate description
            with torch.inference_mode():
                outputs = self.vision_model.generate(
                    **inputs,
                    max_new_tokens=512,
                    do_sample=False,
                    repetition_penalty=settings.medgemma_repetition_penalty,
                )
            
            # Decode only the generated tokens (skip input)
            input_len = inputs["input_ids"].shape[1]
            generated_ids = outputs[0][input_len:]
            description = self.vision_processor.decode(generated_ids, skip_special_tokens=True)
            
            self._safe_log_generated_text("MedGemma image analysis", description)
            
            # Parse structured sections from the description
            import re
            body_area = "not specified"
            observations = "not specified"
            notable_features = "not specified"
            
            body_match = re.search(r'BODY\s*AREA:\s*(.+?)(?=OBSERVATIONS:|$)', description, re.DOTALL | re.IGNORECASE)
            if body_match:
                body_area = body_match.group(1).strip()
            
            obs_match = re.search(r'OBSERVATIONS:\s*(.+?)(?=NOTABLE\s*FEATURES:|$)', description, re.DOTALL | re.IGNORECASE)
            if obs_match:
                observations = obs_match.group(1).strip()
            
            feat_match = re.search(r'NOTABLE\s*FEATURES:\s*(.+?)$', description, re.DOTALL | re.IGNORECASE)
            if feat_match:
                notable_features = feat_match.group(1).strip()
            
            return {
                "description": description,
                "body_area": body_area,
                "observations": observations,
                "notable_features": notable_features,
                "visual_findings_text": description,
                "requires_clinician_review": True,
                "compliance_notice": build_compliance_notice(),
                "compliance_metadata": build_compliance_metadata(),
            }
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            raise


# Global instance (singleton pattern)
_medgemma_service = None


def get_medgemma_service() -> MedGemmaService:
    """Get or create MedGemma service instance."""
    global _medgemma_service
    if _medgemma_service is None:
        _medgemma_service = MedGemmaService()
    return _medgemma_service
