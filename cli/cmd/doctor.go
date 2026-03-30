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
	"strconv"
	"strings"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

type aiProvider struct {
	name    string
	envVars []string          // all must be set for the provider to be "configured"
	warns   []providerWarning // conditional warnings (checked even if not fully configured)
	models  []string          // example models available with this provider
}

type providerWarning struct {
	condition func() bool
	message   string
	fix       string
}

const ollamaDefaultURL = "http://localhost:11434"

var aiProviders = []aiProvider{
	{
		name:    "OpenAI",
		envVars: []string{"OPENAI_API_KEY"},
		models: []string{
			"openai/gpt-4o",
			"openai/gpt-4o-mini",
			"openai/o1",
			"openai/o3-mini",
		},
	},
	{
		name:    "Anthropic",
		envVars: []string{"ANTHROPIC_API_KEY"},
		models: []string{
			"anthropic/claude-opus-4-20250514",
			"anthropic/claude-sonnet-4-20250514",
			"anthropic/claude-3-5-sonnet-20241022",
		},
	},
	{
		name:    "Google Gemini",
		envVars: []string{"GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT"},
		warns: []providerWarning{
			{
				condition: func() bool {
					return os.Getenv("GEMINI_API_KEY") != "" && os.Getenv("GOOGLE_CLOUD_PROJECT") == ""
				},
				message: "GEMINI_API_KEY is set but GOOGLE_CLOUD_PROJECT is missing",
				fix:     "export GOOGLE_CLOUD_PROJECT=your-gcp-project-id",
			},
		},
		models: []string{
			"google_gemini/gemini-2.0-flash",
			"google_gemini/gemini-1.5-pro",
			"google_gemini/gemini-1.5-flash",
		},
	},
	{
		name:    "Azure OpenAI",
		envVars: []string{"AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"},
		warns: []providerWarning{
			{
				condition: func() bool {
					return os.Getenv("AZURE_OPENAI_API_KEY") != "" && os.Getenv("AZURE_OPENAI_ENDPOINT") == ""
				},
				message: "AZURE_OPENAI_API_KEY is set but AZURE_OPENAI_ENDPOINT is missing",
				fix:     "export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com",
			},
			{
				condition: func() bool {
					return os.Getenv("AZURE_OPENAI_API_KEY") != "" && os.Getenv("AZURE_OPENAI_DEPLOYMENT") == ""
				},
				message: "AZURE_OPENAI_DEPLOYMENT is not set (required to route requests)",
				fix:     "export AZURE_OPENAI_DEPLOYMENT=your-deployment-name",
			},
		},
		models: []string{
			"azure_openai/gpt-4o",
			"azure_openai/gpt-4",
		},
	},
	{
		name:    "AWS Bedrock",
		envVars: []string{"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"},
		warns: []providerWarning{
			{
				condition: func() bool {
					return os.Getenv("AWS_ACCESS_KEY_ID") != "" && os.Getenv("AWS_DEFAULT_REGION") == "" && os.Getenv("AWS_REGION") == ""
				},
				message: "No AWS region set — defaults to us-east-1",
				fix:     "export AWS_DEFAULT_REGION=us-east-1  # or your preferred region",
			},
		},
		models: []string{
			"aws_bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
			"aws_bedrock/meta.llama3-70b-instruct-v1:0",
			"aws_bedrock/amazon.titan-text-express-v1",
		},
	},
	{
		name:    "Mistral",
		envVars: []string{"MISTRAL_API_KEY"},
		models: []string{
			"mistral/mistral-large-latest",
			"mistral/mistral-small-latest",
			"mistral/open-mixtral-8x7b",
		},
	},
	{
		name:    "Cohere",
		envVars: []string{"COHERE_API_KEY"},
		models: []string{
			"cohere/command-r-plus",
			"cohere/command-r",
		},
	},
	{
		name:    "Grok",
		envVars: []string{"XAI_API_KEY"},
		models: []string{
			"grok/grok-3",
			"grok/grok-3-mini",
		},
	},
	{
		name:    "Perplexity",
		envVars: []string{"PERPLEXITY_API_KEY"},
		models: []string{
			"perplexity/sonar-pro",
			"perplexity/sonar",
		},
	},
	{
		name:    "Hugging Face",
		envVars: []string{"HUGGINGFACE_API_KEY"},
		models: []string{
			"hugging_face/meta-llama/Llama-3-70b-chat-hf",
		},
	},
	{
		name:    "Stability AI",
		envVars: []string{"STABILITY_API_KEY"},
		models: []string{
			"stabilityai/sd3.5-large",
			"stabilityai/stable-image-core",
		},
	},
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
		if _, err := os.Stat(filepath.Join(javaHome, "bin", "java")); err != nil {
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

	configured := 0
	for _, p := range aiProviders {
		allSet := isProviderConfigured(p)

		if allSet {
			configured++
			green.Printf("  ✓ %s", p.name)
			dim.Printf("  (%s)\n", strings.Join(p.envVars, ", "))

			// Check for warnings on this provider
			for _, w := range p.warns {
				if w.condition() {
					yellow.Printf("    ⚠ %s\n", w.message)
					fmt.Printf("      %s\n", w.fix)
					issues++
				}
			}

			// Print available models
			for _, m := range p.models {
				dim.Printf("    %s\n", m)
			}
		} else {
			dim.Printf("  - %s", p.name)
			dim.Printf("  (%s)\n", strings.Join(p.envVars, ", "))

			// Still show warnings for partially configured providers
			for _, w := range p.warns {
				if w.condition() {
					yellow.Printf("    ⚠ %s\n", w.message)
					fmt.Printf("      %s\n", w.fix)
					issues++
				}
			}
		}
	}

	// Ollama — special case, no API key, check connectivity
	ollamaURL := os.Getenv("OLLAMA_BASE_URL")
	if ollamaURL == "" {
		ollamaURL = ollamaDefaultURL
	}
	ollamaOk := checkOllama(ollamaURL)
	if ollamaOk {
		configured++
		green.Printf("  ✓ Ollama")
		dim.Printf("  (%s)\n", ollamaURL)
		dim.Println("    ollama/llama3, ollama/mistral, ollama/phi3, ollama/codellama")
	} else if os.Getenv("OLLAMA_BASE_URL") != "" {
		yellow.Printf("  ⚠ Ollama  (not reachable at %s)\n", ollamaURL)
		fmt.Println("    Check that Ollama is running at the configured URL.")
		fmt.Printf("    OLLAMA_BASE_URL=%s\n", ollamaURL)
		issues++
	} else {
		dim.Println("  - Ollama  (not running)")
		dim.Println("    To use a local Ollama instance:")
		dim.Println("      Install: https://ollama.com/download")
		dim.Println("      Default: http://localhost:11434")
		dim.Println("      Custom:  export OLLAMA_BASE_URL=http://your-host:11434")
	}

	fmt.Println()

	// ── Server Connectivity ──────────────────────────────────────
	bold.Println("Server")
	fmt.Println()

	cfg := getConfig()
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

	if configured == 0 {
		red.Println("  ✗ No AI providers configured")
		fmt.Println()
		fmt.Println("  Set at least one provider's API key to get started:")
		fmt.Println()
		fmt.Println("    export OPENAI_API_KEY=sk-...")
		fmt.Println("    export ANTHROPIC_API_KEY=sk-ant-...")
		fmt.Println("    export GEMINI_API_KEY=AI...")
		fmt.Println("    export GOOGLE_CLOUD_PROJECT=your-gcp-project-id")
		fmt.Println()
		issues++
	} else {
		green.Printf("  %d AI provider(s) configured\n", configured)
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

func isProviderConfigured(p aiProvider) bool {
	for _, env := range p.envVars {
		if os.Getenv(env) == "" {
			return false
		}
	}
	return true
}

// checkJava returns (meets_minimum, version_string)
func checkJava() (bool, string) {
	out, err := exec.Command("java", "-version").CombinedOutput()
	if err != nil {
		return false, ""
	}

	// Java version output goes to stderr, but CombinedOutput captures both.
	// Matches patterns like: "21.0.1", "17.0.2", "1.8.0_292"
	re := regexp.MustCompile(`"(\d+[\d._]*)"|version "(\d+[\d._]*)"`)
	matches := re.FindStringSubmatch(string(out))

	version := ""
	if len(matches) > 1 {
		for _, m := range matches[1:] {
			if m != "" {
				version = m
				break
			}
		}
	}

	if version == "" {
		return false, ""
	}

	// Extract major version number
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

func checkOllama(baseURL string) bool {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(baseURL)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
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

