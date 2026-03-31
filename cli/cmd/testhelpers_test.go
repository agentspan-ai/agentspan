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

// newTestConfig returns a config pointing at the given server URL without writing to disk.
func newTestConfig(t *testing.T, serverURL string) *config.Config {
	t.Helper()
	cfg := config.DefaultConfig()
	cfg.ServerURL = serverURL
	return cfg
}
