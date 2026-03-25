"""
FHIR Export Service — HL7 FHIR R4 Resource Generation

Generates FHIR-compliant resources (Patient, Encounter, Condition, Observation)
from the application's documentation output and NER entities.

Supports export as a FHIR Bundle (transaction) and direct push to EHR systems
(Epic, Cerner, HAPI FHIR) via their FHIR REST API.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class FHIRExportService:
    """Generates HL7 FHIR R4 resources from documentation data."""

    FHIR_DATE_FMT = "%Y-%m-%dT%H:%M:%S+00:00"

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _uid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime(FHIRExportService.FHIR_DATE_FMT)

    # ── Patient (placeholder) ────────────────────────────────
    def build_patient(self, patient_info: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Build a minimal FHIR Patient resource.
        In production this would come from the EHR; here we generate a stub.
        """
        pid = self._uid()
        info = patient_info or {}
        return {
            "resourceType": "Patient",
            "id": pid,
            "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
            "identifier": [{
                "system": "urn:oid:2.16.840.1.113883.19.5",
                "value": info.get("mrn", f"MRN-{pid[:8]}")
            }],
            "name": [{
                "use": "official",
                "family": info.get("last_name", "Unknown"),
                "given": [info.get("first_name", "Patient")]
            }],
            "gender": info.get("gender", "unknown"),
            "birthDate": info.get("birth_date", "1970-01-01")
        }

    # ── Encounter ────────────────────────────────────────────
    def build_encounter(self, patient_id: str, documentation: Dict) -> Dict[str, Any]:
        """Build a FHIR Encounter resource for this intake session."""
        return {
            "resourceType": "Encounter",
            "id": self._uid(),
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory"
            },
            "type": [{
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "185349003",
                    "display": "Encounter for symptom assessment"
                }]
            }],
            "subject": {"reference": f"Patient/{patient_id}"},
            "period": {
                "start": self._now_iso(),
                "end": self._now_iso()
            },
            "reasonCode": [{
                "text": documentation.get("chief_complaint", "Symptom intake")
            }]
        }

    # ── Condition (from NER entities + chief complaint) ──────
    def build_conditions(
        self,
        patient_id: str,
        encounter_id: str,
        documentation: Dict,
        entities: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Build FHIR Condition resources from NER-extracted conditions."""
        conditions = []

        # From NER entities
        ner_conditions = (entities or {}).get("conditions", [])
        for ent in ner_conditions:
            code_system = "http://hl7.org/fhir/sid/icd-10-cm" if ent.get("system") == "ICD-10" \
                else "http://snomed.info/sct"
            conditions.append({
                "resourceType": "Condition",
                "id": self._uid(),
                "clinicalStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active"
                    }]
                },
                "verificationStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": "unconfirmed"
                    }]
                },
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                        "display": "Encounter Diagnosis"
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": code_system,
                        "code": ent.get("code", ""),
                        "display": ent.get("text", "")
                    }],
                    "text": ent.get("text", "")
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "encounter": {"reference": f"Encounter/{encounter_id}"},
                "recordedDate": self._now_iso()
            })

        # Fallback: chief complaint as a single condition if NER found nothing
        if not conditions:
            cc = documentation.get("chief_complaint", "")
            if cc and cc != "not specified":
                conditions.append({
                    "resourceType": "Condition",
                    "id": self._uid(),
                    "clinicalStatus": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active"
                        }]
                    },
                    "verificationStatus": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                            "code": "unconfirmed"
                        }]
                    },
                    "code": {"text": cc},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "recordedDate": self._now_iso()
                })

        return conditions

    # ── Observation (SOAP subjective + symptom details) ──────
    def build_observations(
        self,
        patient_id: str,
        encounter_id: str,
        documentation: Dict
    ) -> List[Dict[str, Any]]:
        """Build FHIR Observation resources from SOAP notes."""
        observations = []

        # Subjective narrative
        soap_s = documentation.get("soap_note_subjective", "")
        if soap_s and soap_s != "Pending clinician assessment.":
            observations.append({
                "resourceType": "Observation",
                "id": self._uid(),
                "status": "preliminary",
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "10164-2",
                        "display": "History of Present illness Narrative"
                    }],
                    "text": "Subjective"
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "encounter": {"reference": f"Encounter/{encounter_id}"},
                "effectiveDateTime": self._now_iso(),
                "valueString": soap_s
            })

        # Symptom details as structured observation
        details = documentation.get("symptom_details", {})
        symptoms = details.get("symptoms_mentioned", [])
        if symptoms and symptoms != ["not specified"]:
            observations.append({
                "resourceType": "Observation",
                "id": self._uid(),
                "status": "preliminary",
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "75325-1",
                        "display": "Symptom"
                    }],
                    "text": "Reported Symptoms"
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "encounter": {"reference": f"Encounter/{encounter_id}"},
                "effectiveDateTime": self._now_iso(),
                "valueString": ", ".join(symptoms),
                "component": self._symptom_components(details)
            })

        return observations

    def _symptom_components(self, details: Dict) -> List[Dict]:
        """Build FHIR Observation components for onset/duration/location."""
        components = []
        field_map = {
            "onset": ("LA19747-7", "Onset"),
            "duration": ("LA18821-1", "Duration"),
            "location": ("LA18327-9", "Body Site"),
        }
        for key, (code, display) in field_map.items():
            val = details.get(key, "not specified")
            if val and val != "not specified":
                components.append({
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": code, "display": display}]
                    },
                    "valueString": val
                })
        return components

    # ── Bundle ───────────────────────────────────────────────
    def build_bundle(
        self,
        documentation: Dict,
        entities: Optional[Dict] = None,
        patient_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Build a complete FHIR R4 Bundle (transaction) containing all resources.
        """
        patient = self.build_patient(patient_info)
        patient_id = patient["id"]

        encounter = self.build_encounter(patient_id, documentation)
        encounter_id = encounter["id"]

        conditions = self.build_conditions(patient_id, encounter_id, documentation, entities)
        observations = self.build_observations(patient_id, encounter_id, documentation)

        # Assemble all resources into bundle entries
        all_resources = [patient, encounter] + conditions + observations
        entries = []
        for res in all_resources:
            entries.append({
                "fullUrl": f"urn:uuid:{res['id']}",
                "resource": res,
                "request": {
                    "method": "POST",
                    "url": res["resourceType"]
                }
            })

        bundle = {
            "resourceType": "Bundle",
            "id": self._uid(),
            "type": "transaction",
            "timestamp": self._now_iso(),
            "entry": entries
        }

        logger.info(
            f"FHIR Bundle built: {len(entries)} entries "
            f"({len(conditions)} conditions, {len(observations)} observations)"
        )
        return bundle

    # ── Push to external EHR ─────────────────────────────────
    async def push_to_ehr(
        self,
        bundle: Dict,
        ehr_url: str,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST a FHIR Bundle to an external EHR/FHIR server.

        Args:
            bundle: FHIR Bundle dict
            ehr_url: Base FHIR server URL (e.g. https://hapi.fhir.org/baseR4)
            auth_token: Optional Bearer token for authentication

        Returns:
            Dict with status and server response
        """
        import httpx

        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(ehr_url, json=bundle, headers=headers)

            if resp.status_code in (200, 201):
                logger.info(f"FHIR push successful: {resp.status_code}")
                return {"success": True, "status_code": resp.status_code, "response": resp.json()}
            else:
                logger.warning(f"FHIR push returned {resp.status_code}: {resp.text[:500]}")
                return {"success": False, "status_code": resp.status_code, "error": resp.text[:500]}

        except Exception as e:
            logger.error(f"FHIR push failed: {e}")
            return {"success": False, "error": str(e)}


    # -----------------------------------------------------------------
    # Phase 7: HL7 v2 Message Generation
    # -----------------------------------------------------------------

    def build_hl7v2_adt(
        self,
        documentation: Dict,
        entities: Optional[Dict] = None,
        patient_info: Optional[Dict] = None,
    ) -> str:
        """Generate an HL7 v2.x ADT (Admit/Discharge/Transfer) message.

        Produces a minimal ADT^A04 (Register a Patient) message suitable
        for legacy EHR systems that don't support FHIR.
        """
        info = patient_info or {}
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d%H%M%S")
        msg_id = self._uid()[:20]

        pid = info.get("id", self._uid()[:10])
        family = info.get("family_name", "UNKNOWN")
        given = info.get("given_name", "PATIENT")
        dob = info.get("birth_date", "19700101")
        gender = info.get("gender", "U")

        chief = documentation.get("chief_complaint", "Not specified")[:80]

        segments = [
            f"MSH|^~\\&|VOXDOC|VOXDOC_FAC|EHR|EHR_FAC|{ts}||ADT^A04^ADT_A01|{msg_id}|P|2.5.1",
            f"EVN|A04|{ts}",
            f"PID|1||{pid}^^^VOXDOC||{family}^{given}||{dob}|{gender}",
            f"PV1|1|O|^^^VOXDOC||||||||||||||||{self._uid()[:10]}",
            f"DG1|1||{chief}||{ts}|A",
        ]

        # Add diagnosis segments from entities
        if entities:
            for i, cond in enumerate(entities.get("conditions", [])[:5], start=2):
                code = cond.get("code", "")
                text = cond.get("text", "")
                system = cond.get("system", "ICD-10")
                segments.append(f"DG1|{i}|{system}|{code}^{text}||{ts}|A")

        return "\r".join(segments)

    def build_hl7v2_oru(
        self,
        documentation: Dict,
        entities: Optional[Dict] = None,
        patient_info: Optional[Dict] = None,
    ) -> str:
        """Generate an HL7 v2.x ORU (Observation Result) message.

        Embeds the SOAP note as observation text segments.
        """
        info = patient_info or {}
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d%H%M%S")
        msg_id = self._uid()[:20]

        pid = info.get("id", self._uid()[:10])
        family = info.get("family_name", "UNKNOWN")
        given = info.get("given_name", "PATIENT")

        segments = [
            f"MSH|^~\\&|VOXDOC|VOXDOC_FAC|EHR|EHR_FAC|{ts}||ORU^R01^ORU_R01|{msg_id}|P|2.5.1",
            f"PID|1||{pid}^^^VOXDOC||{family}^{given}",
            f"OBR|1|||SOAP_NOTE^SOAP Documentation^VOXDOC|||{ts}",
        ]

        # Each SOAP section as an OBX segment
        soap_sections = [
            ("S", documentation.get("soap_subjective", "")),
            ("O", documentation.get("soap_objective", "")),
            ("A", documentation.get("soap_assessment", "")),
            ("P", documentation.get("soap_plan", "")),
        ]
        for i, (label, text) in enumerate(soap_sections, start=1):
            if text:
                # HL7 v2 limits OBX text; truncate if needed
                clean = text.replace("\r", " ").replace("\n", " ").replace("|", " ")[:1000]
                segments.append(f"OBX|{i}|TX|SOAP_{label}^{label}||{clean}|||N|||F")

        return "\r".join(segments)

    # -----------------------------------------------------------------
    # Phase 7: CDA/CCDA Export
    # -----------------------------------------------------------------

    def build_ccda_document(
        self,
        documentation: Dict,
        entities: Optional[Dict] = None,
        patient_info: Optional[Dict] = None,
    ) -> str:
        """Generate a simplified CCD (Continuity of Care Document) in XML.

        Follows the HL7 C-CDA (Consolidated Clinical Document Architecture)
        template structure with the core required sections.
        """
        info = patient_info or {}
        now = datetime.now(timezone.utc)
        doc_id = self._uid()
        ts = now.strftime("%Y%m%d%H%M%S")

        given = info.get("given_name", "Patient")
        family = info.get("family_name", "Unknown")
        gender = info.get("gender", "UN")
        dob = info.get("birth_date", "19700101")

        soap_s = _xml_escape(documentation.get("soap_subjective", "Not documented"))
        soap_o = _xml_escape(documentation.get("soap_objective", "Not documented"))
        soap_a = _xml_escape(documentation.get("soap_assessment", "Not documented"))
        soap_p = _xml_escape(documentation.get("soap_plan", "Not documented"))
        chief = _xml_escape(documentation.get("chief_complaint", "Not specified"))

        # Build conditions list for Problems section
        problems_entries = ""
        if entities:
            for cond in entities.get("conditions", [])[:10]:
                code = _xml_escape(cond.get("code", ""))
                text = _xml_escape(cond.get("text", ""))
                problems_entries += f"""
                <entry>
                    <act classCode="ACT" moodCode="EVN">
                        <code code="{code}" displayName="{text}" codeSystemName="ICD-10-CM"/>
                        <statusCode code="active"/>
                    </act>
                </entry>"""

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <realmCode code="US"/>
    <typeId root="2.16.840.1.113883.1.3" extension="POCD_HD000040"/>
    <templateId root="2.16.840.1.113883.10.20.22.1.2"/>
    <id root="{doc_id}"/>
    <code code="34133-9" displayName="Summarization of Episode Note" codeSystem="2.16.840.1.113883.6.1"/>
    <title>VoxDoc Clinical Document</title>
    <effectiveTime value="{ts}"/>
    <confidentialityCode code="N"/>
    <recordTarget>
        <patientRole>
            <patient>
                <name><given>{_xml_escape(given)}</given><family>{_xml_escape(family)}</family></name>
                <administrativeGenderCode code="{gender}"/>
                <birthTime value="{dob}"/>
            </patient>
        </patientRole>
    </recordTarget>
    <author>
        <assignedAuthor><id root="2.16.840.1.113883.4.6"/></assignedAuthor>
    </author>
    <component>
        <structuredBody>
            <component>
                <section>
                    <title>Chief Complaint</title>
                    <text>{chief}</text>
                </section>
            </component>
            <component>
                <section>
                    <title>Subjective</title>
                    <text>{soap_s}</text>
                </section>
            </component>
            <component>
                <section>
                    <title>Objective</title>
                    <text>{soap_o}</text>
                </section>
            </component>
            <component>
                <section>
                    <title>Assessment</title>
                    <text>{soap_a}</text>
                </section>
            </component>
            <component>
                <section>
                    <title>Plan</title>
                    <text>{soap_p}</text>
                </section>
            </component>
            <component>
                <section>
                    <title>Problems</title>
                    <text>Active problem list from encounter.</text>{problems_entries}
                </section>
            </component>
        </structuredBody>
    </component>
</ClinicalDocument>"""

    # -----------------------------------------------------------------
    # Phase 7: Webhook Notifications
    # -----------------------------------------------------------------

    async def send_webhook(
        self,
        webhook_url: str,
        event_type: str,
        payload: Dict,
        auth_token: Optional[str] = None,
    ) -> Dict:
        """Send a webhook notification when a session is finalized.

        Args:
            webhook_url: The URL to POST the notification to
            event_type: e.g. "session.finalized", "session.created"
            payload: Event data
            auth_token: Optional Bearer token for authentication
        """
        import httpx

        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        webhook_body = {
            "event": event_type,
            "timestamp": self._now_iso(),
            "data": payload,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=webhook_body, headers=headers)
                return {
                    "success": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "response": resp.text[:500],
                }
        except Exception as e:
            logger.error("Webhook delivery failed: %s", e)
            return {"success": False, "error": str(e)}


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# Global singleton
_fhir_service = None


def get_fhir_service() -> FHIRExportService:
    """Get or create the FHIR Export service instance."""
    global _fhir_service
    if _fhir_service is None:
        _fhir_service = FHIRExportService()
    return _fhir_service
