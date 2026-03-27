import { Accessibility } from "lucide-react";
import { Toggle } from "../ui/Toggle";
import { useThemeStore } from "../../stores/themeStore";

export function AccessibilitySettings() {
  const {
    reducedMotion,
    setReducedMotion,
    soundEnabled,
    setSoundEnabled,
    particlesEnabled,
    setParticlesEnabled,
  } = useThemeStore();

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Accessibility size={16} className="text-[var(--text-muted)]" />
        <h4 className="text-sm font-medium text-[var(--text-primary)]">
          Accessibility
        </h4>
      </div>
      <div className="space-y-4">
        <Toggle
          label="Reduced motion"
          checked={reducedMotion}
          onChange={setReducedMotion}
        />
        <Toggle
          label="Sound effects"
          checked={soundEnabled}
          onChange={setSoundEnabled}
        />
        <Toggle
          label="Particle effects"
          checked={particlesEnabled}
          onChange={setParticlesEnabled}
        />
      </div>
    </div>
  );
}
