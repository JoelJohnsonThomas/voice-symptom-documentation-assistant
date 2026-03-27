export type ThemeName = "glass" | "light" | "neon" | "midnight" | "aurora" | "high-contrast";

export interface ThemeDefinition {
  name: ThemeName;
  label: string;
  description: string;
  previewColors: [string, string, string];
}

export const THEMES: ThemeDefinition[] = [
  {
    name: "glass",
    label: "Clinical Glass",
    description: "Dark navy with violet/indigo accents",
    previewColors: ["#0f111a", "#8b5cf6", "#6366f1"],
  },
  {
    name: "light",
    label: "Clinical Light",
    description: "Clean white with indigo accents",
    previewColors: ["#f8fafc", "#6366f1", "#4f46e5"],
  },
  {
    name: "neon",
    label: "Neon Cyber",
    description: "Dark with electric neon accents",
    previewColors: ["#0a0a0f", "#00ff88", "#ff0080"],
  },
  {
    name: "midnight",
    label: "Midnight Void",
    description: "Deep dark with subtle blues",
    previewColors: ["#070b14", "#1e40af", "#3b82f6"],
  },
  {
    name: "aurora",
    label: "Aurora Dusk",
    description: "Warm dark with gradient accents",
    previewColors: ["#0f0f1a", "#ec4899", "#8b5cf6"],
  },
  {
    name: "high-contrast",
    label: "High Contrast",
    description: "WCAG AAA: pure black/white/yellow",
    previewColors: ["#000000", "#ffff00", "#ffffff"],
  },
];
