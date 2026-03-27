import { Shield, CheckCircle } from "lucide-react";
import { Modal } from "../ui/Modal";
import { useAuth } from "../../hooks/useAuth";

interface ConsentDialogProps {
  isOpen: boolean;
}

export function ConsentDialog({ isOpen }: ConsentDialogProps) {
  const { giveConsent } = useAuth();

  return (
    <Modal open={isOpen} onClose={() => {}} title="Consent & Disclaimer">
      <div className="space-y-4">
        <div className="flex items-start gap-3 rounded-lg bg-[var(--accent-primary)]/5 p-4">
          <Shield size={20} className="mt-0.5 shrink-0 text-[var(--accent-primary)]" />
          <div className="text-sm text-[var(--text-secondary)]">
            <p className="mb-2 font-medium text-[var(--text-primary)]">
              Clinical Use Agreement
            </p>
            <ul className="space-y-1.5 text-xs">
              <li>
                This system provides AI-assisted clinical documentation as a
                decision support tool.
              </li>
              <li>
                All AI-generated content must be reviewed by a licensed
                clinician before clinical use.
              </li>
              <li>
                Audio recordings and transcripts may be processed by AI models
                for documentation purposes.
              </li>
              <li>
                All data is encrypted and handled in compliance with HIPAA
                regulations.
              </li>
              <li>
                Session data is retained per institutional policy and can be
                exported or deleted upon request.
              </li>
            </ul>
          </div>
        </div>

        <button
          onClick={giveConsent}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] py-2.5 text-sm font-semibold text-white"
        >
          <CheckCircle size={16} />
          I Understand & Consent
        </button>
      </div>
    </Modal>
  );
}
