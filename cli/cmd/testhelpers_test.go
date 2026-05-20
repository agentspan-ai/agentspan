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
	t.Setenv("AGENTSPAN_API_KEY", "")
	return dir
}

// saveTestConfig saves a config pointing at the given server URL with a test token.
// serverURL should be the test server root (no /api suffix); /api is appended here.
func saveTestConfig(t *testing.T, serverURL string) *config.Config {
	t.Helper()
	cfg := config.DefaultConfig()
	cfg.AgentspanURL = serverURL + "/api"
	cfg.APIKey = "test-token"
	if err := config.Save(cfg); err != nil {
		t.Fatalf("saveTestConfig: %v", err)
	}
	return cfg
}

// newTestConfig returns a config pointing at the given server URL without writing to disk.
// serverURL should be the test server root (no /api suffix); /api is appended here.
func newTestConfig(t *testing.T, serverURL string) *config.Config {
	t.Helper()
	cfg := config.DefaultConfig()
	cfg.AgentspanURL = serverURL + "/api"
	return cfg
}
