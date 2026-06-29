package cmd

import (
	"bytes"
	"net"
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

func TestServerStartUsesRequestedVersion(t *testing.T) {
	newTempHome(t)

	prevEnsureLatest := serverEnsureLatestJAR
	prevEnsureVersioned := serverEnsureVersionedJAR
	prevFindLocal := serverFindLocalJAR
	prevCheckJava := serverCheckJava
	prevCheckAI := serverCheckAIProviderKeys
	prevProcessRunning := serverProcessRunning
	prevServerJar := serverJar
	prevServerLocal := serverLocal
	prevServerVersion := serverVersion
	prevServerPort := serverPort
	prevServerModel := serverModel
	t.Cleanup(func() {
		serverEnsureLatestJAR = prevEnsureLatest
		serverEnsureVersionedJAR = prevEnsureVersioned
		serverFindLocalJAR = prevFindLocal
		serverCheckJava = prevCheckJava
		serverCheckAIProviderKeys = prevCheckAI
		serverProcessRunning = prevProcessRunning
		serverJar = prevServerJar
		serverLocal = prevServerLocal
		serverVersion = prevServerVersion
		serverPort = prevServerPort
		serverModel = prevServerModel
	})

	serverJar = ""
	serverLocal = false
	serverVersion = "1.2.3"
	serverPort = freeTCPPort(t)
	serverModel = ""
	serverProcessRunning = func(int) bool { return false }

	versionedCalled := false
	var gotJarPath, gotVersion string
	serverEnsureVersionedJAR = func(jarPath, version string) error {
		versionedCalled = true
		gotJarPath = jarPath
		gotVersion = version
		return nil
	}
	serverEnsureLatestJAR = func(string) error {
		t.Fatal("ensureLatestJAR should not be called when --version is set")
		return nil
	}
	serverFindLocalJAR = func() (string, error) {
		t.Fatal("findLocalJAR should not be called when --version is set")
		return "", nil
	}
	serverCheckAIProviderKeys = func() {}
	serverCheckJava = func() (bool, string) { return false, "" }

	err := runServerStart(serverStartCmd, nil)
	if err == nil {
		t.Fatal("expected runServerStart to stop at Java validation in test")
	}
	if !strings.Contains(err.Error(), "Java is not installed") {
		t.Fatalf("unexpected error: %v", err)
	}
	if !versionedCalled {
		t.Fatal("expected versioned JAR downloader to be called")
	}
	wantJarPath := filepath.Join(serverDir(), "agentspan-runtime-1.2.3.jar")
	if gotJarPath != wantJarPath {
		t.Fatalf("jar path = %q, want %q", gotJarPath, wantJarPath)
	}
	if gotVersion != "1.2.3" {
		t.Fatalf("version = %q, want %q", gotVersion, "1.2.3")
	}
}

// After the server split (#271) the runnable jar lives at
// server/conductor-agentspan-server/build/libs/, not server/build/libs/.
// findLocalJAR must locate it both from the repo root and from a nested CWD.
func TestFindLocalJARNewSplitPath(t *testing.T) {
	root := t.TempDir()
	jarDir := filepath.Join(root, "server", "conductor-agentspan-server", "build", "libs")
	if err := os.MkdirAll(jarDir, 0o755); err != nil {
		t.Fatalf("mkdir jar dir: %v", err)
	}
	jarPath := filepath.Join(jarDir, jarName)
	if err := os.WriteFile(jarPath, []byte("fake jar"), 0o644); err != nil {
		t.Fatalf("write jar: %v", err)
	}
	wantPath, err := filepath.Abs(jarPath)
	if err != nil {
		t.Fatalf("abs jar path: %v", err)
	}

	// Nested CWD exercises the walk-up loop; repo root exercises the candidates list.
	nested := filepath.Join(root, "cli", "cmd")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatalf("mkdir nested: %v", err)
	}

	for _, cwd := range []string{root, nested} {
		t.Run(cwd, func(t *testing.T) {
			t.Chdir(cwd)
			got, err := findLocalJAR()
			if err != nil {
				t.Fatalf("findLocalJAR from %q returned error: %v", cwd, err)
			}
			if got != wantPath {
				t.Fatalf("findLocalJAR from %q = %q, want %q", cwd, got, wantPath)
			}
		})
	}
}

func freeTCPPort(t *testing.T) string {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("allocate free port: %v", err)
	}
	defer ln.Close()
	return strings.TrimPrefix(ln.Addr().String(), "127.0.0.1:")
}
