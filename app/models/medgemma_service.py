"""
MedGemma Service - Medical Documentation Generation

COMPLIANCE NOTICE:
This service generates ADMINISTRATIVE DOCUMENTATION ONLY.
It does NOT provide clinical triage, urgency assessment, or medical advice.
All outputs are flagged for mandatory clinician review.
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Dict, Any
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class MedGemmaService:
    """Service for medical documentation generation using MedGemma 1.5."""
    
    def __init__(self):
        """Initialize MedGemma model and processor."""
        self.device = settings.device
        self.model = None
        self.tokenizer = None
        self._load_model()
    
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
            
            # Load model with appropriate settings
            self.model = AutoModelForCausalLM.from_pretrained(
                settings.medgemma_model,
                torch_dtype=dtype,
                device_map="auto" if settings.enable_gpu and torch.cuda.is_available() else None,
                token=settings.hf_token if settings.hf_token else None,
                low_cpu_mem_usage=True
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
        ai_output_clean = text.lower().strip()
        
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
        
        return {
            "chief_complaint": chief_complaint,
            "symptom_details": {
                "symptoms_mentioned": confirmed_symptoms if confirmed_symptoms else ["not specified"],
                "onset": onset,
                "duration": duration,
                "location": location,
                "quality": "not specified",
                "severity_description": "not specified",
                "associated_symptoms": [],  # Only add truly associated symptoms, not main complaint
                "aggravating_factors": context if context != "not specified" else "not specified",
                "alleviating_factors": "not specified"
            },
            "soap_note_subjective": soap_note,
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
    
    def generate_documentation(self, transcript: str) -> Dict[str, Any]:
        """
        Generate structured symptom documentation from transcript.
        
        COMPLIANCE: This does NOT perform triage or clinical assessment.
        It only extracts and structures information from the patient's statement.
        
        Args:
            transcript: Patient's symptom report (text)
            
        Returns:
            Dictionary with structured documentation
        """
        try:
            logger.info("Generating documentation...")
            
            # Import prompt here to avoid circular dependency
            from app.prompts.documentation_prompts import create_documentation_prompt
            
            # Create prompt content
            prompt_content = create_documentation_prompt(transcript)
            
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
            
            logger.info(f"Formatted prompt (first 200 chars): {prompt[:200]}...")
            
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
            
            logger.info(f"Raw model output (length={len(decoded)}): {decoded[:200]}...")
            
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
                    "validation_failed": True,
                    "validation_error": error_msg,
                    "requires_clinician_review": True,
                    "compliance_notice": "Validation failed. Raw transcript provided for manual review."
                }
                return fallback
            
            # Generate O, A, P sections using MedGemma
            try:
                oap_sections = self.generate_soap_sections(transcript, documentation)
                documentation.update(oap_sections)
            except Exception as oap_err:
                logger.warning(f"O/A/P generation failed, using defaults: {oap_err}")
                documentation["soap_note_objective"] = "Pending clinician assessment."
                documentation["soap_note_assessment"] = "Pending clinician assessment."
                documentation["soap_note_plan"] = "Pending clinician assessment."
            
            # Ensure compliance fields are present
            documentation["requires_clinician_review"] = True
            documentation["compliance_notice"] = (
                "This is administrative documentation only. "
                "All clinical decisions must be made by qualified healthcare professionals."
            )
            
            # Remove any urgency/severity fields if present (compliance)
            documentation.pop("urgency", None)
            documentation.pop("severity", None)
            documentation.pop("risk_level", None)
            documentation.pop("recommended_actions", None)
            
            return documentation
            
        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            raise
    
    def generate_soap_sections(self, transcript: str, subjective_data: dict) -> dict:
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
        
        prompt_content = create_soap_oap_prompt(transcript, subjective_data)
        
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
        
        logger.info(f"SOAP O/A/P raw output (length={len(decoded)}): {decoded[:200]}...")
        
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
                logger.info(f"Extracted {key}: {extracted[:80]}...")
            else:
                result[key] = defaults[key]
                logger.warning(f"Could not extract {key}, using default")
        
        return result
    
    def is_ready(self) -> bool:
        """Check if the model is loaded and ready."""
        return self.model is not None and self.tokenizer is not None


# Global instance (singleton pattern)
_medgemma_service = None


def get_medgemma_service() -> MedGemmaService:
    """Get or create MedGemma service instance."""
    global _medgemma_service
    if _medgemma_service is None:
        _medgemma_service = MedGemmaService()
    return _medgemma_service
