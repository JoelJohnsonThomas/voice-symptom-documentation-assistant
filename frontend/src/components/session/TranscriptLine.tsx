import { cn } from "@/lib/utils";

interface TranscriptLineProps {
  speaker?: "patient" | "clinician" | "system";
  timestamp?: string;
  text: string;
  highlight?: boolean;
  className?: string;
}

const SPEAKER_STYLES: Record<NonNullable<TranscriptLineProps["speaker"]>, string> = {
  patient: "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/[0.04]",
  clinician: "border-[var(--status-online)]/30 bg-[var(--status-online)]/[0.04]",
  system: "border-[var(--border-primary)] bg-white/[0.02]",
};

const SPEAKER_LABEL: Record<NonNullable<TranscriptLineProps["speaker"]>, string> = {
  patient: "Patient",
  clinician: "Clinician",
  system: "System",
};

export function TranscriptLine({ speaker = "patient", timestamp, text, highlight, className }: TranscriptLineProps) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        SPEAKER_STYLES[speaker],
        highlight && "ring-1 ring-[var(--accent-primary)]/40",
        className,
      )}
    >
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
        <span>{SPEAKER_LABEL[speaker]}</span>
        {timestamp && <span>{new Date(timestamp).toLocaleTimeString()}</span>}
      </div>
      <p className="text-[var(--text-primary)]">{text}</p>
    </div>
  );
}
