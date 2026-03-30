package config_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/agentspan/agentspan/cli/config"
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
		{"https localhost with port", "https://localhost:6767", true},
		{"https 127.0.0.1", "https://127.0.0.1", true},
		{"ipv6 loopback", "http://[::1]:6767", true},
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
