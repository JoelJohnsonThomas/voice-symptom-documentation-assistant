# SOC 2 Type II Control Matrix — Voice Symptom Triage Assistant

## Trust Service Criteria Coverage

### CC1: Control Environment
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC1.1 Organizational commitment to integrity | HIPAA compliance notice in all outputs | `app/compliance.py` |
| CC1.2 Board/management oversight | Audit logging of all administrative actions | `app/middleware/audit.py` |
| CC1.3 Organizational structure | Role-based access control (admin, clinician, viewer) | `app/auth.py` |
| CC1.4 Commitment to competence | Clinician review required for all AI outputs | `compliance_metadata.review_requirement` |

### CC2: Communication and Information
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC2.1 Internal communication | Structured audit logs with correlation IDs | `AuditLog.correlation_id` |
| CC2.2 External communication | FHIR R4 interop for health data exchange | `app/models/fhir_service.py` |

### CC3: Risk Assessment
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC3.1 Risk identification | Prompt injection scanning on all inputs | `app/security/prompt_guard.py` |
| CC3.2 Fraud risk | Login rate limiting (5 attempts / 5min) | `app/auth.py:_check_login_rate_limit` |
| CC3.3 Change management | Alembic database migrations | `alembic/` |

### CC5: Control Activities
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC5.1 Risk mitigation controls | PHI detection + redaction (Presidio NER) | `app/security/phi_detector.py` |
| CC5.2 Technology general controls | AES-256-GCM encryption at rest | `app/encryption.py` |
| CC5.3 Security policies through technology | Production mode enforces all security settings | `app/config.py:validate_production_settings()` |

### CC6: Logical and Physical Access Controls
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC6.1 Logical access security | JWT + MFA (TOTP) authentication | `app/auth.py` |
| CC6.2 Prior to issuing credentials | User provisioning with role assignment | `app/routes/auth_routes.py` |
| CC6.3 Registration/authorization | OIDC SSO integration (Okta, Azure AD) | `app/routes/oidc_routes.py` |
| CC6.6 Restrictions on access | RBAC with endpoint-level authorization | `app/auth.py:require_role()` |
| CC6.7 Information transmission | HTTPS/TLS 1.3 enforced | K8s ingress + cert-manager |
| CC6.8 Unauthorized access prevention | NetworkPolicy restricting inter-service communication | `deploy/k8s/templates/network-policy.yaml` |

### CC7: System Operations
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC7.1 Detection of unauthorized changes | Document versioning with diff tracking | `DocumentVersion` model |
| CC7.2 Monitoring of components | OpenTelemetry distributed tracing | `app/infrastructure/observability.py` |
| CC7.3 Environmental threat evaluation | Safety agent runs on every input | `SafetyAgent` |
| CC7.4 Recovery planning | Cross-session memory with Redis persistence | `app/services/memory/` |

### CC8: Change Management
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC8.1 Change management process | Alembic versioned migrations | `alembic/versions/` |

### CC9: Risk Mitigation
| Control | Implementation | Evidence |
|---------|---------------|----------|
| CC9.1 Risk mitigation | Hallucination detection with NLI grounding | `CitationGroundingService` |
| CC9.2 Vendor risk management | Graceful fallbacks for all external deps | All services use try/except import |

## HIPAA-Specific Controls

| Requirement | Implementation |
|------------|---------------|
| Access Controls (164.312(a)) | JWT + MFA + RBAC + session timeout |
| Audit Controls (164.312(b)) | Comprehensive audit logging with PHI access tracking |
| Integrity Controls (164.312(c)) | Document versioning, encryption at rest |
| Transmission Security (164.312(e)) | TLS 1.3, encrypted WebSocket |
| PHI De-identification (164.514) | Presidio NER + regex hybrid redaction |
| Minimum Necessary (164.502(b)) | Role-based data access filtering |
| Data Retention (164.530(j)) | Configurable retention policies with secure purge |
| Breach Notification (164.408) | Audit log alerting for anomalous PHI access |

## Audit Period

This document covers the control implementation as of system version 4.0.0.
Continuous monitoring is performed via OpenTelemetry metrics and audit log analysis.
