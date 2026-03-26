# FDA Software as a Medical Device (SaMD) Classification

## Product: Voice Symptom Triage Assistant v4.0

## 1. Intended Use Statement

The Voice Symptom Triage Assistant is an **administrative documentation tool**
that converts spoken patient encounters into structured clinical notes (SOAP format).

**This system does NOT:**
- Diagnose diseases or medical conditions
- Recommend treatments, medications, or dosages
- Triage patients by urgency or severity
- Make clinical decisions of any kind
- Replace clinician judgment

**This system DOES:**
- Transcribe spoken audio to text
- Extract structured medical entities from transcripts
- Generate draft SOAP documentation for clinician review
- Provide ICD-10/SNOMED code suggestions (clinician-validated)
- Export documentation in FHIR R4 format

## 2. Regulatory Classification

### IMDRF SaMD Classification Framework

| Factor | Assessment |
|--------|-----------|
| **Significance of information** | The system provides information to **inform** clinical management, not to **drive** or **treat** |
| **State of healthcare situation** | Non-critical — documentation occurs post-encounter or during routine care |
| **IMDRF Category** | **Category I** (lowest risk) — Inform only |

### FDA Risk Classification

Based on the intended use as an **administrative documentation aid**:

- **Not a medical device** under 21 CFR 520(o)(1)(E) — the system is a
  Clinical Decision Support (CDS) tool that meets all four CDS exclusion
  criteria:
  1. Not intended to acquire, process, or analyze a medical image/signal
  2. Intended for display to a healthcare professional (clinician review required)
  3. Intended for the healthcare professional to independently review the basis
  4. Does not replace clinical judgment — explicitly flagged as suggestions

### Relevant FDA Guidance Documents

- "Clinical Decision Support Software" (September 2022)
- "Policy for Device Software Functions and Mobile Medical Applications"
- "Software as a Medical Device (SaMD): Clinical Evaluation" (IMDRF/SaMD WG/N41FINAL:2017)

## 3. Design Controls (Per 21 CFR 820.30, if applicable)

Even though the system may qualify for CDS exclusion, we maintain
design controls as best practice:

### 3.1 Design Input
- Clinician workflow requirements
- HIPAA security requirements
- HL7 FHIR R4 interoperability standards
- Multi-language support requirements

### 3.2 Design Output
- SOAP note generation with mandatory clinician review
- Confidence scores with verification indicators
- Hallucination detection and ungrounded claim flagging
- Comprehensive audit trail

### 3.3 Design Verification
- Unit and integration test suites
- OWASP security scanning
- PHI detection recall testing (target: 98%)
- SOAP quality evaluation against clinician gold standard

### 3.4 Design Validation
- Clinician user acceptance testing
- Ambient mode encounter simulation (15-min encounters)
- Multi-specialty template validation

### 3.5 Risk Management (ISO 14971)
| Hazard | Severity | Probability | Mitigation |
|--------|----------|-------------|------------|
| Incorrect SOAP content | Moderate | Possible | Mandatory clinician review, confidence scoring |
| Missed emergency symptoms | High | Unlikely | Safety agent with emergency detection |
| PHI exposure | High | Unlikely | Presidio NER + encryption at rest + audit logging |
| Hallucinated medical facts | Moderate | Possible | NLI citation grounding, [UNGROUNDED] tagging |
| System downtime | Low | Possible | K8s auto-scaling, multi-region failover |

## 4. Compliance Safeguards in Code

| Safeguard | Location |
|-----------|----------|
| All outputs include `requires_clinician_review: true` | `medgemma_service.py` |
| Compliance notice appended to every response | `compliance.py:build_compliance_notice()` |
| No urgency/severity/triage fields in output | `medgemma_service.py` (fields explicitly popped) |
| Differential diagnoses labeled "for consideration only" | `documentation_prompts.py:DIFFERENTIAL_DISCLAIMER` |
| Emergency escalation does NOT diagnose — directs to 911 | `safety_guardrails.py` |

## 5. Post-Market Surveillance Plan

- Clinician feedback collection via LoRA training pipeline
- Hallucination rate monitoring via OpenTelemetry metrics
- Monthly SOAP quality regression testing
- Quarterly clinician satisfaction surveys
- Adverse event reporting procedure (if ever reclassified)

---

**Document Status:** Pre-submission draft
**Regulatory Counsel Review:** Pending
**Last Updated:** 2026-03-26
