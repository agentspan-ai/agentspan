// Package serverctl provides the core logic for starting, stopping, and
// health-checking the AgentSpan runtime server. Shared between cmd/server.go
// and the TUI views/server.go so both can launch the JVM process.
package serverctl

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	S3Bucket = "https://agentspan.s3.us-east-2.amazonaws.com"
	JarName  = "agentspan-runtime.jar"
	// StartTimeout is how long we wait for the health check to pass.
	StartTimeout = 5 * time.Minute
)

// Options configures a server start call.
type Options struct {
	Port    string // default "6767"
	Model   string // AGENT_DEFAULT_MODEL env var
	JarPath string // override JAR path
}

// StartResult is returned from Start() and includes progress events.
type StartResult struct {
	PID int
	Err error
}

// StartEvent is a progress update during server startup.
type StartEvent struct {
	Stage   string // "jar", "launching", "waiting", "ready", "error"
	Message string
	PID     int
}

// Dir returns the ~/.agentspan/server/ directory.
func Dir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".agentspan", "server")
}

// PIDFile returns the path to the PID file.
func PIDFile() string { return filepath.Join(Dir(), "server.pid") }

// LogFile returns the path to the server log file.
func LogFile() string { return filepath.Join(Dir(), "server.log") }

// JarPath returns the default path for the runtime JAR.
func DefaultJarPath() string { return filepath.Join(Dir(), JarName) }

// ReadPID reads the PID from the PID file. Returns 0 if not found.
func ReadPID() int {
	data, err := os.ReadFile(PIDFile())
	if err != nil {
		return 0
	}
	var pid int
	fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &pid)
	return pid
}

// ProcessRunning returns true if a process with the given PID is running.
func ProcessRunning(pid int) bool {
	if pid <= 0 {
		return false
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	// Signal 0: check if process exists (Unix only — on Windows FindProcess always succeeds)
	return proc.Signal(os.Signal(nil)) == nil
}

// IsRunning returns true if the server process is running and healthy.
func IsRunning() bool {
	pid := ReadPID()
	if pid == 0 || !ProcessRunning(pid) {
		return false
	}
	return HealthCheck("6767") == nil
}

// HealthCheck calls the /health endpoint on the given port.
func HealthCheck(port string) error {
	c := &http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get(fmt.Sprintf("http://localhost:%s/health", port))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	var result struct {
		Healthy bool `json:"healthy"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return err
	}
	if !result.Healthy {
		return fmt.Errorf("server reports unhealthy")
	}
	return nil
}

// EnsureJAR makes sure the JAR file exists at jarPath, downloading if needed.
// progress receives download progress as a 0-100 percentage (-1 = indeterminate).
func EnsureJAR(jarPath string, progress func(pct float64, msg string)) error {
	if jarPath == "" {
		jarPath = DefaultJarPath()
	}
	if err := os.MkdirAll(filepath.Dir(jarPath), 0o755); err != nil {
		return fmt.Errorf("create server dir: %w", err)
	}

	downloadURL := fmt.Sprintf("%s/agentspan-server-latest.jar", S3Bucket)

	// If cached, do a HEAD check for freshness
	if info, err := os.Stat(jarPath); err == nil {
		if progress != nil {
			progress(-1, "Checking for JAR updates...")
		}
		c := &http.Client{Timeout: 15 * time.Second}
		resp, err := c.Head(downloadURL)
		if err != nil {
			// Can't check — use cached
			return nil
		}
		resp.Body.Close()
		if resp.StatusCode == http.StatusOK && resp.ContentLength > 0 && resp.ContentLength == info.Size() {
			return nil // up to date
		}
		if resp.StatusCode == http.StatusNotFound {
			return nil // no remote release, use cached
		}
	}

	// Download
	if progress != nil {
		progress(0, "Downloading server JAR...")
	}
	return downloadJAR(downloadURL, jarPath, progress)
}

func downloadJAR(url, dest string, progress func(float64, string)) error {
	c := &http.Client{Timeout: 10 * time.Minute}
	resp, err := c.Get(url)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed: HTTP %d", resp.StatusCode)
	}

	tmp := dest + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	total := resp.ContentLength
	var written int64
	buf := make([]byte, 32*1024)
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := f.Write(buf[:n]); werr != nil {
				f.Close()
				os.Remove(tmp)
				return fmt.Errorf("write: %w", werr)
			}
			written += int64(n)
			if progress != nil && total > 0 {
				progress(float64(written)/float64(total)*100, fmt.Sprintf("Downloading JAR (%.0f MB / %.0f MB)",
					float64(written)/1024/1024, float64(total)/1024/1024))
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			f.Close()
			os.Remove(tmp)
			return fmt.Errorf("read: %w", err)
		}
	}
	f.Close()

	if err := os.Rename(tmp, dest); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("rename: %w", err)
	}
	return nil
}

// javaCmd returns the java binary path, preferring $JAVA_HOME/bin/java when set.
func javaCmd() string {
	if jh := os.Getenv("JAVA_HOME"); jh != "" {
		p := filepath.Join(jh, "bin", "java")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "java"
}

// CheckJava returns (ok, versionString). ok=true means Java 21+ is available.
// Prefers $JAVA_HOME/bin/java over PATH when JAVA_HOME is set.
func CheckJava() (ok bool, version string) {
	out, err := exec.Command(javaCmd(), "-version").CombinedOutput()
	if err != nil {
		return false, ""
	}

	re := regexp.MustCompile(`version "(\d+[\d._]*)"`)
	matches := re.FindStringSubmatch(string(out))
	if len(matches) < 2 {
		return false, strings.TrimSpace(string(out))
	}
	ver := matches[1]

	major := ver
	if idx := strings.IndexAny(ver, "._"); idx > 0 {
		major = ver[:idx]
	}
	majorNum, err := strconv.Atoi(major)
	if err != nil {
		return false, ver
	}
	return majorNum >= 21, ver
}

// CheckPortFree returns an error if the given port is already in use.
func CheckPortFree(port string) error {
	conn, err := net.DialTimeout("tcp", "127.0.0.1:"+port, time.Second)
	if err == nil {
		conn.Close()
		return fmt.Errorf("port %s is already in use", port)
	}
	return nil
}

// Launch starts the JVM process with the given JAR. It detaches the process
// and writes the PID file. Returns the PID.
// events receives live startup progress messages (may be nil).
func Launch(jarPath string, opts Options, events chan<- StartEvent) (int, error) {
	if opts.Port == "" {
		opts.Port = "6767"
	}
	if jarPath == "" {
		jarPath = DefaultJarPath()
	}

	send := func(stage, msg string, pid int) {
		if events != nil {
			events <- StartEvent{Stage: stage, Message: msg, PID: pid}
		}
	}

	// Pre-flight checks
	if ok, ver := CheckJava(); !ok {
		msg := "Java 21+ is required."
		if ver != "" {
			msg = fmt.Sprintf("Java %s detected but Java 21+ is required.", ver)
		}
		return 0, fmt.Errorf("%s Install from https://adoptium.net/", msg)
	}
	if err := CheckPortFree(opts.Port); err != nil {
		return 0, err
	}

	// Open log file
	if err := os.MkdirAll(Dir(), 0o755); err != nil {
		return 0, fmt.Errorf("create server dir: %w", err)
	}
	logF, err := os.OpenFile(LogFile(), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return 0, fmt.Errorf("open log file: %w", err)
	}

	// Build command
	javaArgs := []string{"-jar", jarPath}
	env := os.Environ()
	if opts.Port != "6767" {
		env = append(env, "SERVER_PORT="+opts.Port)
	}
	if opts.Model != "" {
		env = append(env, "AGENT_DEFAULT_MODEL="+opts.Model)
	}

	proc := exec.Command(javaCmd(), javaArgs...)
	proc.Env = env
	proc.Stdout = logF
	proc.Stderr = logF
	proc.SysProcAttr = sysProcAttr()

	send("launching", fmt.Sprintf("Starting JVM (port %s)...", opts.Port), 0)

	if err := proc.Start(); err != nil {
		logF.Close()
		return 0, fmt.Errorf("start JVM: %w", err)
	}
	pid := proc.Process.Pid

	// Write PID file
	if err := os.WriteFile(PIDFile(), []byte(strconv.Itoa(pid)), 0o644); err != nil {
		logF.Close()
		return pid, fmt.Errorf("write PID: %w", err)
	}

	proc.Process.Release()
	logF.Close()

	send("waiting", fmt.Sprintf("Waiting for server health (PID %d)...", pid), pid)

	// Poll health
	if err := waitHealthy(pid, opts.Port, events); err != nil {
		return pid, err
	}

	send("ready", fmt.Sprintf("Server is ready on port %s", opts.Port), pid)
	return pid, nil
}

func waitHealthy(pid int, port string, events chan<- StartEvent) error {
	deadline := time.Now().Add(StartTimeout)
	c := &http.Client{Timeout: 3 * time.Second}
	healthURL := fmt.Sprintf("http://localhost:%s/health", port)

	for time.Now().Before(deadline) {
		if !ProcessRunning(pid) {
			return fmt.Errorf("server process (PID %d) exited — check logs: %s", pid, LogFile())
		}
		resp, err := c.Get(healthURL)
		if err == nil {
			var result struct {
				Healthy bool `json:"healthy"`
			}
			if json.NewDecoder(resp.Body).Decode(&result) == nil && result.Healthy {
				resp.Body.Close()
				return nil
			}
			resp.Body.Close()
		}
		if events != nil {
			events <- StartEvent{Stage: "waiting", Message: "Still starting...", PID: pid}
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("server did not become healthy within 5 minutes — check logs: %s", LogFile())
}

// Stop sends SIGTERM to the server process and removes the PID file.
func Stop() error {
	pid := ReadPID()
	if pid == 0 {
		return fmt.Errorf("no PID file found — is the server running?")
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("find process %d: %w", pid, err)
	}
	if err := proc.Signal(os.Interrupt); err != nil {
		return fmt.Errorf("signal process %d: %w", pid, err)
	}
	os.Remove(PIDFile())
	return nil
}
