import { Header } from "../components/layout/Header";
import { GlassCard } from "../components/ui/GlassCard";
import { Divider } from "../components/ui/Divider";
import { ThemeSelector } from "../components/settings/ThemeSelector";
import { AudioSettings } from "../components/settings/AudioSettings";
import { ModelSettings } from "../components/settings/ModelSettings";
import { AccessibilitySettings } from "../components/settings/AccessibilitySettings";
import { usePWA } from "../hooks/usePWA";
import { Download } from "lucide-react";

export default function SettingsPage() {
  const { installable, install, isStandalone } = usePWA();

  return (
    <>
      <Header title="Settings" subtitle="Configuration" />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-2xl space-y-6">
          {/* PWA Install */}
          {installable && !isStandalone && (
            <GlassCard glow="violet" className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    Install App
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    Install as a standalone app for the best experience
                  </p>
                </div>
                <button
                  onClick={install}
                  className="flex items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-primary)]/80"
                >
                  <Download size={14} />
                  Install
                </button>
              </div>
            </GlassCard>
          )}

          {/* Appearance */}
          <GlassCard className="p-5">
            <ThemeSelector />
          </GlassCard>

          {/* Audio */}
          <GlassCard className="p-5">
            <AudioSettings />
          </GlassCard>

          {/* Models */}
          <GlassCard className="p-5">
            <ModelSettings />
          </GlassCard>

          {/* Accessibility */}
          <GlassCard className="p-5">
            <AccessibilitySettings />
          </GlassCard>

          {/* Version info */}
          <div className="text-center text-xs text-[var(--text-muted)]">
            Voice Symptom Triage Assistant v2.0.0 · Clinical Glass UI
          </div>
        </div>
      </div>
    </>
  );
}
