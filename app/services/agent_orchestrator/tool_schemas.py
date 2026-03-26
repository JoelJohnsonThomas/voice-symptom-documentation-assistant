"""
Structured Tool Schemas for Agent-Invocable Capabilities (Phase 3)

Defines the tool interface that agents can invoke during orchestration.
Each tool has a typed schema (input/output), execution function, and
permission scope. The supervisor routes tool calls to the appropriate
service layer.

Follows the OpenAI function-calling / LangChain tool convention so
the tools can be directly passed to LLM tool-use APIs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """Categories for agent tools."""
    ASR = "asr"
    NER = "ner"
    DOCUMENTATION = "documentation"
    RAG = "rag"
    SAFETY = "safety"
    COMPLIANCE = "compliance"
    CODING = "coding"
    FHIR = "fhir"


@dataclass
class ToolParameter:
    """Single parameter for a tool."""
    name: str
    type: str  # string, integer, number, boolean, array, object
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolSchema:
    """Complete schema for an agent-invocable tool."""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: str = "object"  # Return type description
    requires_phi_access: bool = False
    requires_auth: bool = True
    execute_fn: Optional[Callable] = None

    def to_openai_function(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        properties = {}
        required = []
        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_langchain_tool(self) -> Dict[str, Any]:
        """Convert to LangChain tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.to_openai_function()["parameters"],
        }


# =====================================================================
# Tool Definitions
# =====================================================================

TRANSCRIBE_AUDIO = ToolSchema(
    name="transcribe_audio",
    description=(
        "Transcribe an audio segment to text using faster-whisper ASR. "
        "Returns transcript with word-level timestamps."
    ),
    category=ToolCategory.ASR,
    parameters=[
        ToolParameter("audio_base64", "string", "Base64-encoded audio data"),
        ToolParameter("sample_rate", "integer", "Sample rate in Hz", default=16000),
        ToolParameter("language", "string", "Language code (auto-detect if empty)", required=False),
    ],
    returns="TranscriptionResult with text, words[], language, duration",
    requires_phi_access=True,
)

DIARIZE_SPEAKERS = ToolSchema(
    name="diarize_speakers",
    description=(
        "Perform speaker diarization on an audio segment. "
        "Returns speaker-labeled segments with timestamps."
    ),
    category=ToolCategory.ASR,
    parameters=[
        ToolParameter("audio_base64", "string", "Base64-encoded audio data"),
        ToolParameter("sample_rate", "integer", "Sample rate in Hz", default=16000),
        ToolParameter("num_speakers", "integer", "Expected number of speakers", required=False),
        ToolParameter("word_timestamps", "array", "Word timestamps from ASR for alignment", required=False),
    ],
    returns="List of DiarizedSegment with speaker, start, end, text",
    requires_phi_access=True,
)

EXTRACT_ENTITIES = ToolSchema(
    name="extract_entities",
    description=(
        "Extract medical entities (conditions, medications) from text "
        "using SciSpaCy NER with UMLS code linking."
    ),
    category=ToolCategory.NER,
    parameters=[
        ToolParameter("text", "string", "Clinical text to analyze"),
    ],
    returns="Dict with conditions[] and medications[], each with code, system, confidence",
)

EXTRACT_VITALS = ToolSchema(
    name="extract_vitals",
    description=(
        "Extract vital signs (BP, HR, temp, SpO2, RR) from text "
        "using regex patterns."
    ),
    category=ToolCategory.NER,
    parameters=[
        ToolParameter("text", "string", "Text containing vital sign mentions"),
    ],
    returns="Dict with temperature, blood_pressure, heart_rate, respiratory_rate, oxygen_saturation",
)

GENERATE_FOLLOWUP_QUESTIONS = ToolSchema(
    name="generate_followup_questions",
    description=(
        "Generate 2-3 clinically relevant follow-up questions "
        "based on the patient's transcript."
    ),
    category=ToolCategory.DOCUMENTATION,
    parameters=[
        ToolParameter("transcript", "string", "Patient transcript"),
        ToolParameter("language", "string", "Language code", default="en"),
    ],
    returns="List of 2-3 follow-up question strings",
    requires_phi_access=True,
)

GENERATE_SOAP = ToolSchema(
    name="generate_soap",
    description=(
        "Generate full SOAP documentation from transcript and context. "
        "Includes Subjective extraction and OAP generation."
    ),
    category=ToolCategory.DOCUMENTATION,
    parameters=[
        ToolParameter("transcript", "string", "Full patient transcript"),
        ToolParameter("language", "string", "Language code", default="en"),
        ToolParameter("specialty", "string", "Clinical specialty", default="general",
                      enum=["general", "emergency", "primary_care", "psychiatry", "ob_gyn", "pediatrics"]),
        ToolParameter("followup_qa", "array", "Follow-up Q&A pairs", required=False),
        ToolParameter("similar_cases", "array", "RAG-retrieved similar cases", required=False),
    ],
    returns="Full documentation dict with SOAP sections, confidence, compliance metadata",
    requires_phi_access=True,
)

RETRIEVE_SIMILAR_CASES = ToolSchema(
    name="retrieve_similar_cases",
    description=(
        "Search the knowledge base for similar past cases "
        "using vector similarity search."
    ),
    category=ToolCategory.RAG,
    parameters=[
        ToolParameter("query", "string", "Search query (transcript or chief complaint)"),
        ToolParameter("top_k", "integer", "Number of results to return", default=3),
    ],
    returns="List of similar cases with document text, similarity score, metadata",
)

CHECK_DRUG_INTERACTIONS = ToolSchema(
    name="check_drug_interactions",
    description=(
        "Check for drug-drug interactions given a list of medication names."
    ),
    category=ToolCategory.CODING,
    parameters=[
        ToolParameter("medications", "array", "List of medication name strings"),
    ],
    returns="List of interactions with severity, effect, recommendation",
)

DETECT_EMERGENCY = ToolSchema(
    name="detect_emergency",
    description=(
        "Check text for emergency symptoms requiring immediate escalation."
    ),
    category=ToolCategory.SAFETY,
    parameters=[
        ToolParameter("text", "string", "User input text to check"),
    ],
    returns="Dict with is_emergency, emergency_type, response_text",
)

SCAN_PHI = ToolSchema(
    name="scan_phi",
    description=(
        "Scan text for Protected Health Information (PHI) using Presidio NER."
    ),
    category=ToolCategory.SAFETY,
    parameters=[
        ToolParameter("text", "string", "Text to scan for PHI"),
        ToolParameter("redact", "boolean", "If True, return redacted text", default=False),
    ],
    returns="PHIScanResult with has_phi, entities[], optionally redacted_text",
    requires_phi_access=True,
)

SCAN_PROMPT_INJECTION = ToolSchema(
    name="scan_prompt_injection",
    description=(
        "Scan user input for prompt injection attempts."
    ),
    category=ToolCategory.SAFETY,
    parameters=[
        ToolParameter("text", "string", "User input to scan"),
    ],
    returns="ScanResult with is_injection, matches[], risk_score",
)

CHECK_HALLUCINATION = ToolSchema(
    name="check_hallucination",
    description=(
        "Check if generated text is grounded in evidence using NLI scoring."
    ),
    category=ToolCategory.SAFETY,
    parameters=[
        ToolParameter("generated_text", "string", "Generated SOAP section text"),
        ToolParameter("evidence_texts", "array", "List of evidence document strings"),
        ToolParameter("transcript", "string", "Original patient transcript"),
    ],
    returns="Dict with is_grounded, overlap_ratio, risk_level, claims[]",
)

CODE_ICD10 = ToolSchema(
    name="code_icd10",
    description=(
        "Resolve medical entity text to ICD-10-CM / SNOMED-CT codes "
        "using UMLS entity linker."
    ),
    category=ToolCategory.CODING,
    parameters=[
        ToolParameter("entity_text", "string", "Medical entity mention (e.g. 'hypertension')"),
        ToolParameter("entity_type", "string", "Entity type", enum=["DISEASE", "CHEMICAL", "PROCEDURE"]),
    ],
    returns="List of candidate codes with code, system, description, confidence",
)

GENERATE_FHIR_BUNDLE = ToolSchema(
    name="generate_fhir_bundle",
    description=(
        "Generate a FHIR R4 Bundle from documentation and entities."
    ),
    category=ToolCategory.FHIR,
    parameters=[
        ToolParameter("documentation", "object", "SOAP documentation dict"),
        ToolParameter("entities", "object", "Extracted NER entities dict"),
        ToolParameter("patient_id", "string", "Patient identifier", required=False),
    ],
    returns="FHIR R4 Bundle JSON",
    requires_phi_access=True,
)


# =====================================================================
# Tool Registry
# =====================================================================

TOOL_REGISTRY: Dict[str, ToolSchema] = {
    tool.name: tool
    for tool in [
        TRANSCRIBE_AUDIO,
        DIARIZE_SPEAKERS,
        EXTRACT_ENTITIES,
        EXTRACT_VITALS,
        GENERATE_FOLLOWUP_QUESTIONS,
        GENERATE_SOAP,
        RETRIEVE_SIMILAR_CASES,
        CHECK_DRUG_INTERACTIONS,
        DETECT_EMERGENCY,
        SCAN_PHI,
        SCAN_PROMPT_INJECTION,
        CHECK_HALLUCINATION,
        CODE_ICD10,
        GENERATE_FHIR_BUNDLE,
    ]
}


def get_tools_for_agent(agent_role: str) -> List[ToolSchema]:
    """Get the tools available to a specific agent role."""
    role_tools = {
        "intake": [
            "transcribe_audio", "diarize_speakers", "extract_entities",
            "extract_vitals", "generate_followup_questions", "retrieve_similar_cases",
        ],
        "documentation": [
            "generate_soap", "retrieve_similar_cases", "extract_entities",
            "check_hallucination", "code_icd10",
        ],
        "safety": [
            "detect_emergency", "scan_phi", "scan_prompt_injection",
            "check_hallucination",
        ],
        "compliance": [
            "code_icd10", "check_drug_interactions", "generate_fhir_bundle",
            "scan_phi",
        ],
    }
    tool_names = role_tools.get(agent_role, [])
    return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]


def get_openai_functions_for_agent(agent_role: str) -> List[Dict[str, Any]]:
    """Get OpenAI function-calling schemas for an agent role."""
    return [tool.to_openai_function() for tool in get_tools_for_agent(agent_role)]


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with given arguments.

    Routes to the appropriate service layer function.
    """
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}

    tool = TOOL_REGISTRY[tool_name]

    try:
        if tool_name == "extract_entities":
            from app.models.ner_service import get_ner_service
            svc = get_ner_service()
            return svc.extract_entities(arguments["text"])

        elif tool_name == "extract_vitals":
            from app.models.ner_service import get_ner_service
            svc = get_ner_service()
            return svc.extract_vitals(arguments["text"])

        elif tool_name == "detect_emergency":
            from app.models.safety_guardrails import check_emergency
            result = check_emergency(arguments["text"])
            return result or {"is_emergency": False}

        elif tool_name == "scan_phi":
            from app.security.phi_detector import get_phi_detector
            detector = get_phi_detector()
            if arguments.get("redact"):
                redacted, scan = detector.redact_for_storage(arguments["text"])
                return {"has_phi": scan.has_phi, "redacted_text": redacted}
            scan = detector.scan(arguments["text"])
            return {"has_phi": scan.has_phi, "entity_count": len(scan.entities) if scan.entities else 0}

        elif tool_name == "scan_prompt_injection":
            from app.security.prompt_guard import scan_input
            result = scan_input(arguments["text"])
            return {"is_injection": result.is_injection, "risk_score": getattr(result, "risk_score", 0.0)}

        elif tool_name == "check_hallucination":
            from app.models.rag_evaluation_service import check_hallucination
            return check_hallucination(
                arguments["generated_text"],
                arguments["evidence_texts"],
                arguments.get("transcript", ""),
            )

        elif tool_name == "retrieve_similar_cases":
            from app.models.rag_service import retrieve_similar_sessions
            return retrieve_similar_sessions(
                arguments["query"],
                top_k=arguments.get("top_k", 3),
            )

        elif tool_name == "check_drug_interactions":
            from app.models.drug_interaction_service import check_interactions
            return check_interactions(arguments["medications"])

        elif tool_name == "code_icd10":
            from app.models.ner_service import _get_umls_linker
            linker = _get_umls_linker()
            return linker.resolve_entity(arguments["entity_text"], arguments["entity_type"])

        else:
            return {"error": f"Tool '{tool_name}' execution not yet implemented"}

    except Exception as e:
        logger.error(f"Tool execution failed for '{tool_name}': {e}")
        return {"error": str(e)}
