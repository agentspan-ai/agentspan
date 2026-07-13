// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"os"
	"path/filepath"
	"testing"
)

// TestMain sandboxes HOME for the whole package. getConfig persists the
// package-level serverURL flag to ~/.agentspan/config.json, so any test that
// sets serverURL (most httptest-based command tests do) would otherwise
// overwrite the developer's real config with an ephemeral test port.
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "agentspan-cmd-test-home-*")
	if err != nil {
		panic(err)
	}
	os.Setenv("HOME", dir)
	os.Setenv("USERPROFILE", dir)
	if vol := filepath.VolumeName(dir); vol != "" {
		os.Setenv("HOMEDRIVE", vol)
		os.Setenv("HOMEPATH", dir[len(vol):])
	}
	os.Unsetenv("AGENTSPAN_SERVER_URL")
	os.Unsetenv("AGENT_SERVER_URL")
	os.Unsetenv("AGENTSPAN_API_KEY")

	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}
