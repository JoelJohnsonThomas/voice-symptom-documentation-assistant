/**
 * Service worker bootstrap for the React clinical UI.
 *
 * Uses vite-plugin-pwa's virtual module to register the Workbox-generated SW
 * and surfaces lifecycle events to the React tree via window CustomEvents that
 * PwaUpdatePrompt listens for.
 *
 * NOTE: We intentionally do NOT cache /api or /ws responses — PHI must never
 * be written to disk by the browser. The workbox config in vite.config.ts
 * declares those routes NetworkOnly.
 */
import { registerSW } from "virtual:pwa-register";

export function registerVoxDocSW() {
  const update = registerSW({
    immediate: false,
    onNeedRefresh() {
      window.dispatchEvent(
        new CustomEvent("voxdoc:pwa-need-refresh", {
          detail: { update: async () => update(true) },
        }),
      );
    },
    onOfflineReady() {
      window.dispatchEvent(new CustomEvent("voxdoc:pwa-offline-ready"));
    },
    onRegisterError(error: unknown) {
      // eslint-disable-next-line no-console
      console.error("[PWA] SW registration failed", error);
    },
  });
  return update;
}
