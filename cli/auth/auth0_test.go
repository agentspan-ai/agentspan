package auth

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestDeviceFlow drives RequestDeviceCode + PollForToken against a real local HTTP
// server emulating Auth0's device endpoints, including one authorization_pending poll.
func TestDeviceFlow(t *testing.T) {
	polls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/oauth/device/code":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"device_code":               "dev-123",
				"user_code":                 "WXYZ-1234",
				"verification_uri":          "https://example/activate",
				"verification_uri_complete": "https://example/activate?user_code=WXYZ-1234",
				"expires_in":                300,
				"interval":                  1,
			})
		case "/oauth/token":
			polls++
			if polls < 2 {
				w.WriteHeader(http.StatusForbidden)
				_ = json.NewEncoder(w).Encode(map[string]string{"error": "authorization_pending"})
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"access_token":  "access-xyz",
				"id_token":      "id-xyz",
				"refresh_token": "refresh-xyz",
				"expires_in":    3600,
				"token_type":    "Bearer",
			})
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	dc, err := RequestDeviceCode(srv.URL, "client-id", "")
	if err != nil {
		t.Fatalf("RequestDeviceCode: %v", err)
	}
	if dc.UserCode != "WXYZ-1234" {
		t.Errorf("user code = %q", dc.UserCode)
	}

	tok, err := PollForToken(srv.URL, "client-id", dc)
	if err != nil {
		t.Fatalf("PollForToken: %v", err)
	}
	if tok.AccessToken != "access-xyz" || tok.RefreshToken != "refresh-xyz" {
		t.Errorf("unexpected token: %+v", tok)
	}
	if polls < 2 {
		t.Errorf("expected at least 2 polls (one pending), got %d", polls)
	}
}

func TestRefresh(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			http.Error(w, "bad form", http.StatusBadRequest)
			return
		}
		if r.FormValue("grant_type") != "refresh_token" || r.FormValue("refresh_token") != "rt" {
			http.Error(w, "bad refresh", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "new-access", "expires_in": 3600})
	}))
	defer srv.Close()

	tok, err := Refresh(srv.URL, "client-id", "rt")
	if err != nil {
		t.Fatalf("Refresh: %v", err)
	}
	if tok.AccessToken != "new-access" {
		t.Errorf("refreshed access token = %q", tok.AccessToken)
	}
}

func TestDiscoverConfig(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/context.js" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/javascript")
		_, _ = w.Write([]byte(`window.authConfig = { type: "auth0", domain: "tenant.us.auth0.com", clientId: "abc123", useIdToken: true };`))
	}))
	defer srv.Close()

	cfg, err := DiscoverConfig(srv.URL)
	if err != nil {
		t.Fatalf("DiscoverConfig: %v", err)
	}
	if cfg.Domain != "tenant.us.auth0.com" || cfg.ClientID != "abc123" || !cfg.UseIDToken {
		t.Errorf("unexpected config: %+v", cfg)
	}
}

// TestDiscoverConfigRealOrkesFormat uses the exact serialization a real orkes server
// emits — quoted keys with spaces around the colon, plus the window.conductor flags
// block and the auth0Identifiers fallback block (regression: bare-key-only regex).
func TestDiscoverConfigRealOrkesFormat(t *testing.T) {
	body := `window.conductor = {
  "ENABLE_METRICS_DASHBOARD" : false,
  "MULTITENANCY_TYPE" : "none"
};

window.authConfig = {
  "useIdToken" : false,
  "clientId" : "s4HLdVbnaJMGvPSgx2YLpynfJlW7GV2e",
  "domain" : "auth.orkes.io",
  "type" : "auth0"
};

window.auth0Identifiers = {
  "clientId" : "s4HLdVbnaJMGvPSgx2YLpynfJlW7GV2e",
  "domain" : "auth.orkes.io"
};`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/context.js" {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write([]byte(body))
	}))
	defer srv.Close()

	cfg, err := DiscoverConfig(srv.URL)
	if err != nil {
		t.Fatalf("DiscoverConfig: %v", err)
	}
	if cfg.Domain != "auth.orkes.io" || cfg.ClientID != "s4HLdVbnaJMGvPSgx2YLpynfJlW7GV2e" {
		t.Errorf("unexpected config: %+v", cfg)
	}
	if cfg.UseIDToken {
		t.Error("useIdToken=false in authConfig but parsed true")
	}
}

// TestDiscoverConfigIdentifiersFallback mirrors the UI's auth0-config.ts fallback:
// authConfig missing -> values from window.auth0Identifiers.
func TestDiscoverConfigIdentifiersFallback(t *testing.T) {
	body := `window.auth0Identifiers = {
  "clientId" : "cid-fallback",
  "domain" : "tenant.eu.auth0.com"
};`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(body))
	}))
	defer srv.Close()

	cfg, err := DiscoverConfig(srv.URL)
	if err != nil {
		t.Fatalf("DiscoverConfig: %v", err)
	}
	if cfg.Domain != "tenant.eu.auth0.com" || cfg.ClientID != "cid-fallback" {
		t.Errorf("unexpected config: %+v", cfg)
	}
}

func TestDiscoverConfigNoAuth(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`window.conductor = { stack: "test" };`))
	}))
	defer srv.Close()

	if _, err := DiscoverConfig(srv.URL); err == nil {
		t.Fatal("expected error when /context.js has no authConfig")
	}
}
