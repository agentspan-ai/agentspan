package cmd

import (
	"strings"
	"testing"
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
)

func TestPromptServerURL(t *testing.T) {
	// Enter accepts the current default.
	if got := promptServerURL(strings.NewReader("\n"), "http://localhost:6767"); got != "" {
		t.Errorf("enter should keep current, got %q", got)
	}
	// Full URL passes through (trailing slash trimmed).
	if got := promptServerURL(strings.NewReader("https://my.orkes.io/\n"), "x"); got != "https://my.orkes.io" {
		t.Errorf("got %q", got)
	}
	// Missing scheme defaults to http:// (local instances).
	if got := promptServerURL(strings.NewReader("localhost:8080\n"), "x"); got != "http://localhost:8080" {
		t.Errorf("got %q", got)
	}
}

func TestGetConfigPersistsExplicitServer(t *testing.T) {
	newTempHome(t)
	old := serverURL
	defer func() { serverURL = old }()

	serverURL = "http://localhost:8080"
	cfg := getConfig()
	if cfg.ServerURL != "http://localhost:8080" {
		t.Fatalf("effective server = %q", cfg.ServerURL)
	}
	// The explicit --server must now be the persisted default.
	if got := config.FileServerURL(); got != "http://localhost:8080" {
		t.Errorf("persisted default = %q, want http://localhost:8080", got)
	}
	// And a flag-less invocation picks it up.
	serverURL = ""
	if cfg2 := getConfig(); cfg2.ServerURL != "http://localhost:8080" {
		t.Errorf("flag-less server = %q, want persisted default", cfg2.ServerURL)
	}
}

func TestSaveDefaultServerPreservesAPIKey(t *testing.T) {
	newTempHome(t)
	if err := config.Save(&config.Config{ServerURL: "http://a", APIKey: "keep-me"}); err != nil {
		t.Fatalf("save: %v", err)
	}
	if err := config.SaveDefaultServer("http://b"); err != nil {
		t.Fatalf("SaveDefaultServer: %v", err)
	}
	cfg := config.Load()
	if cfg.ServerURL != "http://b" || cfg.APIKey != "keep-me" {
		t.Errorf("got %+v, want server http://b with api key preserved", cfg)
	}
}

func TestLogoutClearsToken(t *testing.T) {
	newTempHome(t)

	if err := config.SaveToken(&config.TokenInfo{
		AccessToken: "jwt-abc",
		ExpiresAt:   time.Now().Add(time.Hour).Unix(),
	}); err != nil {
		t.Fatalf("save token: %v", err)
	}

	if err := config.ClearToken(); err != nil {
		t.Fatalf("clear token: %v", err)
	}

	tok, err := config.LoadToken()
	if err != nil {
		t.Fatalf("load token: %v", err)
	}
	if tok != nil {
		t.Errorf("token after logout = %+v, want nil", tok)
	}
}

func TestTokenHeaderSelection(t *testing.T) {
	access := &config.TokenInfo{AccessToken: "acc", IDToken: "id", UseIDToken: false}
	if got := access.Header(); got != "acc" {
		t.Errorf("default header = %q, want access token", got)
	}
	idtok := &config.TokenInfo{AccessToken: "acc", IDToken: "id", UseIDToken: true}
	if got := idtok.Header(); got != "id" {
		t.Errorf("useIdToken header = %q, want id token", got)
	}
}

func TestTokenExpired(t *testing.T) {
	expired := &config.TokenInfo{ExpiresAt: time.Now().Add(-time.Minute).Unix()}
	if !expired.Expired() {
		t.Error("expected expired token to report Expired()=true")
	}
	fresh := &config.TokenInfo{ExpiresAt: time.Now().Add(time.Hour).Unix()}
	if fresh.Expired() {
		t.Error("expected fresh token to report Expired()=false")
	}
}
