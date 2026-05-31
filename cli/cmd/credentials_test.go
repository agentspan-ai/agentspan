package cmd

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/agentspan-ai/agentspan/cli/config"
)

func TestSecretsSet(t *testing.T) {
	newTempHome(t)

	var gotMethod, gotPath, gotBody, gotCT string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotCT = r.Header.Get("Content-Type")
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL)

	if err := runSecretsSet("GITHUB_TOKEN", "ghp_xxx"); err != nil {
		t.Fatalf("runSecretsSet: %v", err)
	}

	if gotMethod != http.MethodPut {
		t.Errorf("method = %q, want PUT", gotMethod)
	}
	if gotPath != "/api/secrets/GITHUB_TOKEN" {
		t.Errorf("path = %q, want /api/secrets/GITHUB_TOKEN", gotPath)
	}
	if gotCT != "text/plain" {
		t.Errorf("Content-Type = %q, want text/plain", gotCT)
	}
	if gotBody != "ghp_xxx" {
		t.Errorf("body = %q, want raw plaintext ghp_xxx", gotBody)
	}
}

func TestSecretsList(t *testing.T) {
	newTempHome(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/secrets/v2" {
			t.Errorf("expected GET /api/secrets/v2, got %s %s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]map[string]string{
			{"name": "GITHUB_TOKEN", "partial": "ghp_...k2mn", "updated_at": "2026-03-15"},
			{"name": "OPENAI_API_KEY", "partial": "sk-...4x9z", "updated_at": "2026-03-10"},
		})
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL)

	output, err := runSecretsList()
	if err != nil {
		t.Fatalf("runSecretsList: %v", err)
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

func TestSecretsListEmpty(t *testing.T) {
	newTempHome(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]map[string]string{})
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL)

	output, err := runSecretsList()
	if err != nil {
		t.Fatalf("runSecretsList: %v", err)
	}
	if !strings.Contains(output, "No secrets") {
		t.Errorf("expected 'No secrets' message, got:\n%s", output)
	}
}

func TestSecretsDelete(t *testing.T) {
	newTempHome(t)

	var gotMethod, gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL)

	if err := runSecretsDelete("GITHUB_TOKEN"); err != nil {
		t.Fatalf("runSecretsDelete: %v", err)
	}

	if gotMethod != http.MethodDelete {
		t.Errorf("method = %q, want DELETE", gotMethod)
	}
	if gotPath != "/api/secrets/GITHUB_TOKEN" {
		t.Errorf("path = %q, want /api/secrets/GITHUB_TOKEN", gotPath)
	}
}

func TestSecretsDeleteEncodesName(t *testing.T) {
	newTempHome(t)

	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL)

	if err := runSecretsDelete("my/cred with spaces"); err != nil {
		t.Fatalf("runSecretsDelete: %v", err)
	}

	if gotPath != "/api/secrets/my%2Fcred%20with%20spaces" {
		t.Errorf("path = %q, want URL-encoded path", gotPath)
	}
}

func TestSecretsBearerHeader(t *testing.T) {
	newTempHome(t)

	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]map[string]string{})
	}))
	defer srv.Close()

	saveTestConfig(t, srv.URL) // sets APIKey = "test-token"

	if _, err := runSecretsList(); err != nil {
		t.Fatalf("runSecretsList: %v", err)
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

	cfg := config.DefaultConfig()
	cfg.ServerURL = srv.URL
	if err := config.Save(cfg); err != nil {
		t.Fatalf("save: %v", err)
	}

	if _, err := runSecretsList(); err != nil {
		t.Fatalf("runSecretsList: %v", err)
	}

	if gotAuth != "" {
		t.Errorf("Authorization = %q, want empty for anonymous mode", gotAuth)
	}
}
