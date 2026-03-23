import { fetchWithContext, useFetchContext } from "plugins/fetch";
import {
  useMutation,
  useQuery,
  useQueryClient,
  UseQueryResult,
} from "react-query";
import { BindingMeta, CredentialListItem, LoginRequest } from "../types";

// ── credentialFetch ────────────────────────────────────────────────────────────
// Wraps fetchWithContext, optionally injecting Authorization: Bearer header.
// Catches 401 responses and calls onUnauthorized so callers can clear the token.

export async function credentialFetch(
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

export function useListCredentials(
  { token, onUnauthorized }: ApiOptions,
): UseQueryResult<CredentialListItem[]> {
  const ctx = useFetchContext();
  return useQuery<CredentialListItem[]>(
    [ctx.stack, "/credentials"],
    () =>
      credentialFetch(
        "/credentials",
        ctx,
        { headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    { retry: false },
  );
}

export function useListBindings(
  { token, onUnauthorized }: ApiOptions,
): UseQueryResult<BindingMeta[]> {
  const ctx = useFetchContext();
  return useQuery<BindingMeta[]>(
    [ctx.stack, "/credentials/bindings"],
    () =>
      credentialFetch(
        "/credentials/bindings",
        ctx,
        { headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    { retry: false },
  );
}

export function useCreateCredential({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    ({ name, value }: { name: string; value: string }) =>
      credentialFetch(
        "/credentials",
        ctx,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders(token) },
          body: JSON.stringify({ name, value }),
        },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/credentials"]),
    },
  );
}

export function useUpdateCredential({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    ({ name, value }: { name: string; value: string }) =>
      credentialFetch(
        `/credentials/${encodeURIComponent(name)}`,
        ctx,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...authHeaders(token) },
          body: JSON.stringify({ value }),
        },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/credentials"]),
    },
  );
}

export function useDeleteCredential({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    (name: string) =>
      credentialFetch(
        `/credentials/${encodeURIComponent(name)}`,
        ctx,
        { method: "DELETE", headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/credentials"]),
    },
  );
}

export function useCreateBinding({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    ({ logical_key, store_name }: { logical_key: string; store_name: string }) =>
      credentialFetch(
        `/credentials/bindings/${encodeURIComponent(logical_key)}`,
        ctx,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...authHeaders(token) },
          body: JSON.stringify({ store_name }),
        },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/credentials/bindings"]),
    },
  );
}

export function useDeleteBinding({ token, onUnauthorized }: ApiOptions) {
  const ctx = useFetchContext();
  const qc = useQueryClient();
  return useMutation(
    (logical_key: string) =>
      credentialFetch(
        `/credentials/bindings/${encodeURIComponent(logical_key)}`,
        ctx,
        { method: "DELETE", headers: { ...authHeaders(token) } },
        onUnauthorized,
      ),
    {
      onSuccess: () => qc.invalidateQueries([ctx.stack, "/credentials/bindings"]),
    },
  );
}

export function useLogin() {
  const ctx = useFetchContext();
  return useMutation(({ username, password }: LoginRequest) =>
    credentialFetch("/auth/login", ctx, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  );
}
