import { Brain } from "lucide-react";
import { useState } from "react";
import { Toggle } from "../ui/Toggle";

export function ModelSettings() {
  const [streamingMode, setStreamingMode] = useState(true);
  const [selectedASR, setSelectedASR] = useState("whisper-large-v3");
  const [selectedLLM, setSelectedLLM] = useState("med-palm-2");

  const ASR_OPTIONS = [
    { value: "whisper-large-v3", label: "Whisper Large v3" },
    { value: "whisper-medium", label: "Whisper Medium" },
    { value: "wav2vec2", label: "Wav2Vec2 (Offline)" },
  ];

  const LLM_OPTIONS = [
    { value: "med-palm-2", label: "Med-PaLM 2" },
    { value: "claude-opus", label: "Claude Opus 4.6" },
    { value: "llama-med", label: "LLaMA-Med (Local)" },
  ];

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Brain size={16} className="text-[var(--text-muted)]" />
        <h4 className="text-sm font-medium text-[var(--text-primary)]">
          Model Configuration
        </h4>
      </div>
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs text-[var(--text-muted)]">
            ASR Model
          </label>
          <select
            value={selectedASR}
            onChange={(e) => setSelectedASR(e.target.value)}
            className="w-full rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
          >
            {ASR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-xs text-[var(--text-muted)]">
            LLM Model
          </label>
          <select
            value={selectedLLM}
            onChange={(e) => setSelectedLLM(e.target.value)}
            className="w-full rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
          >
            {LLM_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <Toggle
          label="Streaming mode"
          checked={streamingMode}
          onChange={setStreamingMode}
        />
      </div>
    </div>
  );
}
