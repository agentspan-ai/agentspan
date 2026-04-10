// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/agentspan-ai/agentspan/cli/internal/progress"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	s3Bucket = "https://agentspan.s3.us-east-2.amazonaws.com"
	jarName  = "agentspan-runtime.jar"
)

var (
	serverPort    string
	serverModel   string
	serverVersion string
	serverJar     string
	serverLocal   bool
	followLogs    bool
	tailLines     int
)

var serverCmd = &cobra.Command{
	Use:   "server",
	Short: "Manage the agent runtime server",
}

var serverStartCmd = &cobra.Command{
	Use:   "start",
	Short: "Download (if needed) and start the agent runtime server",
	RunE:  runServerStart,
}

var serverStopCmd = &cobra.Command{
	Use:   "stop",
	Short: "Stop the running agent runtime server",
	RunE:  runServerStop,
}

var serverLogsCmd = &cobra.Command{
	Use:   "logs",
	Short: "Show server logs",
	RunE:  runServerLogs,
}

func init() {
	serverStartCmd.Flags().StringVarP(&serverPort, "port", "p", "6767", "Server port")
	serverStartCmd.Flags().StringVarP(&serverModel, "model", "m", "", "Default LLM model (e.g. openai/gpt-4o)")
	serverStartCmd.Flags().StringVar(&serverVersion, "version", "", "Specific server version to download (e.g. 0.1.0)")
	serverStartCmd.Flags().StringVar(&serverJar, "jar", "", "Path to a local JAR file to use directly")
	serverStartCmd.Flags().BoolVar(&serverLocal, "local", false, "Use locally built JAR from server/build/libs/")

	serverLogsCmd.Flags().BoolVarP(&followLogs, "follow", "f", false, "Follow log output")
	serverLogsCmd.Flags().IntVarP(&tailLines, "lines", "n", 20, "Number of lines to show before following (with -f)")

	serverCmd.AddCommand(serverStartCmd, serverStopCmd, serverLogsCmd)
	rootCmd.AddCommand(serverCmd)
}

func serverDir() string {
	return filepath.Join(config.ConfigDir(), "server")
}

func pidFile() string {
	return filepath.Join(serverDir(), "server.pid")
}

func logFile() string {
	return filepath.Join(serverDir(), "server.log")
}

func runServerStart(cmd *cobra.Command, args []string) error {
	cmd.SilenceUsage = true
	dir := serverDir()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create server dir: %w", err)
	}

	var jarPath string
	switch {
	case serverJar != "":
		// Use explicit JAR path
		abs, err := filepath.Abs(serverJar)
		if err != nil {
			return fmt.Errorf("resolve JAR path: %w", err)
		}
		if _, err := os.Stat(abs); err != nil {
			return fmt.Errorf("JAR not found: %s", abs)
		}
		jarPath = abs
		color.Green("Using JAR: %s", jarPath)

	case serverLocal:
		// Find locally built JAR by walking up from executable or CWD
		localJar, err := findLocalJAR()
		if err != nil {
			return err
		}
		jarPath = localJar
		color.Green("Using local JAR: %s", jarPath)

	case serverVersion != "":
		jarPath = filepath.Join(dir, fmt.Sprintf("agentspan-runtime-%s.jar", serverVersion))
		if err := ensureVersionedJAR(jarPath, serverVersion); err != nil {
			return err
		}

	default:
		jarPath = filepath.Join(dir, jarName)
		if err := ensureLatestJAR(jarPath); err != nil {
			return err
		}
	}

	// Check if already running
	if pid, err := readPID(); err == nil {
		if processRunning(pid) {
			color.Yellow("Server already running (PID %d). Stop it first with: agentspan server stop", pid)
			return nil
		}
		// Stale PID file
		os.Remove(pidFile())
	}

	// Check if port is already in use before starting the JVM
	if conn, err := net.DialTimeout("tcp", "127.0.0.1:"+serverPort, time.Second); err == nil {
		conn.Close()
		return fmt.Errorf("port %s is already in use. Stop the other process or use --port to choose a different port.", serverPort)
	}

	checkAIProviderKeys()

	// Validate JDK before launching java
	javaOk, javaVersion := checkJava()
	if !javaOk {
		if javaVersion != "" {
			return fmt.Errorf(
				"Java %s detected but Java 21+ is required.\n"+
					"  Install Java 21+: https://adoptium.net/\n"+
					"  Run 'agentspan doctor' for full diagnostics.", javaVersion)
		}
		return fmt.Errorf(
			"Java is not installed. The Agentspan server requires Java 21+.\n" +
				"  Install: https://adoptium.net/\n" +
				"  Run 'agentspan doctor' for full diagnostics.")
	}

	bold := color.New(color.Bold)
	bold.Printf("Starting agent runtime on port %s...\n", serverPort)

	// Build java args
	javaArgs := []string{"-jar", jarPath}

	env := os.Environ()
	if serverPort != "6767" {
		env = append(env, "SERVER_PORT="+serverPort)
	}
	if serverModel != "" {
		env = append(env, "AGENT_DEFAULT_MODEL="+serverModel)
	}

	// Open log file
	logF, err := os.OpenFile(logFile(), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return fmt.Errorf("open log file: %w", err)
	}

	proc := exec.Command("java", javaArgs...)
	proc.Env = env
	proc.Stdout = logF
	proc.Stderr = logF
	proc.SysProcAttr = sysProcAttr()

	if err := proc.Start(); err != nil {
		logF.Close()
		return fmt.Errorf("failed to start server: %w", err)
	}

	// Write PID
	pid := proc.Process.Pid
	if err := os.WriteFile(pidFile(), []byte(strconv.Itoa(pid)), 0o644); err != nil {
		logF.Close()
		return fmt.Errorf("write PID file: %w", err)
	}

	// Detach - release the process so CLI can exit
	proc.Process.Release()
	logF.Close()

	fmt.Printf("Server starting (PID %d)...\n", pid)

	if err := waitForHealthy(pid, serverPort); err != nil {
		return err
	}

	color.Green("Server is ready!")
	fmt.Println()
	fmt.Printf("  Logs: %s\n", logFile())
	fmt.Printf("  URL:  http://localhost:%s\n", serverPort)
	fmt.Println()
	fmt.Println("Use 'agentspan server logs -f' to follow output.")
	return nil
}

func waitForHealthy(pid int, port string) error {
	const (
		timeout      = 5 * time.Minute
		pollInterval = 2 * time.Second
	)

	healthURL := fmt.Sprintf("http://localhost:%s/health", port)
	client := &http.Client{Timeout: 3 * time.Second}
	deadline := time.Now().Add(timeout)

	spinner := progress.NewSpinner("Waiting for server to be ready...")
	spinner.Start()
	defer spinner.Stop()

	for time.Now().Before(deadline) {
		// Fail fast if the process has died
		if !processRunning(pid) {
			return fmt.Errorf("server process exited unexpectedly — check logs: %s", logFile())
		}

		resp, err := client.Get(healthURL)
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

		time.Sleep(pollInterval)
	}

	return fmt.Errorf("server did not become healthy within 5 minutes — check logs: %s", logFile())
}

func runServerStop(cmd *cobra.Command, args []string) error {
	pid, err := readPID()
	if err != nil {
		color.Yellow("No server PID file found. Server may not be running.")
		return nil
	}

	if !processRunning(pid) {
		os.Remove(pidFile())
		color.Yellow("Server process (PID %d) is not running. Cleaned up stale PID file.", pid)
		return nil
	}

	process, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("find process %d: %w", pid, err)
	}

	if err := killProcess(process); err != nil {
		return fmt.Errorf("stop process %d: %w", pid, err)
	}

	os.Remove(pidFile())
	color.Green("Server stopped (PID %d)", pid)
	return nil
}

func runServerLogs(cmd *cobra.Command, args []string) error {
	path := logFile()
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return fmt.Errorf("no log file found at %s", path)
	}

	if !followLogs {
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		fmt.Print(string(data))
		return nil
	}

	// Follow mode: tail -n N -f style
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	// Seek to show only the last N lines before following
	if tailLines > 0 {
		if offset, err := lastNLinesOffset(f, tailLines); err == nil {
			f.Seek(offset, io.SeekStart)
		}
		// On error just follow from start
	}

	buf := make([]byte, 4096)
	for {
		n, err := f.Read(buf)
		if n > 0 {
			fmt.Print(string(buf[:n]))
		}
		if err == io.EOF {
			time.Sleep(200 * time.Millisecond)
			continue
		}
		if err != nil {
			return err
		}
	}
}

// lastNLinesOffset returns the file offset to start reading from to get the last n lines.
func lastNLinesOffset(f *os.File, n int) (int64, error) {
	size, err := f.Seek(0, io.SeekEnd)
	if err != nil {
		return 0, err
	}
	if size == 0 {
		return 0, nil
	}

	const chunkSize = 4096
	found := 0
	offset := size
	buf := make([]byte, chunkSize)

	for offset > 0 {
		read := int64(chunkSize)
		if read > offset {
			read = offset
		}
		offset -= read
		if _, err := f.Seek(offset, io.SeekStart); err != nil {
			return 0, err
		}
		if _, err := io.ReadFull(f, buf[:read]); err != nil {
			return 0, err
		}
		for i := int(read) - 1; i >= 0; i-- {
			if buf[i] == '\n' {
				found++
				if found > n {
					return offset + int64(i) + 1, nil
				}
			}
		}
	}
	return 0, nil
}

// --- Local JAR helpers ---

func findLocalJAR() (string, error) {
	// Try CWD first, then walk up to find 'server/build/libs/agentspan-runtime.jar'
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("get working directory: %w", err)
	}

	// Check common relative paths from likely CWD locations
	candidates := []string{
		filepath.Join(cwd, "server", "build", "libs", jarName),
		filepath.Join(cwd, "build", "libs", jarName),
		filepath.Join(cwd, "..", "server", "build", "libs", jarName),
	}

	// Also walk up from CWD looking for server/build/libs/
	dir := cwd
	for i := 0; i < 5; i++ {
		candidate := filepath.Join(dir, "server", "build", "libs", jarName)
		candidates = append(candidates, candidate)
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return filepath.Abs(c)
		}
	}

	return "", fmt.Errorf("local JAR not found. Build it first with: cd server && ./gradlew build")
}

// --- JAR download helpers ---

func ensureVersionedJAR(jarPath, version string) error {
	if _, err := os.Stat(jarPath); err == nil {
		color.Green("Using cached JAR for version %s", version)
		return nil
	}

	downloadURL := fmt.Sprintf("%s/agentspan-server-%s.jar", s3Bucket, version)
	return downloadJAR(downloadURL, jarPath)
}

func ensureLatestJAR(jarPath string) error {
	downloadURL := fmt.Sprintf("%s/agentspan-server-latest.jar", s3Bucket)

	// If we already have a cached JAR, do a HEAD request to check if remote has changed
	if info, err := os.Stat(jarPath); err == nil {
		httpClient := &http.Client{Timeout: 15 * time.Second}
		resp, err := httpClient.Head(downloadURL)
		if err != nil {
			color.Yellow("Could not check for updates (%v), using cached JAR", err)
			return nil
		}
		resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			// Compare content-length as a simple freshness check
			remoteSize := resp.ContentLength
			if remoteSize > 0 && remoteSize == info.Size() {
				color.Green("Server JAR is up to date")
				return nil
			}
		} else if resp.StatusCode == http.StatusNotFound {
			color.Yellow("No remote release found, using cached JAR")
			return nil
		}
	}

	return downloadJAR(downloadURL, jarPath)
}

func downloadJAR(downloadURL, destPath string) error {
	color.Yellow("Downloading server JAR...")
	fmt.Printf("  URL: %s\n", downloadURL)

	httpClient := &http.Client{
		Timeout: 10 * time.Minute,
	}

	resp, err := httpClient.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed: HTTP %d", resp.StatusCode)
	}

	// Write to temp file first, then rename
	tmpPath := destPath + ".tmp"
	f, err := os.Create(tmpPath)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	pr, bar := progress.NewReader(resp.Body, resp.ContentLength, "Downloading")
	_, err = io.Copy(f, pr)
	f.Close()
	bar.Finish()
	if err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("write JAR: %w", err)
	}

	if err := os.Rename(tmpPath, destPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("rename JAR: %w", err)
	}

	color.Green("Download complete!")
	return nil
}

// --- AI provider check ---

const aiModelsDocURL = "https://github.com/agentspan-ai/agentspan/blob/main/docs/ai-models.md"

func checkAIProviderKeys() {
	hasAny := false
	for _, p := range aiProviders {
		allSet := true
		for _, env := range p.envVars {
			if os.Getenv(env) == "" {
				allSet = false
				break
			}
		}
		if allSet {
			hasAny = true
			break
		}
	}

	// Check provider-specific warnings — only for providers that are actually
	// configured (all required env vars set). Warnings for unconfigured providers
	// are noise; the user hasn't opted in to that provider at all.
	for _, p := range aiProviders {
		if !isProviderConfigured(p) {
			continue
		}
		for _, w := range p.warns {
			if w.condition() {
				warn := color.New(color.FgYellow, color.Bold)
				warn.Printf("WARNING: %s — %s\n", p.name, w.message)
				fmt.Println()
				fmt.Printf("    %s\n", w.fix)
				fmt.Println()
			}
		}
	}

	if hasAny {
		return
	}

	warn := color.New(color.FgYellow, color.Bold)
	warn.Println("WARNING: No AI provider API keys detected!")
	fmt.Println()
	fmt.Println("  The server will start, but agents won't be able to call any LLM")
	fmt.Println("  until you set at least one provider's API key.")
	fmt.Println()
	fmt.Println("  Set one or more of these before starting the server:")
	fmt.Println()
	fmt.Println("    # OpenAI")
	fmt.Println("    export OPENAI_API_KEY=sk-...")
	fmt.Println()
	fmt.Println("    # Anthropic (Claude)")
	fmt.Println("    export ANTHROPIC_API_KEY=sk-ant-...")
	fmt.Println()
	fmt.Println("    # Google Gemini")
	fmt.Println("    export GEMINI_API_KEY=AI...")
	fmt.Println("    export GOOGLE_CLOUD_PROJECT=your-gcp-project-id")
	fmt.Println()
	fmt.Println("  Run 'agentspan doctor' for a full diagnostic.")
	fmt.Printf("  Docs: %s\n", aiModelsDocURL)
	fmt.Println()
}

// --- PID helpers ---

func readPID() (int, error) {
	data, err := os.ReadFile(pidFile())
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(strings.TrimSpace(string(data)))
}
