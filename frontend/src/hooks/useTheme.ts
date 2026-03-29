import { useEffect } from "react";
import { useThemeStore } from "../stores/themeStore";

export function useTheme() {
  const theme = useThemeStore((s) => s.theme);
  // Select the action directly — Zustand actions are stable references
  const setReducedMotion = useThemeStore((s) => s.setReducedMotion);

  // Sync theme to DOM on mount
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  // Respect prefers-reduced-motion — stable deps, no infinite loop
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) setReducedMotion(true);
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [setReducedMotion]);

  return useThemeStore();
}
