import { Volume2 } from "lucide-react";
import { Toggle } from "../ui/Toggle";
import { Slider } from "../ui/Slider";
import { useState } from "react";

export function AudioSettings() {
  const [noiseReduction, setNoiseReduction] = useState(true);
  const [vadSensitivity, setVadSensitivity] = useState(70);
  const [silenceTimeout, setSilenceTimeout] = useState(3);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Volume2 size={16} className="text-[var(--text-muted)]" />
        <h4 className="text-sm font-medium text-[var(--text-primary)]">
          Audio Settings
        </h4>
      </div>
      <div className="space-y-4">
        <Toggle
          label="Noise reduction"
          checked={noiseReduction}
          onChange={setNoiseReduction}
        />
        <Slider
          label="VAD Sensitivity"
          min={0}
          max={100}
          value={vadSensitivity}
          onChange={setVadSensitivity}
          displayValue={`${vadSensitivity}%`}
        />
        <Slider
          label="Silence timeout"
          min={1}
          max={10}
          value={silenceTimeout}
          onChange={setSilenceTimeout}
          displayValue={`${silenceTimeout}s`}
        />
      </div>
    </div>
  );
}
