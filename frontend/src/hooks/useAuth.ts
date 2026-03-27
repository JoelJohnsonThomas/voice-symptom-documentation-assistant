import { useCallback } from "react";
import { useAuthStore } from "../stores/authStore";
import type { LoginRequest, LoginResponse } from "../types/api";

export function useAuth() {
  const store = useAuthStore();

  const login = useCallback(
    async (credentials: LoginRequest) => {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Login failed" }));
        throw new Error(err.detail);
      }

      const data: LoginResponse = await res.json();
      store.login(data.user, data.accessToken, data.refreshToken);
      return data.user;
    },
    [store]
  );

  const logout = useCallback(() => {
    store.logout();
  }, [store]);

  return {
    user: store.user,
    isAuthenticated: store.isAuthenticated,
    consentGiven: store.consentGiven,
    login,
    logout,
    giveConsent: store.giveConsent,
  };
}
