// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

// providerReportLine is one rendered row of the AI Providers section.
type providerReportLine struct {
	level string // "ok" | "warn" | "fail" | "skip" | "info"
	text  string
	extra []string
}

// serverProviderInfo maps the server's provider names to display names and the
// API-key env var used only for shell/server mismatch hints.
var serverProviderInfo = map[string]struct {
	display string
	envVar  string
}{
	"openai":      {"OpenAI", "OPENAI_API_KEY"},
	"anthropic":   {"Anthropic", "ANTHROPIC_API_KEY"},
	"gemini":      {"Google Gemini", "GEMINI_API_KEY"},
	"azureopenai": {"Azure OpenAI", "AZURE_OPENAI_API_KEY"},
	"aws_bedrock": {"AWS Bedrock", "AWS_ACCESS_KEY_ID"},
	"mistral":     {"Mistral", "MISTRAL_API_KEY"},
	"cohere":      {"Cohere", "COHERE_API_KEY"},
	"grok":        {"Grok", "XAI_API_KEY"},
	"perplexity":  {"Perplexity", "PERPLEXITY_API_KEY"},
	"huggingface": {"Hugging Face", "HUGGINGFACE_API_KEY"},
	"ollama":      {"Ollama", ""},
}

// buildProviderReport turns the server's provider status into display lines.
// The client shell's env is consulted only to flag mismatches ("key set here
// but not on the server") — never as evidence that a provider works.
func buildProviderReport(report *client.ProviderStatusReport, getenv func(string) string) []providerReportLine {
	if report.ManagedByHost {
		return []providerReportLine{{
			level: "info",
			text:  "Provider configuration is managed by the host platform",
		}}
	}

	var lines []providerReportLine
	for _, p := range report.Providers {
		display := p.Name
		info, known := serverProviderInfo[p.Name]
		if known {
			display = info.display
		}

		if p.Name == "ollama" {
			if p.Reachable != nil && !*p.Reachable {
				lines = append(lines, providerReportLine{
					level: "fail",
					text:  fmt.Sprintf("%s — server resolved %s, unreachable from the server", display, p.BaseURL),
					extra: []string{
						"The URL must be reachable from the AgentSpan server, which makes the LLM calls.",
						"Fix: agentspan credentials set OLLAMA_BASE_URL <url>  (or set OLLAMA_BASE_URL in the server environment)",
					},
				})
			} else {
				lines = append(lines, providerReportLine{
					level: "ok",
					text:  fmt.Sprintf("%s (%s — reachable from server)", display, p.BaseURL),
				})
			}
			continue
		}

		switch {
		case p.Configured:
			lines = append(lines, providerReportLine{level: "ok", text: display + " — configured on server"})
		case known && info.envVar != "" && getenv(info.envVar) != "":
			lines = append(lines, providerReportLine{
				level: "warn",
				text:  fmt.Sprintf("%s — %s is set in this shell but the server is not configured", display, info.envVar),
				extra: []string{
					fmt.Sprintf("Fix: agentspan credentials set %s <value>  (or restart a local server from this shell)", info.envVar),
				},
			})
		default:
			lines = append(lines, providerReportLine{level: "skip", text: display + " — not configured"})
		}
	}
	return lines
}

// shellProviderKeys lists provider API-key env vars set in this shell (names only).
func shellProviderKeys() []string {
	var keys []string
	for _, info := range serverProviderInfo {
		if info.envVar != "" && os.Getenv(info.envVar) != "" {
			keys = append(keys, info.envVar)
		}
	}
	if os.Getenv("OLLAMA_BASE_URL") != "" {
		keys = append(keys, "OLLAMA_BASE_URL")
	}
	sort.Strings(keys)
	return keys
}

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "Check system dependencies and AI provider configuration",
	RunE:  runDoctor,
}

func init() {
	rootCmd.AddCommand(doctorCmd)
}

func runDoctor(cmd *cobra.Command, args []string) error {
	bold := color.New(color.Bold)
	green := color.New(color.FgGreen)
	yellow := color.New(color.FgYellow)
	red := color.New(color.FgRed)
	dim := color.New(color.Faint)

	issues := 0

	// ── System Dependencies ──────────────────────────────────────
	bold.Println("System Dependencies")
	fmt.Println()

	// Java
	javaOk, javaVersion := checkJava()
	if javaOk {
		green.Printf("  ✓ Java %s\n", javaVersion)
	} else if javaVersion != "" {
		red.Printf("  ✗ Java %s (21+ required)\n", javaVersion)
		fmt.Println("    The server runtime requires Java 21 or later.")
		fmt.Println("    Install: https://adoptium.net/")
		issues++
	} else {
		red.Println("  ✗ Java not found")
		fmt.Println("    The server runtime requires Java 21 or later.")
		fmt.Println("    Install: https://adoptium.net/")
		issues++
	}

	// JAVA_HOME check
	javaHome := os.Getenv("JAVA_HOME")
	if javaHome != "" {
		javaBin := "java"
		if runtime.GOOS == "windows" {
			javaBin = "java.exe"
		}
		if _, err := os.Stat(filepath.Join(javaHome, "bin", javaBin)); err != nil {
			yellow.Println("  ⚠ JAVA_HOME is set but java binary not found there")
			fmt.Printf("    JAVA_HOME=%s\n", javaHome)
			issues++
		}
	}

	// Python (optional, for SDK)
	pythonOk, pythonVersion := checkPython()
	if pythonOk {
		green.Printf("  ✓ Python %s\n", pythonVersion)
	} else if pythonVersion != "" {
		yellow.Printf("  ~ Python %s (3.9+ recommended for the Python SDK)\n", pythonVersion)
	} else {
		dim.Println("  - Python not found (optional, needed for the Python SDK)")
	}

	// Disk space
	dir := serverDir()
	os.MkdirAll(dir, 0o755)
	freeMB := getFreeDiskMB(dir)
	if freeMB >= 0 {
		if freeMB < 500 {
			yellow.Printf("  ⚠ Low disk space: %d MB free in %s\n", freeMB, dir)
			fmt.Println("    The server JAR is ~200 MB. Free up space if downloads fail.")
			issues++
		} else {
			green.Printf("  ✓ Disk space: %d MB free\n", freeMB)
		}
	}

	// Port availability
	port := "6767"
	if serverPort != "" {
		port = serverPort
	}
	if isPortAvailable(port) {
		green.Printf("  ✓ Port %s is available\n", port)
	} else {
		yellow.Printf("  ~ Port %s is in use (server may already be running)\n", port)
	}

	// Server JAR
	jarPath := filepath.Join(dir, jarName)
	if info, err := os.Stat(jarPath); err == nil {
		sizeMB := float64(info.Size()) / 1024 / 1024
		green.Printf("  ✓ Server JAR cached (%.0f MB)\n", sizeMB)
	} else {
		dim.Println("  - Server JAR not downloaded yet (will download on first start)")
	}

	fmt.Println()

	// ── AI Providers ─────────────────────────────────────────────
	bold.Println("AI Providers")
	fmt.Println()

	// Providers are configured on and dialed by the SERVER. Ask it; never
	// present this shell's env as provider status.
	cfg := getConfig()
	configured := 0
	providerStatusGap := "" // non-empty when the server's provider status is unavailable
	report, perr := newClient(cfg).GetProviderStatus()
	switch {
	case perr == nil:
		for _, l := range buildProviderReport(report, os.Getenv) {
			switch l.level {
			case "ok":
				configured++
				green.Printf("  ✓ %s\n", l.text)
			case "warn":
				yellow.Printf("  ⚠ %s\n", l.text)
				issues++
			case "fail":
				red.Printf("  ✗ %s\n", l.text)
				issues++
			case "skip":
				dim.Printf("  - %s\n", l.text)
			case "info":
				configured++ // host-managed counts as configured
				dim.Printf("  %s\n", l.text)
			}
			for _, e := range l.extra {
				fmt.Printf("      %s\n", e)
			}
		}
	case strings.Contains(perr.Error(), "HTTP 404"):
		// Older server without the status endpoint — be explicit that the
		// shell env below is NOT the server's view.
		providerStatusGap = "this server version does not report provider status"
		dim.Println("  - Server does not report provider status (older server).")
		if keys := shellProviderKeys(); len(keys) > 0 {
			dim.Printf("    Keys set in this shell (may not reflect the server): %s\n", strings.Join(keys, ", "))
		}
	default:
		providerStatusGap = "server not reachable"
		yellow.Printf("  ⚠ Provider status unknown — server not reachable at %s\n", cfg.ServerURL)
		fmt.Println("    Providers are configured on the server; doctor cannot check them from this machine.")
		if cfg.IsLocalhost() {
			if keys := shellProviderKeys(); len(keys) > 0 {
				dim.Printf("    Keys set in this shell (seeded into a local server at its next start): %s\n",
					strings.Join(keys, ", "))
			}
		}
		issues++
	}

	fmt.Println()

	// ── Server Connectivity ──────────────────────────────────────
	bold.Println("Server")
	fmt.Println()

	serverAddr := cfg.ServerURL
	serverOk := checkServer(serverAddr)
	if serverOk {
		green.Printf("  ✓ Server reachable at %s\n", serverAddr)
	} else {
		dim.Printf("  - Server not running at %s\n", serverAddr)
		dim.Println("    Start with: agentspan server start")
	}

	fmt.Println()

	// ── Summary ──────────────────────────────────────────────────
	bold.Println("Summary")
	fmt.Println()

	if providerStatusGap != "" {
		yellow.Printf("  ⚠ Provider status unknown (%s)\n", providerStatusGap)
	} else if configured == 0 {
		red.Println("  ✗ No AI providers configured on the server")
		fmt.Println()
		fmt.Println("  Configure at least one provider on the server:")
		fmt.Println()
		fmt.Println("    agentspan credentials set OPENAI_API_KEY sk-...")
		fmt.Println("    agentspan credentials set ANTHROPIC_API_KEY sk-ant-...")
		fmt.Println("    # or export the variable in the server's environment before it starts")
		fmt.Println()
		issues++
	} else {
		green.Printf("  %d AI provider(s) configured on the server\n", configured)
	}

	if issues == 0 {
		fmt.Println()
		green.Println("  Everything looks good!")
	} else {
		fmt.Printf("\n  %d issue(s) found — see above for details.\n", issues)
	}

	fmt.Printf("\n  Docs: %s\n\n", aiModelsDocURL)

	return nil
}

// javaExe returns the java binary path, preferring $JAVA_HOME/bin/java when set.
func javaExe() string {
	if jh := os.Getenv("JAVA_HOME"); jh != "" {
		p := filepath.Join(jh, "bin", "java")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "java"
}

// checkJava returns (meets_minimum, version_string).
// Prefers $JAVA_HOME/bin/java over PATH when JAVA_HOME is set.
func checkJava() (bool, string) {
	out, err := exec.Command(javaExe(), "-version").CombinedOutput()
	if err != nil {
		return false, ""
	}

	// Java version output goes to stderr, but CombinedOutput captures both.
	// Matches patterns like: "21.0.1", "17.0.2", "1.8.0_292"
	re := regexp.MustCompile(`version "(\d+[\d._]*)"`)
	matches := re.FindStringSubmatch(string(out))
	if len(matches) < 2 {
		return false, ""
	}
	version := matches[1]

	// Extract major version number; compare numerically so Java 26+ is accepted.
	major := version
	if idx := strings.IndexAny(version, "._"); idx > 0 {
		major = version[:idx]
	}

	majorNum, err := strconv.Atoi(major)
	if err != nil {
		return false, version
	}

	return majorNum >= 21, version
}

// checkPython returns (meets_minimum, version_string)
func checkPython() (bool, string) {
	for _, bin := range []string{"python3", "python"} {
		out, err := exec.Command(bin, "--version").Output()
		if err != nil {
			continue
		}

		// "Python 3.12.1"
		parts := strings.Fields(strings.TrimSpace(string(out)))
		if len(parts) < 2 {
			continue
		}
		version := parts[1]

		// Extract major.minor
		segments := strings.SplitN(version, ".", 3)
		if len(segments) < 2 {
			return false, version
		}
		major, err1 := strconv.Atoi(segments[0])
		minor, err2 := strconv.Atoi(segments[1])
		if err1 != nil || err2 != nil {
			return false, version
		}

		return major > 3 || (major == 3 && minor >= 9), version
	}
	return false, ""
}

func isPortAvailable(port string) bool {
	ln, err := net.Listen("tcp", ":"+port)
	if err != nil {
		return false
	}
	ln.Close()
	return true
}

func checkServer(baseURL string) bool {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(baseURL + "/health")
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}
