export interface DashboardStats {
  totalSessions: number;
  activeSessions: number;
  avgProcessingTime: number;
  successRate: number;
  todaySessions: number;
  weekSessions: number;
}

export interface SystemHealth {
  status: "healthy" | "degraded" | "down";
  uptime: number;
  cpu: number;
  memory: number;
  gpu?: number;
  lastChecked: string;
}

export interface SessionSummary {
  id: string;
  patientId?: string;
  chiefComplaint: string;
  status: "recording" | "processing" | "completed" | "error";
  createdAt: string;
  updatedAt: string;
  duration?: number;
  language?: string;
}

export interface SessionDetail extends SessionSummary {
  audioUrl?: string;
  transcript?: string;
  documentation?: DocumentationResult;
  followUpQuestions?: FollowUpQuestion[];
  metadata?: Record<string, unknown>;
}

export interface DocumentationResult {
  chiefComplaint: string;
  clinicalDetails: string;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  nerEntities: NEREntities;
  confidence: ConfidenceScores;
  language?: string;
  processingTime?: number;
}

export interface NEREntities {
  conditions: EntityItem[];
  medications: EntityItem[];
  procedures?: EntityItem[];
  anatomical?: EntityItem[];
}

export interface EntityItem {
  text: string;
  type: string;
  confidence: number;
  umlsCode?: string;
}

export interface ConfidenceScores {
  overall: number;
  transcription: number;
  extraction: number;
  coding: number;
}

export interface FollowUpQuestion {
  id: string;
  question: string;
  answer?: string;
  required: boolean;
}

export interface MonitoringData {
  models: ModelPerformance[];
  queue: QueueStatus;
  connections: ConnectionStats;
  alerts: Alert[];
  uptime: number;
  lastRefresh: string;
}

export interface ModelPerformance {
  name: string;
  status: "online" | "offline" | "degraded";
  requestCount: number;
  errorRate: number;
  avgLatency: number;
  p95Latency: number;
}

export interface QueueStatus {
  active: number;
  queued: number;
  maxConcurrent: number;
  avgProcessingTime: number;
}

export interface ConnectionStats {
  http: number;
  websocket: number;
}

export interface Alert {
  id: string;
  severity: "info" | "warning" | "error" | "critical";
  message: string;
  timestamp: string;
  dismissed?: boolean;
}

export interface HIPAAComplianceData {
  auditTrailCount: number;
  encryptionStatus: "active" | "inactive";
  retentionDays: number;
  lastAudit: string;
  complianceScore: number;
  pendingActions: number;
}

export interface AuditLogEntry {
  id: string;
  action: string;
  userId: string;
  timestamp: string;
  details: string;
  ipAddress?: string;
}

export interface EHRPushRequest {
  fhirUrl: string;
  authToken: string;
  sessionId: string;
  preset?: "hapi" | "epic" | "cerner";
}

export interface EHRPushResponse {
  success: boolean;
  bundleId?: string;
  error?: string;
}

export interface PipelineStage {
  name: string;
  status: "pending" | "active" | "completed" | "error";
  duration?: number;
}

export interface BatchExportRequest {
  sessionIds: string[];
  format: "json" | "pdf" | "fhir" | "csv";
}

export interface LoginRequest {
  username: string;
  password: string;
  totpCode?: string;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  user: UserProfile;
}

export interface UserProfile {
  id: string;
  username: string;
  name: string;
  role: "clinician" | "admin" | "nurse";
  email?: string;
}
