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
