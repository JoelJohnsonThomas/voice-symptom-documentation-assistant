import { useEffect, useRef } from "react";
import { FileText } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { Spinner } from "../ui/Spinner";

interface LiveTranscriptProps {
  transcript: string;
  partialText?: string;
  isListening: boolean;
}

export function LiveTranscript({
  transcript,
  partialText,
  isListening,
}: LiveTranscriptProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript, partialText]);

  return (
    <GlassCard className="flex max-h-48 flex-col p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[var(--text-muted)]">
          <FileText size={14} />
          <span className="text-xs font-semibold uppercase tracking-wider">
            Live Transcript
          </span>
        </div>
        {isListening && <Spinner size="sm" />}
      </div>
      <div className="flex-1 overflow-y-auto text-sm leading-relaxed text-[var(--text-secondary)]">
        {transcript || partialText ? (
          <>
            {transcript && <span>{transcript}</span>}
            {partialText && (
              <span className="text-[var(--accent-primary)]/70">{" "}{partialText}</span>
            )}
          </>
        ) : (
          <span className="italic text-[var(--text-muted)]">
            {isListening
              ? "Waiting for speech..."
              : "Start recording to see transcript"}
          </span>
        )}
        <div ref={endRef} />
      </div>
    </GlassCard>
  );
}
