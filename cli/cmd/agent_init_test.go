package cmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// chdirTemp creates a temp dir, chdirs into it, and restores the original on cleanup.
func chdirTemp(t *testing.T) string {
	t.Helper()
	tmp := t.TempDir()
	orig, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(tmp); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chdir(orig) })
	return tmp
}

func TestInit_CreatesAgentspanYAML(t *testing.T) {
	chdirTemp(t)
	initForce = false

	if err := runInitCmd(nil, []string{"my-agent"}); err != nil {
		t.Fatalf("runInitCmd: %v", err)
	}

	if _, err := os.Stat(filepath.Join("my-agent", "agentspan.yaml")); err != nil {
		t.Errorf("expected agentspan.yaml to exist: %v", err)
	}
	for _, extra := range []string{"main.py", "requirements.txt"} {
		if _, err := os.Stat(filepath.Join("my-agent", extra)); err == nil {
			t.Errorf("%s must not be created by init", extra)
		}
	}
}

func TestInit_AgentspanYamlHasName(t *testing.T) {
	chdirTemp(t)
	initForce = false

	if err := runInitCmd(nil, []string{"my-agent"}); err != nil {
		t.Fatalf("runInitCmd: %v", err)
	}

	data, err := os.ReadFile(filepath.Join("my-agent", "agentspan.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "name:       my-agent") {
		t.Errorf("agentspan.yaml does not contain expected name field, got:\n%s", data)
	}
}

func TestInit_DotUsesBasename(t *testing.T) {
	tmp := chdirTemp(t)

	sub := filepath.Join(tmp, "dot-agent")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	orig, _ := os.Getwd()
	if err := os.Chdir(sub); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chdir(orig) })
	initForce = false

	if err := runInitCmd(nil, []string{"."}); err != nil {
		t.Fatalf("runInitCmd(.): %v", err)
	}

	data, err := os.ReadFile(filepath.Join(sub, "agentspan.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "name:       dot-agent") {
		t.Errorf("expected name dot-agent in agentspan.yaml, got:\n%s", data)
	}
}

func TestInit_ErrorIfDirExists(t *testing.T) {
	chdirTemp(t)
	initForce = false

	if err := runInitCmd(nil, []string{"my-agent"}); err != nil {
		t.Fatalf("first call failed: %v", err)
	}

	initForce = false
	err := runInitCmd(nil, []string{"my-agent"})
	if err == nil {
		t.Fatal("expected error on second call without --force, got nil")
	}
	if !strings.Contains(err.Error(), "already exists") {
		t.Errorf("error should mention 'already exists', got: %v", err)
	}
}

func TestInit_ForceOverwrites(t *testing.T) {
	chdirTemp(t)
	initForce = false

	if err := runInitCmd(nil, []string{"my-agent"}); err != nil {
		t.Fatalf("first call failed: %v", err)
	}

	initForce = true
	t.Cleanup(func() { initForce = false })

	if err := runInitCmd(nil, []string{"my-agent"}); err != nil {
		t.Fatalf("second call with --force failed: %v", err)
	}
}

func TestInit_RejectsInvalidName(t *testing.T) {
	chdirTemp(t)
	initForce = false

	for _, bad := range []string{"MyAgent", "123abc", "-bad", "has space", "HAS_UPPER"} {
		err := runInitCmd(nil, []string{bad})
		if err == nil {
			t.Errorf("expected error for name %q, got nil", bad)
		}
	}
}
