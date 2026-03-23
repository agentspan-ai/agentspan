import { renderHook, act } from "@testing-library/react";
import { useCredentialAuth } from "../hooks/useCredentialAuth";

const LS_KEY = "agentspan.credential_token";

beforeEach(() => {
  localStorage.clear();
});

describe("useCredentialAuth", () => {
  it("isAuthenticated is false when no token in localStorage", () => {
    const { result } = renderHook(() => useCredentialAuth());
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
  });

  it("isAuthenticated is true when token is present", () => {
    localStorage.setItem(LS_KEY, "tok123");
    const { result } = renderHook(() => useCredentialAuth());
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe("tok123");
  });

  it("setToken stores token and triggers re-render", () => {
    const { result } = renderHook(() => useCredentialAuth());
    act(() => result.current.setToken("newtoken"));
    expect(localStorage.getItem(LS_KEY)).toBe("newtoken");
    expect(result.current.token).toBe("newtoken");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("clearToken removes token and triggers re-render", () => {
    localStorage.setItem(LS_KEY, "tok123");
    const { result } = renderHook(() => useCredentialAuth());
    act(() => result.current.clearToken());
    expect(localStorage.getItem(LS_KEY)).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });
});
