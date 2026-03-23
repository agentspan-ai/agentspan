# Credentials UI Design Spec

**Date:** 2026-03-20
**Branch:** feature/credential-management

---

## Goal

Add a Credentials management page to the Agentspan UI that lets users store, view, update, and delete per-user API keys and secrets, and manage bindings (logical key → store name aliases). Follows the existing React 18 + MUI 7 + React Query design language exactly.

---

## Architecture

### Page structure

A single `/credentials` route registered under a new **Settings** section in the sidebar. No sub-routes — bindings are managed inline via expandable rows, not a separate page.

### State management

React Query (`useFetch`, `useAction`, `useActionWithPath` from `utils/query.ts`) — no XState needed. Same pattern as `TaskDefinitions` and other list pages. Local `useState` for dialog visibility, expanded row state, and toast messages.

### Auth

The credentials API requires a Bearer JWT only when `auth.enabled=true` (non-default in OSS). The UI handles both modes:

- A `useCredentialAuth` hook in `pages/credentials/hooks/useCredentialAuth.ts` reads/writes a JWT from `localStorage` under the key `agentspan.credential_token`.
- All credentials API calls use a `credentialFetch(path, options)` helper that **wraps `fetchWithContext`** (from `plugins/fetch.ts`), passing an `Authorization: Bearer <token>` header only when a token exists. This preserves `fetchWithContext`'s URL construction (`VITE_WF_SERVER` base, `cleanPath`, error handler).
- If the API returns **401**, the hook clears the token and shows a **LoginDialog**.
- If no token is stored and the API returns **200** (i.e. `auth.enabled=false` — the OSS default), the page loads normally without ever showing `LoginDialog`. `LoginDialog` only appears in response to a 401.
- On successful login (`POST /auth/login`), the token is stored in localStorage and the credentials list is refetched.
- A **Logout** link appears in the page's `SectionHeaderActions` when a token is stored.

This is self-contained — it does not modify the existing `useFetch` / `useAuthHeaders` infrastructure (which uses `X-Authorization` for the existing Conductor APIs).

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `ui/src/pages/credentials/CredentialsPage.tsx` | Main page: table, expand/collapse, dialogs, toasts |
| `ui/src/pages/credentials/hooks/useCredentialAuth.ts` | JWT read/write from localStorage; 401 → clear token → trigger LoginDialog |
| `ui/src/pages/credentials/hooks/useCredentialsApi.ts` | Fetch wrappers: `useListCredentials`, `useCreateCredential`, `useUpdateCredential`, `useDeleteCredential`, `useListBindings`, `useCreateBinding`, `useDeleteBinding` |
| `ui/src/pages/credentials/components/AddEditCredentialDialog.tsx` | Add/edit dialog: Name + Value (masked, show/hide toggle). Edit pre-fills Name (read-only), clears Value. |
| `ui/src/pages/credentials/components/AddBindingDialog.tsx` | Add binding dialog: Logical Key + Store Name fields |
| `ui/src/pages/credentials/components/LoginDialog.tsx` | Username + password dialog; calls `POST /auth/login`; stores token |
| `ui/src/pages/credentials/components/BindingChips.tsx` | Renders binding chips (logical_key → store_name) with delete (✕) |
| `ui/src/pages/credentials/index.ts` | Re-exports `CredentialsPage` |

### Modified files

| File | Change |
|------|--------|
| `ui/src/utils/constants/route.ts` | Add `export const CREDENTIALS_URL = "/credentials";` (single route — plain string, consistent with `NEW_TASK_DEF_URL` pattern) |
| `ui/src/routes/routes.tsx` | Add `{ path: CREDENTIALS_URL, element: <CredentialsPage /> }` |
| `ui/src/components/Sidebar/sidebarCoreItems.tsx` | Add Settings submenu at **position 350** (between Definitions at 300 and Help at 400 — no renumbering needed). Use `SettingsIcon` from `@mui/icons-material` to match the existing sidebar icon style. |

---

## Data Model

API responses the UI consumes:

```typescript
// GET /credentials  — list; no created_at
type CredentialListItem = {
  name: string;         // store name, e.g. "GITHUB_TOKEN"
  partial: string;      // e.g. "ghp_...6789"
  updated_at: string;   // ISO-8601
};

// GET /credentials/bindings  — returns array
type BindingMeta = {
  logical_key: string;  // e.g. "GITHUB_TOKEN" or "GH_TOKEN"
  store_name: string;   // e.g. "GITHUB_TOKEN"
};

// POST /auth/login
type LoginRequest = { username: string; password: string };
type LoginResponse = { token: string; user: { id: string; username: string; name: string } };
```

---

## Component Details

### CredentialsPage

- **Header**: uses `SectionHeader` with `title="Credentials"` and a `SectionHeaderActions` node containing:
  - `+ Add Credential` primary button (always shown)
  - `Logout` text button (shown only when a token is stored in localStorage)
  - A descriptive note ("Values are encrypted at rest and never shown after creation") is placed as a `Typography` subtitle below `SectionHeader`, not inside it (SectionHeader has no subtitle prop).
- **Search**: quick-filter `TextField` above the MUI `Table` — filters `data` client-side by credential name.
- **Table**: MUI `Table` / `TableHead` / `TableBody` (not the custom `DataTable` — credentials list needs no column customisation, sorting, or server-side pagination). Columns: Name | Value (partial) | Last updated | Actions.
- **Expand/collapse**: `useState<string | null>(null)` for `expandedName`. Clicking the chevron cell toggles the state. A `TableRow` immediately after each credential row renders the `BindingChips` section when `expandedName === credential.name`.
- **BindingRow**: spans all 4 columns via `colSpan={4}`. Shows `BindingChips` for bindings where `store_name === credential.name`, plus `+ Add binding` button. If no bindings: "No bindings — add one to alias a different key name to this credential."
- **Add button**: opens `AddEditCredentialDialog` in "add" mode.
- **Edit icon**: opens `AddEditCredentialDialog` in "edit" mode (Name read-only, Value cleared).
- **Delete icon**: `useState<string | null>(null)` for `confirmDeleteName`. Conditionally renders `{confirmDeleteName && <ConfirmChoiceDialog ... />}` — `ConfirmChoiceDialog` has no `open` prop and must be conditionally mounted. Uses `isInputConfirmation={true}` and `valueToBeDeleted={confirmDeleteName}`. On confirm, calls `deleteCredential(confirmDeleteName)`.
- **LoginDialog**: rendered when `!isAuthenticated` — covers the page content, no dismiss button.
- **Toast**: `{toastMessage && <SnackbarMessage message={toastMessage.text} severity={toastMessage.severity} autoHideDuration={3000} onDismiss={() => setToastMessage(null)} />}` — guard required because `message` prop is a required `string`.

### AddEditCredentialDialog

- **Fields**: Name (text, monospace font, required; read-only in edit mode) + Value (password `<input>` with a show/hide `IconButton`, required in both add and edit modes — user re-enters to update).
- **Validation** (React Hook Form + Yup): Name must be non-empty. The UI suggests UPPER_SNAKE_CASE in the helper text ("Convention: UPPER_SNAKE_CASE e.g. GITHUB_TOKEN") but does **not** enforce it with a regex — the backend imposes no constraint and supports lowercase/hyphen names (e.g. `my-github-prod-key`). Only blank names are rejected.
- **Submit**: `POST /credentials` (add) or `PUT /credentials/{name}` (edit) via `credentialFetch`.

### AddBindingDialog

- **Fields**: Logical Key (text, monospace, required) + Store Name (text, monospace, pre-filled with the credential's name, editable).
- **Validation**: both fields non-empty.
- **Submit**: `PUT /credentials/bindings/{logical_key}` with body `{ store_name }` — this is a upsert (create or overwrite), matching the backend API.

### LoginDialog

- **Fields**: Username + Password (masked, `type="password"`).
- **No close button** — cannot be dismissed without logging in.
- **On success**: stores token in localStorage, calls `refetchCredentials()`, closes dialog.
- **On error**: shows inline `Alert severity="error"` inside the dialog: "Invalid username or password."

### useCredentialsApi

All mutations accept an `onSuccess` / `onError` callback pair so `CredentialsPage` can set toast messages.

`credentialFetch(path, options)`:
1. Calls `fetchWithContext(path, fetchContext, { ...options, headers: { ...options.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) } })`.
2. Catches thrown errors (raw `Response` objects per fetch.ts throw behaviour); if `err.status === 401`, calls `clearToken()`. `useCredentialAuth` exposes `{ token, isAuthenticated: !!token, clearToken, setToken }` (from `useCredentialAuth`).
3. Uses the same `fetchContext` from `useFetchContext()` — ensuring `VITE_WF_SERVER` base URL and `cleanPath` logic are inherited.

Query cache invalidation:
- After `createCredential` / `deleteCredential`: invalidate `[fetchContext.stack, "/credentials"]` key.
- After `createBinding` / `deleteBinding`: invalidate `[fetchContext.stack, "/credentials/bindings"]` key. `useDeleteBinding` passes the `logical_key` as the mutation parameter, calls `DELETE /credentials/bindings/{logical_key}`, then invalidates the bindings query.

---

## Sidebar

New **Settings** submenu at **position 350** inserted between Definitions (300) and Help (400). No existing position numbers change.

```typescript
// In CORE_SIDEBAR_POSITIONS.ROOT:
settingsSubMenu: 350,

// Sidebar item:
{
  id: "settingsSubMenu",
  title: "Settings",
  icon: <SettingsIcon />,   // from @mui/icons-material — matches sidebar icon style
  linkTo: "",
  position: 350,
  items: [
    {
      id: "credentialsItem",
      title: "Credentials",
      icon: null,
      linkTo: CREDENTIALS_URL,
      activeRoutes: [CREDENTIALS_URL],
      position: 100,
    },
  ],
}
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| 401 on any credentials API call | Clears token, shows LoginDialog |
| 401 on login attempt | Inline error in LoginDialog: "Invalid username or password" |
| 404 on delete (already gone) | Toast: "Credential not found — it may have already been deleted", severity=warning |
| 409 on create (name exists) | Form-level error on Name field: "A credential with this name already exists" |
| Network error | Toast: "Network error — please try again", severity=error |
| Server returns 200 with no token present | Page loads normally (auth disabled — OSS default) |

---

## Testing

- Tests go in `ui/src/pages/credentials/__tests__/`.
- **`CredentialsPage.test.tsx`**: renders list; expand/collapse bindings row; delete shows `ConfirmChoiceDialog`, typing name enables confirm; delete success shows toast and refetches; 401 response shows `LoginDialog`.
- **`AddEditCredentialDialog.test.tsx`**: blank name rejected; blank value rejected; submit calls `POST` (add) or `PUT` (edit); show/hide toggle changes input type.
- **`AddBindingDialog.test.tsx`**: store name pre-fills with credential name; submit calls `PUT /credentials/bindings/{key}`.
- **`LoginDialog.test.tsx`**: renders when no token; stores token on 200 success; shows inline error on 401.
- **`useCredentialAuth.test.ts`**: `clearToken` removes localStorage key; token present → Authorization header added; no token → no Authorization header.
