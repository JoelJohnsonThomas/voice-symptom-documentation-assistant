"""
MedGemma Remote Inference Service

Routes generation through Hugging Face Inference Providers instead of loading
the model in-process. Intended for free-tier / CPU-only deployments (e.g.
Hugging Face Spaces free CPU, Render, Vercel-edge backends) where the 4b
model would not fit in RAM or would be too slow to be usable.

Inherits parsing, validation, and confidence-calibration helpers from
MedGemmaService — only the model-call sites are overridden.

Limitations vs. local mode:
  - No log-probability confidence (HF Inference does not expose token logprobs
    uniformly across providers).
  - Image analysis is disabled (provider routing for medgemma vision is not
    consistently available; runs on CPU locally instead).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.compliance import build_compliance_metadata, build_compliance_notice
from app.config import settings
from app.models.medgemma_service import MedGemmaService

logger = logging.getLogger(__name__)


class HFInferenceMedGemmaService(MedGemmaService):
    """MedGemma service backed by HF Inference Providers."""

    def __init__(self) -> None:
        from huggingface_hub import InferenceClient

        if not settings.hf_token:
            raise RuntimeError(
                "medgemma_provider='hf-inference' requires HF_TOKEN to be set. "
                "Generate a token at https://huggingface.co/settings/tokens "
                "with read access to MedGemma."
            )

        self.device = "remote"
        self.model = None
        self.tokenizer = None
        self.vision_model = None
        self.vision_processor = None

        provider = settings.hf_inference_provider or "auto"
        self._model_id = settings.medgemma_model
        self.client = InferenceClient(
            model=self._model_id,
            token=settings.hf_token,
            provider=provider,
            timeout=settings.hf_inference_timeout,
        )
        logger.info(
            "MedGemma remote inference initialized (model=%s provider=%s timeout=%ds)",
            self._model_id, provider, settings.hf_inference_timeout,
        )

    def is_ready(self) -> bool:
        return self.client is not None

    def is_vision_ready(self) -> bool:
        return False

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        raise RuntimeError(
            "Image analysis is not available with medgemma_provider='hf-inference'. "
            "Set medgemma_provider='local' or disable image analysis."
        )

    def _chat(self, prompt_content: str, max_new_tokens: int = 512) -> str:
        """Single-turn chat completion via the configured provider."""
        response = self.client.chat_completion(
            messages=[{"role": "user", "content": prompt_content}],
            max_tokens=max_new_tokens,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    def generate_documentation(
        self,
        transcript: str,
        image_findings: Optional[str] = None,
        detected_language: str = "en",
        similar_cases: Optional[List[Dict[str, Any]]] = None,
        followup_qa: Optional[List[Dict[str, str]]] = None,
        clinical_guidelines: Optional[List[Dict[str, Any]]] = None,
        drug_interactions: Optional[List[Dict[str, Any]]] = None,
        icd10_suggestions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        try:
            from app.prompts.documentation_prompts import (
                create_documentation_prompt,
                create_documentation_with_image_prompt,
            )

            if image_findings:
                prompt_content = create_documentation_with_image_prompt(
                    transcript, image_findings, language=detected_language, followup_qa=followup_qa
                )
            else:
                prompt_content = create_documentation_prompt(
                    transcript, language=detected_language, followup_qa=followup_qa
                )

            decoded = self._chat(prompt_content, max_new_tokens=512)
            self._safe_log_generated_text("MedGemma (remote) response", decoded)

            documentation = self._extract_fields_from_text(decoded, transcript)

            is_valid, error_msg = self._validate_output(documentation, transcript)
            if not is_valid:
                logger.warning(f"Documentation validation failed: {error_msg}")
                return self._build_validation_failed_fallback(transcript, error_msg)

            try:
                oap_sections = self.generate_soap_sections(
                    transcript, documentation,
                    detected_language=detected_language,
                    similar_cases=similar_cases,
                    clinical_guidelines=clinical_guidelines,
                    drug_interactions=drug_interactions,
                    icd10_suggestions=icd10_suggestions,
                )
                documentation.update(oap_sections)
            except Exception as oap_err:
                logger.warning(f"O/A/P generation failed: {oap_err}")
                documentation["soap_note_objective"] = "Pending clinician assessment."
                documentation["soap_note_assessment"] = "Pending clinician assessment."
                documentation["soap_note_plan"] = "Pending clinician assessment."

            documentation["requires_clinician_review"] = True
            documentation["compliance_notice"] = build_compliance_notice()
            documentation["compliance_metadata"] = build_compliance_metadata()
            for k in ("urgency", "severity", "risk_level", "recommended_actions"):
                documentation.pop(k, None)
            return documentation
        except Exception as e:
            logger.error(f"Remote documentation generation failed: {e}")
            raise

    def generate_soap_sections(
        self,
        transcript: str,
        subjective_data: dict,
        detected_language: str = "en",
        similar_cases: Optional[List[Dict[str, Any]]] = None,
        clinical_guidelines: Optional[List[Dict[str, Any]]] = None,
        drug_interactions: Optional[List[Dict[str, Any]]] = None,
        icd10_suggestions: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        from app.prompts.documentation_prompts import create_soap_oap_prompt

        prompt_content = create_soap_oap_prompt(
            transcript, subjective_data,
            language=detected_language,
            similar_cases=similar_cases,
            clinical_guidelines=clinical_guidelines,
            drug_interactions=drug_interactions,
            icd10_suggestions=icd10_suggestions,
        )
        decoded = self._chat(prompt_content, max_new_tokens=512)
        self._safe_log_generated_text("MedGemma (remote) OAP response", decoded)
        return self._parse_soap_sections(decoded)

    def generate_followup_questions(
        self, transcript: str, detected_language: str = "en"
    ) -> List[str]:
        from app.prompts.documentation_prompts import create_followup_questions_prompt

        try:
            prompt_content = create_followup_questions_prompt(transcript, language=detected_language)
            decoded = self._chat(prompt_content, max_new_tokens=256)
            self._safe_log_generated_text("MedGemma (remote) follow-up", decoded)

            json_str = self._extract_json_from_response(decoded)
            data = json.loads(json_str)
            questions = data.get("questions", [])
            if isinstance(questions, list) and 2 <= len(questions) <= 3:
                return [str(q) for q in questions]
            if isinstance(questions, list) and len(questions) > 3:
                return [str(q) for q in questions[:3]]
        except Exception as e:
            logger.warning(f"Remote follow-up question generation failed, using fallback: {e}")

        return self._symptom_aware_fallback_questions(transcript)

    def generate_soap_streaming(
        self,
        transcript: str,
        subjective_data: dict,
        detected_language: str = "en",
        similar_cases: Optional[List[Dict[str, Any]]] = None,
        clinical_guidelines: Optional[List[Dict[str, Any]]] = None,
        drug_interactions: Optional[List[Dict[str, Any]]] = None,
        icd10_suggestions: Optional[List[Dict[str, Any]]] = None,
        specialty: str = "general",
    ):
        from app.prompts.documentation_prompts import create_soap_oap_prompt

        prompt_content = create_soap_oap_prompt(
            transcript=transcript,
            subjective_data=subjective_data,
            language=detected_language,
            similar_cases=similar_cases,
            clinical_guidelines=clinical_guidelines,
            drug_interactions=drug_interactions,
            icd10_suggestions=icd10_suggestions,
            specialty=specialty,
            include_differentials=settings.differential_diagnosis_enabled,
        )

        try:
            stream = self.client.chat_completion(
                messages=[{"role": "user", "content": prompt_content}],
                max_tokens=settings.medgemma_max_tokens,
                temperature=0.0,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception as e:
            logger.error(f"Remote streaming generation failed: {e}")
            yield f"Error: {e}"

    def generate_with_confidence(self, prompt: str, max_new_tokens: int = 512):
        """Logprob confidence is unavailable on remote providers — emit a stub.

        Returns the generated text plus a flat 0.5 confidence so callers that
        rely on the structured field do not crash.
        """
        decoded = self._chat(prompt, max_new_tokens=max_new_tokens)
        confidence_info = {
            "overall_confidence": 0.5,
            "calibration": "remote_stub_v1",
            "token_count": 0,
            "note": "logprobs not available via HF Inference Providers",
        }
        return decoded, confidence_info
