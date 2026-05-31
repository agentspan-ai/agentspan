import { fetchWithContext, useFetchContext } from "plugins/fetch";
import {
  useMutation,
  useQuery,
  useQueryClient,
  UseQueryResult,
} from "react-query";
import { SecretListItem, LoginRequest } from "../types";

// ── secretFetch ────────────────────────────────────────────────────────────────
// Wraps fetchWithContext, optionally injecting Authorization: Bearer header.
// Catches 401 responses and calls onUnauthorized so callers can clear the token.

export async function secretFetch(
  path: string,
  context: object,
  options: RequestInit & { headers?: Record<string, string> } = {},
  onUnauthorized?: () => void,
): Promise<any> {
  try {
    return await fetchWithContext(path, context, options);
  } catch (err: any) {
    if (err && typeof err.status === "number" && err.status === 401) {
      onUnauthorized?.();
    }
    throw err;
  }
}

// ── hooks ─────────────────────────────────────────────────────────────────────

interface ApiOptions {
  token: string | null;
  onUnauthorized: () => void;
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Lists via /api/secrets/v2 — richer payload (name + partial + timestamps).
// The v1 POST /api/secrets endpoint returns just names; v2 is the UI-friendly variant.
export function useListSecrets(
  { token, onUnauthorized }: ApiOptions,
): UseQueryResult<SecretListItem[]> {
  const ctx = useFetchContext();
  return useQuery<SecretListItem[]>(
    [ctx.stack, "/secrets/v2"],
    () =>
      secretFetch(
        "/secrets/v2",
        ctx,
        { headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    { retry: false },
  );
}

// Upsert via PUT /api/secrets/{key} — body is the raw plaintext value (Conductor parity).
export function useUpsertSecret({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    ({ name, value }: { name: string; value: string }) =>
      secretFetch(
        `/secrets/${encodeURIComponent(name)}`,
        ctx,
        {
          method: "PUT",
          headers: { "Content-Type": "text/plain", ...authHeaders(token) },
          body: value,
        },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/secrets/v2"]),
    },
  );
}

export function useDeleteSecret({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    (name: string) =>
      secretFetch(
        `/secrets/${encodeURIComponent(name)}`,
        ctx,
        { method: "DELETE", headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/secrets/v2"]),
    },
  );
}

export function useLogin() {
  const ctx = useFetchContext();
  return useMutation(({ username, password }: LoginRequest) =>
    secretFetch("/auth/login", ctx, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  );
}
