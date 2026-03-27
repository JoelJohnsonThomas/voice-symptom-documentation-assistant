import { cn } from "../../lib/utils";

interface DurationDisplayProps {
  seconds: number;
  isRecording: boolean;
  className?: string;
}

export function DurationDisplay({ seconds, isRecording, className }: DurationDisplayProps) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const formatted = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {isRecording && (
        <span className="h-2 w-2 animate-[pulse-glow_1.5s_ease-in-out_infinite] rounded-full bg-[var(--status-error)]" />
      )}
      <span
        className={cn(
          "font-mono text-2xl font-bold tabular-nums",
          isRecording ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]"
        )}
      >
        {formatted}
      </span>
    </div>
  );
}
