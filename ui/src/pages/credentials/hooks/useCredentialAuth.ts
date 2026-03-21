import { useState, useCallback } from "react";

const LS_KEY = "agentspan.credential_token";

export interface CredentialAuth {
  token: string | null;
  isAuthenticated: boolean;
  setToken: (token: string) => void;
  clearToken: () => void;
}

export function useCredentialAuth(): CredentialAuth {
  const [token, setTokenState] = useState<string | null>(
    () => localStorage.getItem(LS_KEY),
  );

  const setToken = useCallback((newToken: string) => {
    localStorage.setItem(LS_KEY, newToken);
    setTokenState(newToken);
  }, []);

  const clearToken = useCallback(() => {
    localStorage.removeItem(LS_KEY);
    setTokenState(null);
  }, []);

  return {
    token,
    isAuthenticated: !!token, // !!token guards against empty-string tokens
    setToken,
    clearToken,
  };
}
