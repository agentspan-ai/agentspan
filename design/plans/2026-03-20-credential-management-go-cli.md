# Go CLI Credentials Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add login/logout and credential management commands to the agentspan CLI.

**Architecture:** The CLI calls server management APIs over HTTP using the existing `client.Client` pattern. A new `APIKey` field in `config.Config` carries the JWT returned by `agentspan login` and is sent as `Authorization: Bearer <api_key>` on every credential-related request. All credential data lives server-side; the only local state is the token in `~/.agentspan/config.json`.

**Tech Stack:** Go, Cobra, standard library (net/http, encoding/json, text/tabwriter, bufio, syscall, testing), golang.org/x/term (password masking)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `cli/config/config.go` | Modify | Add `APIKey` field; add `IsLocalhost()` helper; update `Load`/`Save` |
| `cli/client/client.go` | Modify | Accept `apiKey` on `Client`; send `Authorization: Bearer` header; add credential + auth API methods |
| `cli/cmd/login.go` | Create | `agentspan login` and `agentspan logout` commands |
| `cli/cmd/credentials.go` | Create | `agentspan credentials` group + all six subcommands |
| `cli/cmd/root.go` | No change | `init()` in login.go and credentials.go self-register via `rootCmd.AddCommand` |
| `cli/cmd/login_test.go` | Create | Unit tests for login/logout commands |
| `cli/cmd/credentials_test.go` | Create | Unit tests for all credentials subcommands |
| `cli/cmd/testhelpers_test.go` | Create | Shared test helpers (`newTempHome`, `saveTestConfig`) |
| `cli/config/config_test.go` | Create | Unit tests for `IsLocalhost` and `APIKey` load/save |

---

## Chunk 1: Config and Client Foundation

### Task 1: Add `APIKey` to Config and `IsLocalhost` helper

**Files:**
- Modify: `cli/config/config.go`
- Create: `cli/config/config_test.go`

- [ ] **Step 1: Write the failing tests**

Create `cli/config/config_test.go`:

```go
package config_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/agentspan-ai/agentspan/cli/config"
)

func TestIsLocalhost(t *testing.T) {
	tests := []struct {
		name     string
		url      string
		expected bool
	}{
		{"localhost with port", "http://localhost:6767", true},
		{"localhost no port", "http://localhost", true},
		{"127.0.0.1 with port", "http://127.0.0.1:6767", true},
		{"127.0.0.1 no port", "http://127.0.0.1", true},
		{"remote http", "http://team.agentspan.io", false},
		{"remote https", "https://team.agentspan.io", false},
		{"empty string", "", false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &config.Config{ServerURL: tt.url}
			got := cfg.IsLocalhost()
			if got != tt.expected {
				t.Errorf("IsLocalhost(%q) = %v, want %v", tt.url, got, tt.expected)
			}
		})
	}
}

func TestAPIKeyRoundTrip(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("HOME", dir)
	t.Setenv("AGENTSPAN_AUTH_KEY", "")
	t.Setenv("CONDUCTOR_AUTH_KEY", "")
	t.Setenv("AGENTSPAN_AUTH_SECRET", "")
	t.Setenv("CONDUCTOR_AUTH_SECRET", "")

	cfg := config.DefaultConfig()
	cfg.APIKey = "test-jwt-token-abc123"

	if err := config.Save(cfg); err != nil {
		t.Fatalf("Save: %v", err)
	}

	data, err := os.ReadFile(filepath.Join(dir, ".agentspan", "config.json"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}
	if raw["api_key"] != "test-jwt-token-abc123" {
		t.Errorf("api_key in JSON = %v, want test-jwt-token-abc123", raw["api_key"])
	}

	loaded := config.Load()
	if loaded.APIKey != "test-jwt-token-abc123" {
		t.Errorf("loaded.APIKey = %q, want %q", loaded.APIKey, "test-jwt-token-abc123")
	}
}

func TestAPIKeyClearedOnLogout(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("HOME", dir)
	t.Setenv("AGENTSPAN_AUTH_KEY", "")
	t.Setenv("CONDUCTOR_AUTH_KEY", "")
	t.Setenv("AGENTSPAN_AUTH_SECRET", "")
	t.Setenv("CONDUCTOR_AUTH_SECRET", "")

	cfg := config.DefaultConfig()
	cfg.APIKey = "some-token"
	if err := config.Save(cfg); err != nil {
		t.Fatalf("Save: %v", err)
	}

	cfg.APIKey = ""
	if err := config.Save(cfg); err != nil {
		t.Fatalf("Save cleared: %v", err)
	}

	loaded := config.Load()
	if loaded.APIKey != "" {
		t.Errorf("expected empty APIKey after clearing, got %q", loaded.APIKey)
	}
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./config/ -run "TestIsLocalhost|TestAPIKey" -v
```

Expected: FAIL — `config.Config` has no `APIKey` field, `IsLocalhost` is undefined.

- [ ] **Step 3: Implement changes to `cli/config/config.go`**

Read the existing `cli/config/config.go` first, then add:
1. `APIKey string \`json:"api_key,omitempty"\`` to the `Config` struct
2. `IsLocalhost()` method on `*Config`
3. Load `APIKey` from file in the `Load()` function
4. Ensure `Save()` persists `APIKey`

The `IsLocalhost` implementation:
```go
func (c *Config) IsLocalhost() bool {
    return strings.HasPrefix(c.ServerURL, "http://localhost") ||
        strings.HasPrefix(c.ServerURL, "http://127.0.0.1")
}
```

Add `"strings"` to the import block if not already present.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./config/ -run "TestIsLocalhost|TestAPIKey" -v
```

Expected: PASS — all 3 test functions pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && git add config/config.go config/config_test.go && git commit -m "feat(config): add APIKey field and IsLocalhost helper"
```

---

### Task 2: Add Bearer auth and credential API methods to Client

**Files:**
- Modify: `cli/client/client.go`

Read the existing `cli/client/client.go` to understand current structure, then:
1. Add `apiKey string` field to the `Client` struct
2. In `New(cfg)`, set `apiKey: cfg.APIKey`
3. In the request-building code, when `apiKey != ""` set `Authorization: Bearer <apiKey>` header; else fall back to existing `X-Auth-Key`/`X-Auth-Secret` headers
4. Add these new methods:

```go
// LoginRequest / LoginResponse
type LoginRequest struct {
    Username string `json:"username"`
    Password string `json:"password"`
}
type LoginResponse struct {
    Token string `json:"token"`
}
func (c *Client) Login(username, password string) (*LoginResponse, error)

// Credential management
type CredentialMeta struct {
    Name      string `json:"name"`
    Partial   string `json:"partial"`
    UpdatedAt string `json:"updated_at"`
}
type CredentialSetRequest struct {
    Name  string `json:"name"`
    Value string `json:"value"`
}
type BindingMeta struct {
    LogicalKey string `json:"logical_key"`
    StoreName  string `json:"store_name"`
}
type BindingSetRequest struct {
    StoreName string `json:"store_name"`
}

func (c *Client) ListCredentials() ([]CredentialMeta, error)   // GET /api/credentials
func (c *Client) SetCredential(name, value string) error        // POST /api/credentials
func (c *Client) DeleteCredential(name string) error            // DELETE /api/credentials/{name}
func (c *Client) ListBindings() ([]BindingMeta, error)          // GET /api/credentials/bindings
func (c *Client) SetBinding(logicalKey, storeName string) error // PUT /api/credentials/bindings/{key}
```

Use `net/url.PathEscape(name)` when embedding names in URL paths.

- [ ] **Step 1: Read the existing client file**

```bash
cat /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli/client/client.go
```

- [ ] **Step 2: Apply the changes described above**

- [ ] **Step 3: Verify the package compiles**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go build ./...
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && git add client/client.go && git commit -m "feat(client): add Bearer auth header and credential/auth API methods"
```

---

## Chunk 2: Login and Logout Commands

### Task 3: Add `golang.org/x/term` dependency for password masking

**Files:**
- Modify: `cli/go.mod`, `cli/go.sum`

- [ ] **Step 1: Add the dependency**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go get golang.org/x/term@latest
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go build ./...
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && git add go.mod go.sum && git commit -m "chore(deps): add golang.org/x/term for password input masking"
```

---

### Task 4: Implement `agentspan login` and `agentspan logout`

**Files:**
- Create: `cli/cmd/login.go`
- Create: `cli/cmd/login_test.go`
- Create: `cli/cmd/testhelpers_test.go`

The `login` command prompts for username then password (masked), POSTs to `/api/auth/login`, and stores the returned JWT as `api_key` in config. The `logout` command clears `api_key`. Tests use `httptest.NewServer` and call `doLogin()` directly to avoid terminal I/O.

- [ ] **Step 1: Create `cli/cmd/testhelpers_test.go`**

```go
package cmd

import (
    "testing"

    "github.com/agentspan-ai/agentspan/cli/config"
)

// newTempHome points HOME at a temp dir so config reads/writes are isolated.
func newTempHome(t *testing.T) string {
    t.Helper()
    dir := t.TempDir()
    t.Setenv("HOME", dir)
    t.Setenv("AGENTSPAN_SERVER_URL", "")
    t.Setenv("AGENT_SERVER_URL", "")
    t.Setenv("AGENTSPAN_AUTH_KEY", "")
    t.Setenv("CONDUCTOR_AUTH_KEY", "")
    t.Setenv("AGENTSPAN_AUTH_SECRET", "")
    t.Setenv("CONDUCTOR_AUTH_SECRET", "")
    return dir
}

// saveTestConfig saves a config pointing at the given server URL with a test token.
func saveTestConfig(t *testing.T, serverURL string) *config.Config {
    t.Helper()
    cfg := config.DefaultConfig()
    cfg.ServerURL = serverURL
    cfg.APIKey = "test-token"
    if err := config.Save(cfg); err != nil {
        t.Fatalf("saveTestConfig: %v", err)
    }
    return cfg
}
```

- [ ] **Step 2: Create `cli/cmd/login_test.go`**

```go
package cmd

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/agentspan-ai/agentspan/cli/config"
)

func TestLogoutClearsAPIKey(t *testing.T) {
    newTempHome(t)

    cfg := config.DefaultConfig()
    cfg.APIKey = "existing-token"
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save: %v", err)
    }

    cfg.APIKey = ""
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save cleared: %v", err)
    }

    loaded := config.Load()
    if loaded.APIKey != "" {
        t.Errorf("APIKey after logout = %q, want empty", loaded.APIKey)
    }
}

func TestLoginStoresToken(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodPost || r.URL.Path != "/api/auth/login" {
            http.NotFound(w, r)
            return
        }
        var body map[string]string
        if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
            http.Error(w, "bad body", http.StatusBadRequest)
            return
        }
        if body["username"] != "alice" || body["password"] != "secret" {
            http.Error(w, "unauthorized", http.StatusUnauthorized)
            return
        }
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"token": "jwt-abc123"})
    }))
    defer srv.Close()

    cfg := config.DefaultConfig()
    cfg.ServerURL = srv.URL
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save: %v", err)
    }

    if err := doLogin(cfg, "alice", "secret"); err != nil {
        t.Fatalf("doLogin: %v", err)
    }

    loaded := config.Load()
    if loaded.APIKey != "jwt-abc123" {
        t.Errorf("APIKey = %q, want jwt-abc123", loaded.APIKey)
    }
}

func TestLoginServerError(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        http.Error(w, "unauthorized", http.StatusUnauthorized)
    }))
    defer srv.Close()

    cfg := config.DefaultConfig()
    cfg.ServerURL = srv.URL
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save: %v", err)
    }

    if err := doLogin(cfg, "bad", "creds"); err == nil {
        t.Fatal("expected error from doLogin on 401, got nil")
    }
}

func TestLoginEmptyTokenError(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"token": ""})
    }))
    defer srv.Close()

    cfg := config.DefaultConfig()
    cfg.ServerURL = srv.URL
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save: %v", err)
    }

    if err := doLogin(cfg, "user", "pass"); err == nil {
        t.Fatal("expected error for empty token, got nil")
    }
}
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./cmd/ -run "TestLogin|TestLogout" -v 2>&1 | head -20
```

Expected: compile failure — `doLogin` is not yet defined.

- [ ] **Step 4: Create `cli/cmd/login.go`**

```go
package cmd

import (
    "bufio"
    "fmt"
    "os"
    "strings"
    "syscall"

    "github.com/agentspan-ai/agentspan/cli/client"
    "github.com/agentspan-ai/agentspan/cli/config"
    "github.com/fatih/color"
    "github.com/spf13/cobra"
    "golang.org/x/term"
)

var loginCmd = &cobra.Command{
    Use:   "login",
    Short: "Log in to the AgentSpan server and store an auth token",
    Long: `Prompts for username and password, authenticates against the server,
and stores the returned JWT in ~/.agentspan/config.json.

On localhost with auth disabled, this command is not required — the server
accepts all requests as anonymous admin automatically.`,
    RunE: func(cmd *cobra.Command, args []string) error {
        cfg := getConfig()

        if cfg.IsLocalhost() && cfg.APIKey == "" {
            color.Yellow("Server is localhost — auth is optional.")
            fmt.Println("Proceeding without login (anonymous admin mode).")
            return nil
        }

        fmt.Print("Username: ")
        reader := bufio.NewReader(os.Stdin)
        username, err := reader.ReadString('\n')
        if err != nil {
            return fmt.Errorf("read username: %w", err)
        }
        username = strings.TrimSpace(username)

        fmt.Print("Password: ")
        passwordBytes, err := term.ReadPassword(int(syscall.Stdin))
        fmt.Println()
        if err != nil {
            return fmt.Errorf("read password: %w", err)
        }
        password := string(passwordBytes)

        if err := doLogin(cfg, username, password); err != nil {
            return err
        }

        color.Green("Logged in successfully.")
        fmt.Printf("Token stored in %s/config.json\n", config.ConfigDir())
        return nil
    },
}

var logoutCmd = &cobra.Command{
    Use:   "logout",
    Short: "Remove the stored auth token",
    RunE: func(cmd *cobra.Command, args []string) error {
        cfg := config.Load()
        if cfg.APIKey == "" {
            color.Yellow("Not currently logged in.")
            return nil
        }
        cfg.APIKey = ""
        if err := config.Save(cfg); err != nil {
            return fmt.Errorf("save config: %w", err)
        }
        color.Green("Logged out.")
        return nil
    },
}

// doLogin calls the server auth endpoint and persists the returned token.
// Extracted so tests can call it directly without terminal I/O.
func doLogin(cfg *config.Config, username, password string) error {
    c := client.New(cfg)
    resp, err := c.Login(username, password)
    if err != nil {
        return fmt.Errorf("login failed: %w", err)
    }
    if resp.Token == "" {
        return fmt.Errorf("server returned empty token")
    }
    cfg.APIKey = resp.Token
    if err := config.Save(cfg); err != nil {
        return fmt.Errorf("save config: %w", err)
    }
    return nil
}

func init() {
    rootCmd.AddCommand(loginCmd)
    rootCmd.AddCommand(logoutCmd)
}
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./cmd/ -run "TestLogin|TestLogout" -v
```

Expected: PASS — all 4 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && git add cmd/login.go cmd/login_test.go cmd/testhelpers_test.go && git commit -m "feat(cmd): add login and logout commands"
```

---

## Chunk 3: Credentials Commands

### Task 5: Implement `agentspan credentials` subcommand group

**Files:**
- Create: `cli/cmd/credentials.go`
- Create: `cli/cmd/credentials_test.go`

All six subcommands (`set`, `list`, `delete`, `bind`, `bindings`) live in one file. Each command delegates to a `runCredentials*()` helper so tests can call directly without Cobra plumbing.

- [ ] **Step 1: Write the failing tests in `cli/cmd/credentials_test.go`**

```go
package cmd

import (
    "encoding/json"
    "io"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
)

func TestCredentialsSetSimple(t *testing.T) {
    newTempHome(t)

    var gotBody map[string]string
    var gotMethod, gotPath string

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotMethod = r.Method
        gotPath = r.URL.Path
        b, _ := io.ReadAll(r.Body)
        json.Unmarshal(b, &gotBody)
        w.WriteHeader(http.StatusOK)
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    if err := runCredentialsSet("GITHUB_TOKEN", "ghp_xxx", ""); err != nil {
        t.Fatalf("runCredentialsSet: %v", err)
    }

    if gotMethod != http.MethodPost {
        t.Errorf("method = %q, want POST", gotMethod)
    }
    if gotPath != "/api/credentials" {
        t.Errorf("path = %q, want /api/credentials", gotPath)
    }
    if gotBody["name"] != "GITHUB_TOKEN" {
        t.Errorf("body.name = %q, want GITHUB_TOKEN", gotBody["name"])
    }
    if gotBody["value"] != "ghp_xxx" {
        t.Errorf("body.value = %q, want ghp_xxx", gotBody["value"])
    }
}

func TestCredentialsSetWithStoreName(t *testing.T) {
    newTempHome(t)

    var gotBody map[string]string
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        b, _ := io.ReadAll(r.Body)
        json.Unmarshal(b, &gotBody)
        w.WriteHeader(http.StatusOK)
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    // storeName overrides: value is first arg, storeName is the name sent
    if err := runCredentialsSet("ghp_xxx", "", "github-prod"); err != nil {
        t.Fatalf("runCredentialsSet: %v", err)
    }

    if gotBody["name"] != "github-prod" {
        t.Errorf("body.name = %q, want github-prod", gotBody["name"])
    }
    if gotBody["value"] != "ghp_xxx" {
        t.Errorf("body.value = %q, want ghp_xxx", gotBody["value"])
    }
}

func TestCredentialsList(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{
            {"name": "GITHUB_TOKEN", "partial": "ghp_...k2mn", "updated_at": "2026-03-15"},
            {"name": "OPENAI_API_KEY", "partial": "sk-...4x9z", "updated_at": "2026-03-10"},
        })
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    output, err := runCredentialsList()
    if err != nil {
        t.Fatalf("runCredentialsList: %v", err)
    }

    if !strings.Contains(output, "GITHUB_TOKEN") {
        t.Errorf("output missing GITHUB_TOKEN:\n%s", output)
    }
    if !strings.Contains(output, "ghp_...k2mn") {
        t.Errorf("output missing partial:\n%s", output)
    }
    if !strings.Contains(output, "2026-03-15") {
        t.Errorf("output missing updated_at:\n%s", output)
    }
}

func TestCredentialsListEmpty(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{})
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    output, err := runCredentialsList()
    if err != nil {
        t.Fatalf("runCredentialsList: %v", err)
    }
    if !strings.Contains(output, "No credentials") {
        t.Errorf("expected 'No credentials' message, got:\n%s", output)
    }
}

func TestCredentialsDelete(t *testing.T) {
    newTempHome(t)

    var gotMethod, gotPath string
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotMethod = r.Method
        gotPath = r.URL.Path
        w.WriteHeader(http.StatusOK)
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    if err := runCredentialsDelete("GITHUB_TOKEN"); err != nil {
        t.Fatalf("runCredentialsDelete: %v", err)
    }

    if gotMethod != http.MethodDelete {
        t.Errorf("method = %q, want DELETE", gotMethod)
    }
    if gotPath != "/api/credentials/GITHUB_TOKEN" {
        t.Errorf("path = %q, want /api/credentials/GITHUB_TOKEN", gotPath)
    }
}

func TestCredentialsDeleteEncodesName(t *testing.T) {
    newTempHome(t)

    var gotPath string
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotPath = r.URL.Path
        w.WriteHeader(http.StatusOK)
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    if err := runCredentialsDelete("my/cred with spaces"); err != nil {
        t.Fatalf("runCredentialsDelete: %v", err)
    }

    if gotPath != "/api/credentials/my%2Fcred%20with%20spaces" {
        t.Errorf("path = %q, want URL-encoded path", gotPath)
    }
}

func TestCredentialsBind(t *testing.T) {
    newTempHome(t)

    var gotMethod, gotPath string
    var gotBody map[string]string

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotMethod = r.Method
        gotPath = r.URL.Path
        b, _ := io.ReadAll(r.Body)
        json.Unmarshal(b, &gotBody)
        w.WriteHeader(http.StatusOK)
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    if err := runCredentialsBind("GITHUB_TOKEN", "github-prod"); err != nil {
        t.Fatalf("runCredentialsBind: %v", err)
    }

    if gotMethod != http.MethodPut {
        t.Errorf("method = %q, want PUT", gotMethod)
    }
    if gotPath != "/api/credentials/bindings/GITHUB_TOKEN" {
        t.Errorf("path = %q, want /api/credentials/bindings/GITHUB_TOKEN", gotPath)
    }
    if gotBody["store_name"] != "github-prod" {
        t.Errorf("body.store_name = %q, want github-prod", gotBody["store_name"])
    }
}

func TestCredentialsBindings(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{
            {"logical_key": "GITHUB_TOKEN", "store_name": "github-prod"},
        })
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    output, err := runCredentialsBindings()
    if err != nil {
        t.Fatalf("runCredentialsBindings: %v", err)
    }

    if !strings.Contains(output, "GITHUB_TOKEN") {
        t.Errorf("output missing GITHUB_TOKEN:\n%s", output)
    }
    if !strings.Contains(output, "github-prod") {
        t.Errorf("output missing github-prod:\n%s", output)
    }
}

func TestCredentialsBindingsEmpty(t *testing.T) {
    newTempHome(t)

    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{})
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL)

    output, err := runCredentialsBindings()
    if err != nil {
        t.Fatalf("runCredentialsBindings: %v", err)
    }
    if !strings.Contains(output, "No bindings") {
        t.Errorf("expected 'No bindings' message, got:\n%s", output)
    }
}

func TestCredentialsBearerHeader(t *testing.T) {
    newTempHome(t)

    var gotAuth string
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotAuth = r.Header.Get("Authorization")
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{})
    }))
    defer srv.Close()

    saveTestConfig(t, srv.URL) // sets APIKey = "test-token"

    if _, err := runCredentialsList(); err != nil {
        t.Fatalf("runCredentialsList: %v", err)
    }

    if gotAuth != "Bearer test-token" {
        t.Errorf("Authorization = %q, want \"Bearer test-token\"", gotAuth)
    }
}

func TestNoAuthHeaderOnLocalhostAnonymous(t *testing.T) {
    newTempHome(t)

    var gotAuth string
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        gotAuth = r.Header.Get("Authorization")
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode([]map[string]string{})
    }))
    defer srv.Close()

    // Config with no api_key — anonymous mode
    cfg := config.DefaultConfig()
    cfg.ServerURL = srv.URL
    if err := config.Save(cfg); err != nil {
        t.Fatalf("save: %v", err)
    }

    if _, err := runCredentialsList(); err != nil {
        t.Fatalf("runCredentialsList: %v", err)
    }

    if gotAuth != "" {
        t.Errorf("Authorization = %q, want empty for anonymous mode", gotAuth)
    }
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./cmd/ -run "TestCredentials|TestNoAuth" -v 2>&1 | head -20
```

Expected: compile failure — `runCredentialsList` etc. not yet defined.

- [ ] **Step 3: Create `cli/cmd/credentials.go`**

```go
package cmd

import (
    "bytes"
    "fmt"
    "text/tabwriter"

    "github.com/agentspan-ai/agentspan/cli/client"
    "github.com/agentspan-ai/agentspan/cli/config"
    "github.com/fatih/color"
    "github.com/spf13/cobra"
)

var credentialsCmd = &cobra.Command{
    Use:     "credentials",
    Aliases: []string{"creds"},
    Short:   "Manage credentials stored on the AgentSpan server",
}

// ─── credentials set ──────────────────────────────────────────────────────────

var credentialsSetStoreName string

var credentialsSetCmd = &cobra.Command{
    Use:   "set <NAME> <VALUE>",
    Short: "Store a credential on the server",
    Long: `Store a credential value.

Simple form (logical name = store name, server auto-binds):
  agentspan credentials set GITHUB_TOKEN ghp_xxx

Advanced form (custom store name, explicit binding needed):
  agentspan credentials set --name github-prod ghp_xxx
  agentspan credentials bind GITHUB_TOKEN github-prod`,
    RunE: func(cmd *cobra.Command, args []string) error {
        storeName, _ := cmd.Flags().GetString("name")
        var name, value string
        if storeName != "" {
            if len(args) != 1 {
                return fmt.Errorf("with --name, provide exactly one argument: the credential value")
            }
            name = storeName
            value = args[0]
        } else {
            if len(args) != 2 {
                return fmt.Errorf("usage: credentials set <NAME> <VALUE>  or  credentials set --name <STORE> <VALUE>")
            }
            name = args[0]
            value = args[1]
        }
        if err := runCredentialsSet(name, value, storeName); err != nil {
            return err
        }
        color.Green("Credential %q stored.", name)
        return nil
    },
}

func runCredentialsSet(nameOrValue, value, storeName string) error {
    cfg := config.Load()
    c := client.New(cfg)
    credName := nameOrValue
    credValue := value
    if storeName != "" {
        credName = storeName
        credValue = nameOrValue
    }
    return c.SetCredential(credName, credValue)
}

// ─── credentials list ─────────────────────────────────────────────────────────

var credentialsListCmd = &cobra.Command{
    Use:   "list",
    Short: "List stored credentials (name, partial value, last updated)",
    RunE: func(cmd *cobra.Command, args []string) error {
        output, err := runCredentialsList()
        if err != nil {
            return err
        }
        fmt.Print(output)
        return nil
    },
}

func runCredentialsList() (string, error) {
    cfg := config.Load()
    c := client.New(cfg)
    creds, err := c.ListCredentials()
    if err != nil {
        return "", fmt.Errorf("list credentials: %w", err)
    }
    if len(creds) == 0 {
        return "No credentials stored.\n", nil
    }
    var buf bytes.Buffer
    w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
    fmt.Fprintln(w, "NAME\tPARTIAL\tUPDATED")
    fmt.Fprintln(w, "----\t-------\t-------")
    for _, cr := range creds {
        fmt.Fprintf(w, "%s\t%s\t%s\n", cr.Name, cr.Partial, cr.UpdatedAt)
    }
    w.Flush()
    return buf.String(), nil
}

// ─── credentials delete ───────────────────────────────────────────────────────

var credentialsDeleteCmd = &cobra.Command{
    Use:   "delete <NAME>",
    Short: "Delete a stored credential",
    Args:  cobra.ExactArgs(1),
    RunE: func(cmd *cobra.Command, args []string) error {
        if err := runCredentialsDelete(args[0]); err != nil {
            return err
        }
        color.Green("Credential %q deleted.", args[0])
        return nil
    },
}

func runCredentialsDelete(name string) error {
    cfg := config.Load()
    return client.New(cfg).DeleteCredential(name)
}

// ─── credentials bind ─────────────────────────────────────────────────────────

var credentialsBindCmd = &cobra.Command{
    Use:   "bind <LOGICAL_KEY> <STORE_NAME>",
    Short: "Bind a logical credential key to a stored secret",
    Args:  cobra.ExactArgs(2),
    RunE: func(cmd *cobra.Command, args []string) error {
        if err := runCredentialsBind(args[0], args[1]); err != nil {
            return err
        }
        color.Green("Bound %q -> %q.", args[0], args[1])
        return nil
    },
}

func runCredentialsBind(logicalKey, storeName string) error {
    cfg := config.Load()
    return client.New(cfg).SetBinding(logicalKey, storeName)
}

// ─── credentials bindings ─────────────────────────────────────────────────────

var credentialsBindingsCmd = &cobra.Command{
    Use:   "bindings",
    Short: "List logical key → store name bindings",
    RunE: func(cmd *cobra.Command, args []string) error {
        output, err := runCredentialsBindings()
        if err != nil {
            return err
        }
        fmt.Print(output)
        return nil
    },
}

func runCredentialsBindings() (string, error) {
    cfg := config.Load()
    c := client.New(cfg)
    bindings, err := c.ListBindings()
    if err != nil {
        return "", fmt.Errorf("list bindings: %w", err)
    }
    if len(bindings) == 0 {
        return "No bindings configured.\n", nil
    }
    var buf bytes.Buffer
    w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
    fmt.Fprintln(w, "LOGICAL KEY\tSTORE NAME")
    fmt.Fprintln(w, "-----------\t----------")
    for _, b := range bindings {
        fmt.Fprintf(w, "%s\t%s\n", b.LogicalKey, b.StoreName)
    }
    w.Flush()
    return buf.String(), nil
}

// ─── init ─────────────────────────────────────────────────────────────────────

func init() {
    credentialsSetCmd.Flags().StringVar(&credentialsSetStoreName, "name", "",
        "Store name (overrides logical key as the storage key)")

    credentialsCmd.AddCommand(credentialsSetCmd)
    credentialsCmd.AddCommand(credentialsListCmd)
    credentialsCmd.AddCommand(credentialsDeleteCmd)
    credentialsCmd.AddCommand(credentialsBindCmd)
    credentialsCmd.AddCommand(credentialsBindingsCmd)

    // Default action: show credentials list
    credentialsCmd.RunE = func(cmd *cobra.Command, args []string) error {
        output, err := runCredentialsList()
        if err != nil {
            return err
        }
        fmt.Print(output)
        return nil
    }

    rootCmd.AddCommand(credentialsCmd)
}
```

- [ ] **Step 4: Run all credential + login tests**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./cmd/ -v
```

Expected: PASS — all tests in `cmd` package pass.

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./...
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && git add cmd/credentials.go cmd/credentials_test.go && git commit -m "feat(cmd): add credentials subcommand group (set, list, delete, bind, bindings)"
```

---

## Chunk 4: Final Verification

### Task 6: Build and smoke-test

**Files:** none (verification only)

- [ ] **Step 1: Build the binary**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go build -o /tmp/agentspan-test .
```

Expected: no errors.

- [ ] **Step 2: Verify help surfaces**

```bash
/tmp/agentspan-test --help | grep -E "credentials|login|logout"
```

Expected output includes all three commands.

```bash
/tmp/agentspan-test credentials --help
```

Expected: shows `set`, `list`, `delete`, `bind`, `bindings` subcommands.

```bash
/tmp/agentspan-test credentials set --help
```

Expected: shows `--name` flag in usage.

- [ ] **Step 3: Clean up**

```bash
rm /tmp/agentspan-test
```

- [ ] **Step 4: Run full test suite one final time**

```bash
cd /Users/viren/workspace/github/agentspan-dev/branches/agentspan-branch/cli && go test ./...
```

Expected: PASS — all green.

---

## Future Work (out of scope)

- **Enterprise OIDC browser flow:** `agentspan login --enterprise` opens a browser for OIDC. Requires OS-specific browser-open and a localhost redirect receiver.
- **`agentspan admin credentials re-encrypt`:** Key rotation command is a server-side admin operation.
- **Confirmation prompt on `credentials delete`:** Add `--yes` flag or interactive confirmation for safety.
- **`agentspan credentials update`:** If the server differentiates `POST` (create) from `PUT /{name}` (update), a dedicated `update` subcommand may be added.
