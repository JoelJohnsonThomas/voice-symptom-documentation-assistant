import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ThemeName } from "../types/theme";

interface ThemeState {
  theme: ThemeName;
  soundEnabled: boolean;
  particlesEnabled: boolean;
  reducedMotion: boolean;
  setTheme: (theme: ThemeName) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setParticlesEnabled: (enabled: boolean) => void;
  setReducedMotion: (enabled: boolean) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "glass",
      soundEnabled: true,
      particlesEnabled: true,
      reducedMotion: false,
      setTheme: (theme) => {
        document.documentElement.setAttribute("data-theme", theme);
        set({ theme });
      },
      setSoundEnabled: (soundEnabled) => set({ soundEnabled }),
      setParticlesEnabled: (particlesEnabled) => set({ particlesEnabled }),
      setReducedMotion: (reducedMotion) => set({ reducedMotion }),
    }),
    {
      name: "vst-theme",
      onRehydrateStorage: () => (state) => {
        if (state?.theme) {
          document.documentElement.setAttribute("data-theme", state.theme);
        }
      },
    }
  )
);
