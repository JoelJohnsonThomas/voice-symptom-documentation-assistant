import { useState } from "react";
import { Radio, Pause, Play, RotateCcw } from "lucide-react";
import { Header } from "../components/layout/Header";
import { GlassCard } from "../components/ui/GlassCard";
import { Toggle } from "../components/ui/Toggle";
import { StatusDot } from "../components/ui/StatusDot";
import { WaveformVisualizer } from "../components/voice/WaveformVisualizer";
import { ResultsContainer } from "../components/soap/ResultsContainer";

export default function AmbientModePage() {
  const [isListening, setIsListening] = useState(false);
  const [autoDoc, setAutoDoc] = useState(true);
  const [multiSpeaker, setMultiSpeaker] = useState(true);

  return (
    <>
      <Header
        title="Ambient Mode"
        subtitle="Passive clinical documentation"
        actions={
          <StatusDot
            status={isListening ? "recording" : "offline"}
            size="md"
            pulse={isListening}
          />
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Controls */}
          <GlassCard glow={isListening ? "cyan" : undefined} className="p-6">
            <div className="flex flex-col items-center gap-5">
              <div className="flex items-center gap-2">
                <Radio
                  size={18}
                  className={
                    isListening
                      ? "text-[var(--status-error)]"
                      : "text-[var(--text-muted)]"
                  }
                />
                <span className="text-lg font-semibold text-[var(--text-primary)]">
                  {isListening ? "Listening..." : "Ambient Mode"}
                </span>
              </div>

              <WaveformVisualizer
                audioLevel={isListening ? 0.4 : 0}
                isActive={isListening}
                barCount={60}
              />

              <div className="flex gap-3">
                <button
                  onClick={() => setIsListening(!isListening)}
                  className={`flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-medium text-white transition-all ${
                    isListening
                      ? "bg-[var(--status-error)] hover:bg-[var(--status-error)]/80"
                      : "bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] hover:shadow-lg"
                  }`}
                >
                  {isListening ? (
                    <>
                      <Pause size={16} /> Stop
                    </>
                  ) : (
                    <>
                      <Play size={16} /> Start Listening
                    </>
                  )}
                </button>
                {isListening && (
                  <button className="flex items-center gap-2 rounded-lg border border-[var(--border-primary)] px-4 py-2.5 text-sm text-[var(--text-secondary)] hover:bg-white/[0.06]">
                    <RotateCcw size={14} />
                    Reset
                  </button>
                )}
              </div>
            </div>
          </GlassCard>

          {/* Settings */}
          <GlassCard className="p-5">
            <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">
              Ambient Settings
            </h3>
            <div className="space-y-4">
              <Toggle
                label="Auto-documentation"
                checked={autoDoc}
                onChange={setAutoDoc}
              />
              <Toggle
                label="Multi-speaker diarization"
                checked={multiSpeaker}
                onChange={setMultiSpeaker}
              />
            </div>
          </GlassCard>

          {/* Results */}
          <ResultsContainer />
        </div>
      </div>
    </>
  );
}
