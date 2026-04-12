package cmd

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

func TestServerPSNoPIDFile(t *testing.T) {
	newTempHome(t)

	prevProcessRunning := serverProcessRunning
	t.Cleanup(func() {
		serverProcessRunning = prevProcessRunning
	})

	cmd := &cobra.Command{}
	var out bytes.Buffer
	cmd.SetOut(&out)

	if err := runServerPS(cmd, nil); err != nil {
		t.Fatalf("runServerPS returned error: %v", err)
	}

	if got := out.String(); got != "No server is running.\n" {
		t.Fatalf("unexpected output: %q", got)
	}
}

func TestServerPSShowsRunningPID(t *testing.T) {
	newTempHome(t)

	if err := os.MkdirAll(filepath.Dir(pidFile()), 0o755); err != nil {
		t.Fatalf("create server dir: %v", err)
	}
	if err := os.WriteFile(pidFile(), []byte("1234\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	prevProcessRunning := serverProcessRunning
	serverProcessRunning = func(pid int) bool {
		return pid == 1234
	}
	t.Cleanup(func() {
		serverProcessRunning = prevProcessRunning
	})

	cmd := &cobra.Command{}
	var out bytes.Buffer
	cmd.SetOut(&out)

	if err := runServerPS(cmd, nil); err != nil {
		t.Fatalf("runServerPS returned error: %v", err)
	}

	got := out.String()
	if !strings.Contains(got, "PID\tSTATUS\n") {
		t.Fatalf("missing header in output: %q", got)
	}
	if !strings.Contains(got, "1234\trunning\n") {
		t.Fatalf("missing running pid in output: %q", got)
	}
}

func TestServerPSRemovesStalePIDFile(t *testing.T) {
	newTempHome(t)

	if err := os.MkdirAll(filepath.Dir(pidFile()), 0o755); err != nil {
		t.Fatalf("create server dir: %v", err)
	}
	if err := os.WriteFile(pidFile(), []byte("4321\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	prevProcessRunning := serverProcessRunning
	serverProcessRunning = func(pid int) bool {
		return false
	}
	t.Cleanup(func() {
		serverProcessRunning = prevProcessRunning
	})

	cmd := &cobra.Command{}
	var out bytes.Buffer
	cmd.SetOut(&out)

	if err := runServerPS(cmd, nil); err != nil {
		t.Fatalf("runServerPS returned error: %v", err)
	}

	got := out.String()
	if !strings.Contains(got, "No server is running. Removed stale PID file for PID 4321.") {
		t.Fatalf("unexpected output: %q", got)
	}
	if _, err := os.Stat(pidFile()); !os.IsNotExist(err) {
		t.Fatalf("expected stale pid file to be removed, stat err=%v", err)
	}
}
