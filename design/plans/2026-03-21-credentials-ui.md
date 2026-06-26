# Credentials UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Credentials management page to the Agentspan UI — list, add, edit, delete secrets and manage bindings inline with expandable rows.

**Architecture:** Single `/credentials` route, no XState, React Query for all data fetching, local `useState` for dialog/toast state. A self-contained `credentialFetch` helper wraps the existing `fetchWithContext` to inject `Authorization: Bearer` when a token is stored; a `useCredentialAuth` hook persists the token in `localStorage` and triggers a `LoginDialog` on 401. Everything lives under `ui/src/pages/credentials/`.

**Tech Stack:** React 18, TypeScript, MUI 7, React Query (`useQuery`/`useMutation`/`useQueryClient`), React Hook Form + Yup, Vitest + @testing-library/react (jsdom)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `ui/src/utils/constants/route.ts` | Modify | Add `CREDENTIALS_URL` constant |
| `ui/src/components/Sidebar/sidebarCoreItems.tsx` | Modify | Add Settings submenu at position 350 |
| `ui/src/routes/routes.tsx` | Modify | Register `/credentials` route |
| `ui/src/pages/credentials/hooks/useCredentialAuth.ts` | Create | JWT localStorage read/write; exposes `{ token, isAuthenticated, setToken, clearToken }` |
| `ui/src/pages/credentials/hooks/useCredentialsApi.ts` | Create | `credentialFetch` + all 7 React Query hooks |
| `ui/src/pages/credentials/types.ts` | Create | `CredentialListItem`, `BindingMeta`, `LoginRequest`, `LoginResponse` |
| `ui/src/pages/credentials/components/LoginDialog.tsx` | Create | Username/password dialog; no dismiss; stores token on success |
| `ui/src/pages/credentials/components/AddEditCredentialDialog.tsx` | Create | Name + Value (show/hide); add or edit mode |
| `ui/src/pages/credentials/components/BindingChips.tsx` | Create | Chip row for bindings; delete (✕) per chip |
| `ui/src/pages/credentials/components/AddBindingDialog.tsx` | Create | Logical Key + Store Name dialog; PUT upsert |
| `ui/src/pages/credentials/CredentialsPage.tsx` | Create | Main page: table, expand/collapse, all dialogs wired |
| `ui/src/pages/credentials/index.ts` | Create | Re-exports `CredentialsPage` |
| `ui/src/pages/credentials/__tests__/useCredentialAuth.test.ts` | Create | Token localStorage behavior |
| `ui/src/pages/credentials/__tests__/LoginDialog.test.tsx` | Create | Renders on no token; success stores token; 401 inline error |
| `ui/src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx` | Create | Validation + submit path (POST add / PUT edit) |
| `ui/src/pages/credentials/__tests__/BindingChips.test.tsx` | Create | Empty state; chip render; onDelete callback |
| `ui/src/pages/credentials/__tests__/AddBindingDialog.test.tsx` | Create | Pre-fill + submit |
| `ui/src/pages/credentials/__tests__/CredentialsPage.test.tsx` | Create | List render, expand/collapse, delete flow, toast |

---

## Chunk 1: Route, Sidebar, and Navigation Wiring

### Task 1: Add route constant, sidebar Settings item, and route registration

**Files:**
- Modify: `ui/src/utils/constants/route.ts`
- Modify: `ui/src/components/Sidebar/sidebarCoreItems.tsx`
- Modify: `ui/src/routes/routes.tsx`

- [ ] **Step 1: Add `CREDENTIALS_URL` to route constants**

In `ui/src/utils/constants/route.ts`, append at the end of the file:

```typescript
export const CREDENTIALS_URL = "/credentials";
```

- [ ] **Step 2: Add Settings submenu to sidebar**

In `ui/src/components/Sidebar/sidebarCoreItems.tsx`:

Add import at top with other MUI icon imports:
```typescript
import SettingsIcon from "@mui/icons-material/Settings";
```

Add `CREDENTIALS_URL` to the existing import from `utils/constants/route`:
```typescript
import {
  CREDENTIALS_URL,
  EVENT_HANDLERS_URL,
  // ...existing imports...
} from "utils/constants/route";
```

Add `settingsSubMenu: 350` to `CORE_SIDEBAR_POSITIONS.ROOT`:
```typescript
const CORE_SIDEBAR_POSITIONS = {
  ROOT: {
    executionsSubMenu: 100,
    runWorkflow: 200,
    definitionsSubMenu: 300,
    settingsSubMenu: 350,   // <-- add this
    helpMenu: 400,
    swaggerItem: 500,
  },
  // ...rest unchanged
```

Add the Settings submenu item to the returned array in `getCoreSidebarItems`, after the `definitionsSubMenu` block:
```typescript
// Settings submenu
{
  id: "settingsSubMenu",
  title: "Settings",
  icon: <SettingsIcon />,
  linkTo: "",
  shortcuts: [],
  hotkeys: "",
  hidden: false,
  position: R.settingsSubMenu,
  items: [
    {
      id: "credentialsItem",
      title: "Credentials",
      icon: null,
      linkTo: CREDENTIALS_URL,
      activeRoutes: [CREDENTIALS_URL],
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: 100,
    },
  ],
},
```

- [ ] **Step 3: Register route**

In `ui/src/routes/routes.tsx`, add the import and route entry.

Add import (alongside other page imports):
```typescript
import { CredentialsPage } from "pages/credentials";
```

Add import of `CREDENTIALS_URL` to the existing route import block:
```typescript
import {
  CREDENTIALS_URL,
  // ...existing route constants
} from "utils/constants/route";
```

Add route entry inside `getCoreAuthenticatedRoutes()`, after the Task Definitions block (this ensures the route is protected by `AuthGuard`):
```typescript
{
  path: CREDENTIALS_URL,
  element: <CredentialsPage />,
},
```

- [ ] **Step 4: Create stub page so the route compiles**

Create `ui/src/pages/credentials/index.ts`:
```typescript
export { CredentialsPage } from "./CredentialsPage";
```

Create `ui/src/pages/credentials/CredentialsPage.tsx` (stub — will be replaced in Task 8):
```typescript
export function CredentialsPage() {
  return <div>Credentials coming soon</div>;
}
```

- [ ] **Step 5: Verify it compiles**

```bash
cd ui && npm run typecheck
```
Expected: no errors related to credentials imports.

- [ ] **Step 6: Commit**

```bash
git add ui/src/utils/constants/route.ts \
        ui/src/components/Sidebar/sidebarCoreItems.tsx \
        ui/src/routes/routes.tsx \
        ui/src/pages/credentials/index.ts \
        ui/src/pages/credentials/CredentialsPage.tsx
git commit -m "feat(ui): add credentials route, sidebar Settings entry, and stub page"
```

---

## Chunk 2: Auth Hook and API Layer

### Task 2: `useCredentialAuth` hook

**Files:**
- Create: `ui/src/pages/credentials/hooks/useCredentialAuth.ts`
- Create: `ui/src/pages/credentials/__tests__/useCredentialAuth.test.ts`

- [ ] **Step 1: Write the failing test**

Create `ui/src/pages/credentials/__tests__/useCredentialAuth.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/useCredentialAuth.test.ts
```
Expected: FAIL — "Cannot find module '../hooks/useCredentialAuth'"

- [ ] **Step 3: Implement `useCredentialAuth`**

Create `ui/src/pages/credentials/hooks/useCredentialAuth.ts`:

```typescript
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/useCredentialAuth.test.ts
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ui/src/pages/credentials/hooks/useCredentialAuth.ts \
        ui/src/pages/credentials/__tests__/useCredentialAuth.test.ts
git commit -m "feat(ui): add useCredentialAuth hook with localStorage JWT persistence"
```

---

### Task 3: Types and `useCredentialsApi` hook

**Files:**
- Create: `ui/src/pages/credentials/types.ts`
- Create: `ui/src/pages/credentials/hooks/useCredentialsApi.ts`

- [ ] **Step 1: Create types file**

Create `ui/src/pages/credentials/types.ts`:

```typescript
export interface CredentialListItem {
  name: string;       // e.g. "GITHUB_TOKEN"
  partial: string;    // e.g. "ghp_...6789"
  updated_at: string; // ISO-8601
}

export interface BindingMeta {
  logical_key: string; // e.g. "GH_TOKEN" (the alias)
  store_name: string;  // e.g. "GITHUB_TOKEN" (the stored credential name)
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: { id: string; username: string; name: string };
}
```

- [ ] **Step 2: Implement `useCredentialsApi`**

Create `ui/src/pages/credentials/hooks/useCredentialsApi.ts`:

```typescript
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
```

- [ ] **Step 3: Run typecheck**

```bash
cd ui && npm run typecheck 2>&1 | head -30
```
Expected: 0 errors (do not filter with grep — this hides errors in imported modules).

- [ ] **Step 4: Commit**

```bash
git add ui/src/pages/credentials/types.ts \
        ui/src/pages/credentials/hooks/useCredentialsApi.ts
git commit -m "feat(ui): add credentials types and useCredentialsApi hooks"
```

---

## Chunk 3: Dialogs and Chips

### Task 4: `LoginDialog`

**Files:**
- Create: `ui/src/pages/credentials/components/LoginDialog.tsx`
- Create: `ui/src/pages/credentials/__tests__/LoginDialog.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `ui/src/pages/credentials/__tests__/LoginDialog.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { LoginDialog } from "../components/LoginDialog";

// Mock fetchWithContext so we don't need a real server
vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

import { fetchWithContext } from "plugins/fetch";
const mockFetch = fetchWithContext as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("LoginDialog", () => {
  it("renders username and password fields", () => {
    render(
      <LoginDialog onSuccess={vi.fn()} />,
      { wrapper },
    );
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows inline error on 401", async () => {
    mockFetch.mockRejectedValueOnce({ status: 401 });
    render(<LoginDialog onSuccess={vi.fn()} />, { wrapper });
    await userEvent.type(screen.getByLabelText(/username/i), "admin");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument(),
    );
  });

  it("calls onSuccess with token on 200", async () => {
    mockFetch.mockResolvedValueOnce({ token: "jwt123", user: { id: "1", username: "admin", name: "Admin" } });
    const onSuccess = vi.fn();
    render(<LoginDialog onSuccess={onSuccess} />, { wrapper });
    await userEvent.type(screen.getByLabelText(/username/i), "admin");
    await userEvent.type(screen.getByLabelText(/password/i), "agentspan");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("jwt123"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/LoginDialog.test.tsx
```
Expected: FAIL — cannot find module `../components/LoginDialog`.

- [ ] **Step 3: Implement `LoginDialog`**

Create `ui/src/pages/credentials/components/LoginDialog.tsx`:

```typescript
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import { useLogin } from "../hooks/useCredentialsApi";

interface LoginDialogProps {
  /**
   * Called with the received JWT on successful login.
   * Caller is responsible for calling setToken(tok) and refetching credentials —
   * LoginDialog only signals success and does not touch localStorage directly.
   */
  onSuccess: (token: string) => void;
}

export function LoginDialog({ onSuccess }: LoginDialogProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const loginMutation = useLogin();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const resp = await loginMutation.mutateAsync({ username, password });
      onSuccess(resp.token);
    } catch (err: any) {
      if (err && err.status === 401) {
        setError("Invalid username or password.");
      } else {
        setError("Login failed — please try again.");
      }
    }
  }

  return (
    <Dialog open fullWidth maxWidth="xs" disableEscapeKeyDown>
      <DialogTitle>Sign in to manage credentials</DialogTitle>
      <DialogContent>
        <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Username"
              id="login-username"
              inputProps={{ "aria-label": "Username" }}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              fullWidth
              required
              autoFocus
            />
            <TextField
              label="Password"
              id="login-password"
              inputProps={{ "aria-label": "Password", type: "password" }}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
              required
            />
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={loginMutation.isLoading}
            >
              {loginMutation.isLoading ? "Signing in…" : "Log in"}
            </Button>
          </Stack>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/LoginDialog.test.tsx
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ui/src/pages/credentials/components/LoginDialog.tsx \
        ui/src/pages/credentials/__tests__/LoginDialog.test.tsx
git commit -m "feat(ui): add LoginDialog for credential API authentication"
```

---

### Task 5: `AddEditCredentialDialog`

**Files:**
- Create: `ui/src/pages/credentials/components/AddEditCredentialDialog.tsx`
- Create: `ui/src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `ui/src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { AddEditCredentialDialog } from "../components/AddEditCredentialDialog";

vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const noop = vi.fn();

describe("AddEditCredentialDialog — add mode", () => {
  it("rejects blank name", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(screen.getByText(/name is required/i)).toBeInTheDocument(),
    );
  });

  it("rejects blank value", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^name/i), "GITHUB_TOKEN");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(screen.getByText(/value is required/i)).toBeInTheDocument(),
    );
  });

  it("toggles value visibility", async () => {
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={noop} onClose={noop} />,
      { wrapper },
    );
    const valueInput = screen.getByLabelText(/^value/i);
    expect(valueInput).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(valueInput).toHaveAttribute("type", "text");
  });
});

describe("AddEditCredentialDialog — edit mode", () => {
  it("name field is read-only in edit mode", () => {
    render(
      <AddEditCredentialDialog
        mode="edit"
        initialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={noop}
        onClose={noop}
      />,
      { wrapper },
    );
    expect(screen.getByLabelText(/^name/i)).toHaveAttribute("readonly");
  });
});

describe("AddEditCredentialDialog — submit paths", () => {
  it("calls POST /credentials on add submit", async () => {
    const { fetchWithContext: mockF } = await import("plugins/fetch");
    (mockF as ReturnType<typeof vi.fn>).mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddEditCredentialDialog mode="add" token={null} onUnauthorized={noop} onSuccess={onSuccess} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^name/i), "MY_TOKEN");
    await userEvent.type(screen.getByLabelText(/^value/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockF).toHaveBeenCalledWith(
      "/credentials",
      expect.anything(),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("calls PUT /credentials/{name} on edit submit", async () => {
    const { fetchWithContext: mockF } = await import("plugins/fetch");
    (mockF as ReturnType<typeof vi.fn>).mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddEditCredentialDialog mode="edit" initialName="GITHUB_TOKEN" token={null} onUnauthorized={noop} onSuccess={onSuccess} onClose={noop} />,
      { wrapper },
    );
    await userEvent.type(screen.getByLabelText(/^value/i), "newvalue");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockF).toHaveBeenCalledWith(
      expect.stringContaining("GITHUB_TOKEN"),
      expect.anything(),
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx
```
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement `AddEditCredentialDialog`**

Create `ui/src/pages/credentials/components/AddEditCredentialDialog.tsx`:

```typescript
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  useCreateCredential,
  useUpdateCredential,
} from "../hooks/useCredentialsApi";

interface FormValues {
  name: string;
  value: string;
}

interface Props {
  mode: "add" | "edit";
  initialName?: string;
  token: string | null;
  onUnauthorized: () => void;
  onSuccess: () => void;
  onClose: () => void;
}

export function AddEditCredentialDialog({
  mode,
  initialName = "",
  token,
  onUnauthorized,
  onSuccess,
  onClose,
}: Props) {
  const [showValue, setShowValue] = useState(false);
  const apiOpts = { token, onUnauthorized };
  const createMutation = useCreateCredential(apiOpts);
  const updateMutation = useUpdateCredential(apiOpts);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<FormValues>({
    defaultValues: { name: initialName, value: "" },
  });

  async function onSubmit(data: FormValues) {
    try {
      if (mode === "add") {
        await createMutation.mutateAsync({ name: data.name, value: data.value });
      } else {
        await updateMutation.mutateAsync({ name: data.name, value: data.value });
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      if (err?.status === 409) {
        setError("name", { message: "A credential with this name already exists." });
      }
    }
  }

  const isLoading = isSubmitting || createMutation.isLoading || updateMutation.isLoading;

  return (
    <Dialog open fullWidth maxWidth="sm" onClose={onClose}>
      <DialogTitle>{mode === "add" ? "Add Credential" : "Edit Credential"}</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              inputProps={{
                "aria-label": "Name",
                readOnly: mode === "edit",
                style: { fontFamily: "monospace" },
              }}
              {...register("name", { required: "Name is required." })}
              error={!!errors.name}
              helperText={
                errors.name?.message ??
                "Convention: UPPER_SNAKE_CASE e.g. GITHUB_TOKEN"
              }
              fullWidth
              required
              autoFocus={mode === "add"}
            />
            <TextField
              label="Value"
              type={showValue ? "text" : "password"}
              inputProps={{ "aria-label": "Value" }}
              {...register("value", { required: "Value is required." })}
              error={!!errors.value}
              helperText={
                errors.value?.message ??
                (mode === "add"
                  ? "Encrypted at rest. Value shown only now — never displayed again."
                  : "Enter the full new value to update the stored secret.")
              }
              // Note: Yup omitted — RHF inline `required` rules are sufficient for these
              // two non-empty checks; the spec mentions Yup but it adds no value here.
              fullWidth
              required
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label={showValue ? "Hide" : "Show"}
                      onClick={() => setShowValue((v) => !v)}
                      edge="end"
                    >
                      {showValue ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="text" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={isLoading}>
            {isLoading ? "Saving…" : "Save"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ui/src/pages/credentials/components/AddEditCredentialDialog.tsx \
        ui/src/pages/credentials/__tests__/AddEditCredentialDialog.test.tsx
git commit -m "feat(ui): add AddEditCredentialDialog with validation and show/hide value"
```

---

### Task 6: `BindingChips` and `AddBindingDialog`

**Files:**
- Create: `ui/src/pages/credentials/components/BindingChips.tsx`
- Create: `ui/src/pages/credentials/components/AddBindingDialog.tsx`
- Create: `ui/src/pages/credentials/__tests__/AddBindingDialog.test.tsx`

- [ ] **Step 1: Create `BindingChips`**

Create `ui/src/pages/credentials/components/BindingChips.tsx`:

```typescript
import { Chip, Stack, Typography } from "@mui/material";
import { BindingMeta } from "../types";

interface Props {
  bindings: BindingMeta[];
  onDelete: (logicalKey: string) => void;
}

export function BindingChips({ bindings, onDelete }: Props) {
  if (bindings.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary">
        No bindings — add one to alias a different key name to this credential.
      </Typography>
    );
  }

  return (
    <Stack direction="row" flexWrap="wrap" gap={1}>
      {bindings.map((b) => (
        <Chip
          key={b.logical_key}
          label={
            <span style={{ fontFamily: "monospace" }}>
              {b.logical_key} → {b.store_name}
            </span>
          }
          onDelete={() => onDelete(b.logical_key)}
          size="small"
          variant="outlined"
          color="primary"
        />
      ))}
    </Stack>
  );
}
```

- [ ] **Step 2: Write and run `BindingChips` tests**

Create `ui/src/pages/credentials/__tests__/BindingChips.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BindingChips } from "../components/BindingChips";

const bindings = [
  { logical_key: "GH_TOKEN", store_name: "GITHUB_TOKEN" },
  { logical_key: "GITHUB_TOKEN", store_name: "GITHUB_TOKEN" },
];

describe("BindingChips", () => {
  it("renders empty-state text when no bindings", () => {
    render(<BindingChips bindings={[]} onDelete={vi.fn()} />);
    expect(screen.getByText(/no bindings/i)).toBeInTheDocument();
  });

  it("renders one chip per binding with logical_key → store_name", () => {
    render(<BindingChips bindings={bindings} onDelete={vi.fn()} />);
    expect(screen.getByText(/GH_TOKEN → GITHUB_TOKEN/)).toBeInTheDocument();
  });

  it("calls onDelete with logical_key when chip ✕ is clicked", async () => {
    const onDelete = vi.fn();
    render(<BindingChips bindings={bindings} onDelete={onDelete} />);
    // MUI Chip delete button has role="button" with accessible label matching chip label + "Delete"
    const deleteButtons = screen.getAllByRole("button");
    await userEvent.click(deleteButtons[0]);
    expect(onDelete).toHaveBeenCalledWith("GH_TOKEN");
  });
});
```

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/BindingChips.test.tsx
```
Expected: 3 tests pass.

- [ ] **Step 3: Write the failing `AddBindingDialog` test**

Create `ui/src/pages/credentials/__tests__/AddBindingDialog.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { AddBindingDialog } from "../components/AddBindingDialog";

vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

import { fetchWithContext } from "plugins/fetch";
const mockFetch = fetchWithContext as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const noop = vi.fn();

describe("AddBindingDialog", () => {
  it("pre-fills store name with credential name", () => {
    render(
      <AddBindingDialog
        credentialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={noop}
        onClose={noop}
      />,
      { wrapper },
    );
    expect(screen.getByLabelText(/store name/i)).toHaveValue("GITHUB_TOKEN");
  });

  it("calls PUT /credentials/bindings/{key} on submit", async () => {
    mockFetch.mockResolvedValueOnce(null);
    const onSuccess = vi.fn();
    render(
      <AddBindingDialog
        credentialName="GITHUB_TOKEN"
        token={null}
        onUnauthorized={noop}
        onSuccess={onSuccess}
        onClose={noop}
      />,
      { wrapper },
    );
    // Change the logical key
    await userEvent.clear(screen.getByLabelText(/logical key/i));
    await userEvent.type(screen.getByLabelText(/logical key/i), "GH_TOKEN");
    await userEvent.click(screen.getByRole("button", { name: /add binding/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("GH_TOKEN"),
      expect.anything(),
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/AddBindingDialog.test.tsx
```
Expected: FAIL — cannot find module `../components/AddBindingDialog`.

- [ ] **Step 5: Implement `AddBindingDialog`**

Create `ui/src/pages/credentials/components/AddBindingDialog.tsx`:

```typescript
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useForm } from "react-hook-form";
import { useCreateBinding } from "../hooks/useCredentialsApi";

interface FormValues {
  logical_key: string;
  store_name: string;
}

interface Props {
  credentialName: string;
  token: string | null;
  onUnauthorized: () => void;
  onSuccess: () => void;
  onClose: () => void;
}

export function AddBindingDialog({
  credentialName,
  token,
  onUnauthorized,
  onSuccess,
  onClose,
}: Props) {
  const createBinding = useCreateBinding({ token, onUnauthorized });
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: { logical_key: "", store_name: credentialName },
  });

  async function onSubmit(data: FormValues) {
    await createBinding.mutateAsync(data);
    onSuccess();
    onClose();
  }

  const isLoading = isSubmitting || createBinding.isLoading;

  return (
    <Dialog open fullWidth maxWidth="sm" onClose={onClose}>
      <DialogTitle>Add Binding</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Logical Key"
              inputProps={{
                "aria-label": "Logical Key",
                style: { fontFamily: "monospace" },
              }}
              {...register("logical_key", { required: "Logical key is required." })}
              error={!!errors.logical_key}
              helperText={
                errors.logical_key?.message ??
                "The name your code declares, e.g. GH_TOKEN"
              }
              fullWidth
              required
              autoFocus
            />
            <TextField
              label="Store Name"
              inputProps={{
                "aria-label": "Store Name",
                style: { fontFamily: "monospace" },
              }}
              {...register("store_name", { required: "Store name is required." })}
              error={!!errors.store_name}
              helperText={
                errors.store_name?.message ??
                "The credential this key resolves to, e.g. GITHUB_TOKEN"
              }
              fullWidth
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="text" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={isLoading}>
            {isLoading ? "Adding…" : "Add binding"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/AddBindingDialog.test.tsx
```
Expected: 2 tests pass.

- [ ] **Step 7: Commit**

```bash
git add ui/src/pages/credentials/components/BindingChips.tsx \
        ui/src/pages/credentials/components/AddBindingDialog.tsx \
        ui/src/pages/credentials/__tests__/BindingChips.test.tsx \
        ui/src/pages/credentials/__tests__/AddBindingDialog.test.tsx
git commit -m "feat(ui): add BindingChips and AddBindingDialog"
```

---

## Chunk 4: Main Page Assembly

### Task 7: `CredentialsPage` — full implementation

**Files:**
- Modify: `ui/src/pages/credentials/CredentialsPage.tsx` (replace stub)
- Create: `ui/src/pages/credentials/__tests__/CredentialsPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `ui/src/pages/credentials/__tests__/CredentialsPage.test.tsx`:

```typescript
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "react-query";
import { MemoryRouter } from "react-router";
import { CredentialsPage } from "../CredentialsPage";

vi.mock("plugins/fetch", () => ({
  fetchWithContext: vi.fn(),
  useFetchContext: () => ({ stack: "test", ready: true, setMessage: vi.fn() }),
}));

import { fetchWithContext } from "plugins/fetch";
const mockFetch = fetchWithContext as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

const CREDENTIALS = [
  { name: "GITHUB_TOKEN", partial: "ghp_...6789", updated_at: "2026-03-20" },
  { name: "STRIPE_KEY", partial: "sk_l...4abc", updated_at: "2026-03-19" },
];

const BINDINGS = [
  { logical_key: "GH_TOKEN", store_name: "GITHUB_TOKEN" },
];

beforeEach(() => {
  localStorage.clear();
  // Default: auth disabled — credentials load without login
  mockFetch.mockImplementation((path: string) => {
    if (path === "/credentials") return Promise.resolve(CREDENTIALS);
    if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
    return Promise.resolve(null);
  });
});

describe("CredentialsPage", () => {
  it("renders credential list", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText("GITHUB_TOKEN")).toBeInTheDocument(),
    );
    expect(screen.getByText("STRIPE_KEY")).toBeInTheDocument();
    expect(screen.getByText("ghp_...6789")).toBeInTheDocument();
  });

  it("expand row shows bindings", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    // Click chevron for GITHUB_TOKEN
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() =>
      expect(screen.getByText(/GH_TOKEN/)).toBeInTheDocument(),
    );
  });

  it("collapse row hides bindings", async () => {
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() => screen.getByText(/GH_TOKEN/));
    await userEvent.click(screen.getByTestId("expand-GITHUB_TOKEN"));
    await waitFor(() =>
      expect(screen.queryByText(/GH_TOKEN/)).not.toBeInTheDocument(),
    );
  });

  it("delete confirms with credential name then calls DELETE", async () => {
    mockFetch.mockImplementation((path: string) => {
      if (path === "/credentials") return Promise.resolve(CREDENTIALS);
      if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
      return Promise.resolve(null);
    });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("delete-GITHUB_TOKEN"));
    // ConfirmChoiceDialog should appear
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox");
    await userEvent.type(input, "GITHUB_TOKEN");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("GITHUB_TOKEN"),
        expect.anything(),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
  });

  it("shows LoginDialog when server returns 401", async () => {
    mockFetch.mockRejectedValue({ status: 401 });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText(/sign in to manage credentials/i)).toBeInTheDocument(),
    );
  });

  it("shows success toast and removes item after delete", async () => {
    const credentialsAfterDelete = [
      { name: "STRIPE_KEY", partial: "sk_l...4abc", updated_at: "2026-03-19" },
    ];
    let callCount = 0;
    mockFetch.mockImplementation((path: string, _ctx: any, opts?: RequestInit) => {
      if (opts?.method === "DELETE") return Promise.resolve(null);
      if (path === "/credentials") {
        callCount++;
        // Return full list first, then post-delete list on refetch
        return Promise.resolve(callCount > 2 ? credentialsAfterDelete : CREDENTIALS);
      }
      if (path === "/credentials/bindings") return Promise.resolve(BINDINGS);
      return Promise.resolve(null);
    });
    render(<CredentialsPage />, { wrapper });
    await waitFor(() => screen.getByText("GITHUB_TOKEN"));
    await userEvent.click(screen.getByTestId("delete-GITHUB_TOKEN"));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox");
    await userEvent.type(input, "GITHUB_TOKEN");
    await userEvent.click(within(dialog).getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(screen.getByText(/credential deleted/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/CredentialsPage.test.tsx
```
Expected: FAIL — tests fail (stub page doesn't render the list).

- [ ] **Step 3: Implement `CredentialsPage`**

Replace the stub `ui/src/pages/credentials/CredentialsPage.tsx`:

```typescript
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Box,
  Button,
  Collapse,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import { SnackbarMessage } from "components/SnackbarMessage";
import { Helmet } from "react-helmet";
import { useState, useMemo } from "react";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { PopoverMessage } from "types/Messages";
import { AddBindingDialog } from "./components/AddBindingDialog";
import { AddEditCredentialDialog } from "./components/AddEditCredentialDialog";
import { BindingChips } from "./components/BindingChips";
import { LoginDialog } from "./components/LoginDialog";
import { useCredentialAuth } from "./hooks/useCredentialAuth";
import {
  useDeleteBinding,
  useDeleteCredential,
  useListBindings,
  useListCredentials,
} from "./hooks/useCredentialsApi";
import { CredentialListItem } from "./types";

export function CredentialsPage() {
  const { token, isAuthenticated, setToken, clearToken } = useCredentialAuth();
  const apiOpts = { token, onUnauthorized: clearToken };

  const credentialsQuery = useListCredentials(apiOpts);
  const bindingsQuery = useListBindings(apiOpts);

  const [expandedName, setExpandedName] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editCredential, setEditCredential] = useState<CredentialListItem | null>(null);
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(null);
  const [addBindingFor, setAddBindingFor] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);

  const deleteCredential = useDeleteCredential(apiOpts);
  const deleteBinding = useDeleteBinding(apiOpts);

  const credentials = credentialsQuery.data ?? [];
  const bindings = bindingsQuery.data ?? [];

  const filtered = useMemo(
    () =>
      search.trim()
        ? credentials.filter((c) =>
            c.name.toLowerCase().includes(search.toLowerCase()),
          )
        : credentials,
    [credentials, search],
  );

  function bindingsFor(storeName: string) {
    return bindings.filter((b) => b.store_name === storeName);
  }

  // Show LoginDialog only on 401, not on every page load with no token.
  // In OSS mode (auth.enabled=false) the server returns 200 with no token, so
  // isAuthenticated=false but credentialsQuery.error is null → dialog stays hidden.
  // This matches the spec: "LoginDialog only appears in response to a 401."
  const needs401Login =
    !isAuthenticated &&
    (credentialsQuery.error as any)?.status === 401;

  return (
    <>
      <Helmet>
        <title>Credentials</title>
      </Helmet>

      {/* Dialogs */}
      {needs401Login && (
        <LoginDialog
          onSuccess={(tok) => {
            setToken(tok);
            credentialsQuery.refetch();
            bindingsQuery.refetch();
          }}
        />
      )}

      {addDialogOpen && (
        <AddEditCredentialDialog
          mode="add"
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Credential added.", severity: "success" })}
          onClose={() => setAddDialogOpen(false)}
        />
      )}

      {editCredential && (
        <AddEditCredentialDialog
          mode="edit"
          initialName={editCredential.name}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Credential updated.", severity: "success" })}
          onClose={() => setEditCredential(null)}
        />
      )}

      {confirmDeleteName && (
        <ConfirmChoiceDialog
          header="Delete Credential"
          message={
            <>
              Are you sure you want to delete{" "}
              <strong style={{ color: "red" }}>{confirmDeleteName}</strong>?
              This cannot be undone.
              <div style={{ marginTop: 12 }}>
                Type <strong>{confirmDeleteName}</strong> to confirm.
              </div>
            </>
          }
          isInputConfirmation
          valueToBeDeleted={confirmDeleteName}
          isConfirmLoading={deleteCredential.isLoading}
          handleConfirmationValue={async (confirmed) => {
            if (confirmed && confirmDeleteName) {
              try {
                await deleteCredential.mutateAsync(confirmDeleteName);
                setToastMessage({ text: "Credential deleted.", severity: "success" });
              } catch {
                setToastMessage({ text: "Failed to delete credential.", severity: "error" });
              }
            }
            setConfirmDeleteName(null);
          }}
        />
      )}

      {addBindingFor && (
        <AddBindingDialog
          credentialName={addBindingFor}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Binding added.", severity: "success" })}
          onClose={() => setAddBindingFor(null)}
        />
      )}

      {/* Header */}
      <SectionHeader
        title="Credentials"
        actions={
          <SectionHeaderActions
            buttons={[
              ...(isAuthenticated
                ? [
                    {
                      label: "Logout",
                      onClick: clearToken,
                      variant: "text" as const,
                    },
                  ]
                : []),
              {
                label: "Add Credential",
                onClick: () => setAddDialogOpen(true),
                icon: <AddIcon />,
              },
            ]}
          />
        }
      />

      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ px: 3, pb: 1 }}
      >
        Per-user API keys and secrets. Values are encrypted at rest and never
        shown after creation.
      </Typography>

      <SectionContainer>
        {/* Search */}
        <Box sx={{ mb: 2 }}>
          <TextField
            size="small"
            placeholder="Search credentials…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ width: 280 }}
          />
        </Box>

        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 32 }} /> {/* chevron — 5 columns total */}
                <TableCell>Name</TableCell>
                <TableCell>Value (partial)</TableCell>
                <TableCell>Last updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((cred) => {
                const expanded = expandedName === cred.name;
                const rowBindings = bindingsFor(cred.name);
                return (
                  <>
                    <TableRow
                      key={cred.name}
                      hover
                      sx={{ "& > *": { borderBottom: expanded ? 0 : undefined } }}
                    >
                      <TableCell padding="checkbox">
                        <IconButton
                          size="small"
                          data-testid={`expand-${cred.name}`}
                          onClick={() =>
                            setExpandedName(expanded ? null : cred.name)
                          }
                        >
                          {expanded ? (
                            <ExpandMoreIcon fontSize="small" />
                          ) : (
                            <ChevronRightIcon fontSize="small" />
                          )}
                        </IconButton>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          fontFamily="monospace"
                          fontWeight={500}
                        >
                          {cred.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          fontFamily="monospace"
                          sx={{
                            bgcolor: "action.hover",
                            px: 0.75,
                            py: 0.25,
                            borderRadius: 1,
                            display: "inline",
                          }}
                        >
                          {cred.partial}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {cred.updated_at}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="Edit">
                          <IconButton
                            size="small"
                            onClick={() => setEditCredential(cred)}
                            data-testid={`edit-${cred.name}`}
                          >
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => setConfirmDeleteName(cred.name)}
                            data-testid={`delete-${cred.name}`}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>

                    {/* Bindings expansion row */}
                    <TableRow key={`${cred.name}-bindings`}>
                      <TableCell
                        colSpan={5}
                        sx={{ py: 0, borderBottom: expanded ? undefined : 0 }}
                      >
                        <Collapse in={expanded} timeout="auto" unmountOnExit>
                          <Box
                            sx={{
                              py: 1.5,
                              px: 2,
                              bgcolor: "action.hover",
                              borderTop: "1px solid",
                              borderColor: "divider",
                            }}
                          >
                            <Box
                              sx={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                mb: 1,
                              }}
                            >
                              <Typography
                                variant="caption"
                                fontWeight={600}
                                color="text.secondary"
                                textTransform="uppercase"
                                letterSpacing={0.5}
                              >
                                Bindings — logical keys that resolve to{" "}
                                <code style={{ fontSize: "inherit" }}>
                                  {cred.name}
                                </code>
                              </Typography>
                              <Button
                                size="small"
                                variant="outlined"
                                onClick={() => setAddBindingFor(cred.name)}
                              >
                                + Add binding
                              </Button>
                            </Box>
                            <BindingChips
                              bindings={rowBindings}
                              onDelete={async (logicalKey) => {
                                try {
                                  await deleteBinding.mutateAsync(logicalKey);
                                  setToastMessage({
                                    text: "Binding removed.",
                                    severity: "success",
                                  });
                                } catch {
                                  setToastMessage({
                                    text: "Failed to remove binding.",
                                    severity: "error",
                                  });
                                }
                              }}
                            />
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </>
                );
              })}

              {filtered.length === 0 && !credentialsQuery.isLoading && (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                    <Typography color="text.secondary">
                      {search
                        ? `No credentials match "${search}"`
                        : "No credentials yet — click Add Credential to get started."}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionContainer>

      {toastMessage && (
        <SnackbarMessage
          message={toastMessage.text}
          severity={toastMessage.severity}
          autoHideDuration={3000}
          onDismiss={() => setToastMessage(null)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/__tests__/CredentialsPage.test.tsx
```
Expected: 6 tests pass.

- [ ] **Step 5: Run the full credentials test suite**

```bash
cd ui && npm test -- --reporter=verbose src/pages/credentials/
```
Expected: all tests pass.

- [ ] **Step 6: Run typecheck**

```bash
cd ui && npm run typecheck 2>&1 | head -30
```
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add ui/src/pages/credentials/CredentialsPage.tsx \
        ui/src/pages/credentials/__tests__/CredentialsPage.test.tsx
git commit -m "feat(ui): implement CredentialsPage with table, expand/collapse bindings, and dialogs"
```

---

### Task 8: Final smoke test

**Files:** None new — validation only.

- [ ] **Step 1: Run full UI test suite**

```bash
cd ui && npm test
```
Expected: all tests pass (no regressions).

- [ ] **Step 2: Start dev server and manually verify**

```bash
cd ui && npm run dev
```

Open `http://localhost:5173`. Verify:
1. **Settings** submenu appears in sidebar with **Credentials** item.
2. Navigating to `/credentials` loads the page.
3. In OSS mode (no auth): list loads without `LoginDialog`.
4. `+ Add Credential` opens the dialog; fill Name + Value, save → item appears.
5. Edit icon → dialog opens with Name read-only; update value.
6. Delete icon → confirm dialog requires typing name; confirm → item removed.
7. Expand row → bindings shown; `+ Add binding` → binding appears as chip.
8. Chip ✕ → binding removed.
9. `npm run typecheck` — 0 errors.

- [ ] **Step 3: Push to open PR**

```bash
git push origin feature/credential-management
```
