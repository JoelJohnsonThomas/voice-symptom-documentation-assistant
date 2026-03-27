import { Mic, Square, Pause, Play } from "lucide-react";
import { cn } from "../../lib/utils";

interface RecordButtonProps {
  isRecording: boolean;
  isPaused: boolean;
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  disabled?: boolean;
}

export function RecordButton({
  isRecording,
  isPaused,
  onStart,
  onStop,
  onPause,
  onResume,
  disabled,
}: RecordButtonProps) {
  return (
    <div className="flex items-center gap-4">
      {/* Main record/stop button */}
      <button
        onClick={isRecording ? onStop : onStart}
        disabled={disabled}
        className={cn(
          "relative flex h-16 w-16 items-center justify-center rounded-full transition-all duration-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-primary)]",
          isRecording
            ? "bg-[var(--status-error)] shadow-lg shadow-[var(--status-error)]/40 hover:bg-[var(--status-error)]/90"
            : "bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] shadow-lg shadow-[var(--accent-primary)]/30 hover:shadow-[var(--accent-primary)]/50",
          disabled && "opacity-50 cursor-not-allowed"
        )}
        aria-label={isRecording ? "Stop recording" : "Start recording"}
      >
        {/* Pulse ring when recording */}
        {isRecording && !isPaused && (
          <span className="absolute inset-0 animate-[pulse-glow_2s_ease-in-out_infinite] rounded-full border-2 border-[var(--status-error)]/50" />
        )}

        {isRecording ? (
          <Square size={24} className="text-white" fill="white" />
        ) : (
          <Mic size={24} className="text-white" />
        )}
      </button>

      {/* Pause/resume button (only during recording) */}
      {isRecording && (
        <button
          onClick={isPaused ? onResume : onPause}
          className="flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] transition-colors hover:bg-white/[0.06]"
          aria-label={isPaused ? "Resume recording" : "Pause recording"}
        >
          {isPaused ? <Play size={16} /> : <Pause size={16} />}
        </button>
      )}
    </div>
  );
}
