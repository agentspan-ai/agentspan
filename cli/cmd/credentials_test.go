package cmd

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/agentspan/agentspan/cli/config"
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
		// r.URL.RawPath preserves the percent-encoded form; fall back to Path when empty.
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
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
