import { useState } from "react";
import { Send, CheckCircle, AlertCircle } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Spinner } from "../ui/Spinner";
import type { EHRPushRequest } from "../../types/api";

interface EHRPushModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  onPush: (request: EHRPushRequest) => Promise<void>;
}

const PRESETS = [
  { value: "hapi", label: "HAPI FHIR Server" },
  { value: "epic", label: "Epic FHIR R4" },
  { value: "cerner", label: "Cerner FHIR R4" },
] as const;

export function EHRPushModal({ isOpen, onClose, sessionId, onPush }: EHRPushModalProps) {
  const [preset, setPreset] = useState<"hapi" | "epic" | "cerner">("hapi");
  const [fhirUrl, setFhirUrl] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [status, setStatus] = useState<"idle" | "pushing" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const handlePush = async () => {
    setStatus("pushing");
    try {
      await onPush({ fhirUrl, authToken, sessionId, preset });
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Push failed");
    }
  };

  return (
    <Modal open={isOpen} onClose={onClose} title="Push to EHR">
      <div className="space-y-4">
        {/* Preset */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-[var(--text-muted)]">
            EHR Preset
          </label>
          <div className="flex gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPreset(p.value)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  preset === p.value
                    ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                    : "border-[var(--border-primary)] text-[var(--text-muted)] hover:bg-white/[0.06]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* FHIR URL */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-[var(--text-muted)]">
            FHIR Server URL
          </label>
          <input
            type="url"
            value={fhirUrl}
            onChange={(e) => setFhirUrl(e.target.value)}
            placeholder="https://fhir.example.com/r4"
            className="w-full rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]/50 px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]"
          />
        </div>

        {/* Auth token */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-[var(--text-muted)]">
            Authorization Token
          </label>
          <input
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder="Bearer token..."
            className="w-full rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]/50 px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]"
          />
        </div>

        {/* Status messages */}
        {status === "success" && (
          <div className="flex items-center gap-2 rounded-lg bg-[var(--status-online)]/10 p-3 text-sm text-[var(--status-online)]">
            <CheckCircle size={16} />
            Successfully pushed to EHR
          </div>
        )}
        {status === "error" && (
          <div className="flex items-center gap-2 rounded-lg bg-[var(--status-error)]/10 p-3 text-sm text-[var(--status-error)]">
            <AlertCircle size={16} />
            {errorMsg}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-[var(--border-primary)] px-4 py-2 text-sm text-[var(--text-muted)] hover:bg-white/[0.06]"
          >
            Cancel
          </button>
          <button
            onClick={handlePush}
            disabled={!fhirUrl || status === "pushing"}
            className="flex items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-primary)]/80 disabled:opacity-50"
          >
            {status === "pushing" ? (
              <Spinner size="sm" />
            ) : (
              <Send size={14} />
            )}
            Push to EHR
          </button>
        </div>
      </div>
    </Modal>
  );
}
