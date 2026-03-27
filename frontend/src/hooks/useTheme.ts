import { useEffect } from "react";
import { useThemeStore } from "../stores/themeStore";

export function useTheme() {
  const store = useThemeStore();

  // Sync theme to DOM on mount
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", store.theme);
  }, [store.theme]);

  // Respect prefers-reduced-motion
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) store.setReducedMotion(true);
    const handler = (e: MediaQueryListEvent) => store.setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [store]);

  return store;
}
