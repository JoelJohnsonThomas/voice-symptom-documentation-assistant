import { GlassCard } from "../ui/GlassCard";
import { RecordButton } from "./RecordButton";
import { WaveformVisualizer } from "./WaveformVisualizer";
import { DurationDisplay } from "./DurationDisplay";
import { useSessionStore } from "../../stores/sessionStore";

interface VoiceCardProps {
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  disabled?: boolean;
}

export function VoiceCard({ onStart, onStop, onPause, onResume, disabled }: VoiceCardProps) {
  const { isRecording, isPaused, recordingDuration, audioLevel } = useSessionStore();

  return (
    <GlassCard glow={isRecording ? "rose" : "violet"} className="p-6">
      <div className="flex flex-col items-center gap-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Voice Input
        </h3>

        <WaveformVisualizer
          audioLevel={audioLevel}
          isActive={isRecording && !isPaused}
        />

        <DurationDisplay seconds={recordingDuration} isRecording={isRecording} />

        <RecordButton
          isRecording={isRecording}
          isPaused={isPaused}
          onStart={onStart}
          onStop={onStop}
          onPause={onPause}
          onResume={onResume}
          disabled={disabled}
        />

        <p className="text-center text-xs text-[var(--text-muted)]">
          {isRecording
            ? isPaused
              ? "Recording paused"
              : "Listening..."
            : "Click to start recording"}
        </p>
      </div>
    </GlassCard>
  );
}
