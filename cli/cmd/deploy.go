// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

// discoveredAgent represents an agent found by the discover subprocess.
type discoveredAgent struct {
	Name      string `json:"name"`
	Framework string `json:"framework"`
}

// deployResult represents the outcome of deploying a single agent.
type deployResult struct {
	AgentName      string  `json:"agent_name"`
	RegisteredName *string `json:"registered_name"`
	Success        bool    `json:"success"`
	Error          *string `json:"error"`
}

// Manifest is the deployment manifest included in the tar (cloud deploys only).
type Manifest struct {
	ManifestVersion string         `json:"manifest_version"`
	Name            string         `json:"name"`
	Version         string         `json:"version"`
	Language        string         `json:"language"`
	RuntimeVersion  string         `json:"runtime_version"`
	EntryPoint      string         `json:"entry_point"`
	AutoStart       bool           `json:"auto_start"`
	Resources       ResourceConfig `json:"resources"`
	Metadata        ManifestMeta   `json:"metadata,omitempty"`
}

// ResourceConfig holds resource allocation settings for cloud deploys.
type ResourceConfig struct {
	CPURequest    string `json:"cpu_request"`
	CPULimit      string `json:"cpu_limit"`
	MemoryRequest string `json:"memory_request"`
	MemoryLimit   string `json:"memory_limit"`
	Replicas      int    `json:"replicas"`
	Timeout       int    `json:"timeout"`
}

// ManifestMeta holds auto-generated metadata for cloud deploys.
type ManifestMeta struct {
	CLIVersion string    `json:"cli_version,omitempty"`
	CreatedAt  time.Time `json:"created_at,omitempty"`
	GitSHA     string    `json:"git_sha,omitempty"`
}

// UploadResponse from the ingest service (cloud deploys only).
type UploadResponse struct {
	DeployID  string `json:"deploy_id"`
	StreamURL string `json:"stream_url"`
	RequestID string `json:"request_id"`
}

// Hardcoded exclusions for tar creation (cloud deploys only).
var defaultExclusions = []string{
	// Version control
	".git",
	".gitignore",
	".gitattributes",
	".svn",
	".hg",

	// AgentSpan state
	".agentspan",

	// Python
	"__pycache__",
	"*.pyc",
	"*.pyo",
	"*.pyd",
	".pytest_cache",
	".mypy_cache",
	".ruff_cache",
	".tox",
	".nox",
	".eggs",
	"*.egg-info",
	".venv",
	"venv",
	"env",

	// Secrets
	".env",
	".env.*",
	"*.pem",
	"*.key",

	// Node/TypeScript
	"node_modules",
	".npm",
	".yarn",
	"dist",
	"build",

	// Java
	"target",
	"*.class",
	"*.jar",
	".gradle",

	// IDE
	".idea",
	".vscode",
	"*.swp",
	"*.swo",

	// OS
	".DS_Store",
	"Thumbs.db",

	// Logs
	"*.log",
	"logs",
}

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy agents from your project to the AgentSpan server",
	Long: `Discover agents in your project and deploy them to the AgentSpan server.

For a local server, this registers the agent workflow definitions so they can
be executed with 'agentspan agent run'. Workers still run on your machine.

For a cloud server, this additionally packages and uploads your code so the
server can run the workers remotely.

Examples:
  agentspan deploy                        # Deploy all agents
  agentspan deploy -a my-agent            # Deploy a specific agent
  agentspan deploy --dry-run              # Package without uploading (cloud only)
`,
	RunE: runDeployCmd,
}

func init() {
	deployCmd.Flags().StringSliceP("agents", "a", nil, "Comma-separated list of agent names to deploy (default: all)")
	deployCmd.Flags().StringP("language", "l", "", "Project language: python or typescript")
	deployCmd.Flags().StringP("package", "p", "", "Package/path to scan for agents")
	deployCmd.Flags().BoolP("yes", "y", false, "Skip confirmation prompt")
	deployCmd.Flags().Bool("json", false, "Output results as JSON")
	deployCmd.Flags().Bool("dry-run", false, "Package code without uploading (cloud targets only)")
	deployCmd.Flags().String("cpu", "100m", "CPU request (cloud targets only)")
	deployCmd.Flags().String("memory", "256Mi", "Memory request (cloud targets only)")
	deployCmd.Flags().Int("replicas", 1, "Number of replicas (cloud targets only)")
	deployCmd.Flags().Int("timeout", 300, "Timeout in seconds (cloud targets only)")
	rootCmd.AddCommand(deployCmd)
}

func runDeployCmd(cmd *cobra.Command, args []string) error {
	// 1. Get working directory
	wd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("get working directory: %w", err)
	}

	// 2. Read flags
	agentNames, _ := cmd.Flags().GetStringSlice("agents")
	languageFlag, _ := cmd.Flags().GetString("language")
	packageFlag, _ := cmd.Flags().GetString("package")
	autoYes, _ := cmd.Flags().GetBool("yes")
	jsonOutput, _ := cmd.Flags().GetBool("json")
	dryRun, _ := cmd.Flags().GetBool("dry-run")
	cpu, _ := cmd.Flags().GetString("cpu")
	memory, _ := cmd.Flags().GetString("memory")
	replicas, _ := cmd.Flags().GetInt("replicas")
	timeout, _ := cmd.Flags().GetInt("timeout")

	// Trim whitespace and filter out empty strings from --agents flag
	{
		clean := agentNames[:0]
		for _, n := range agentNames {
			n = strings.TrimSpace(n)
			if n != "" {
				clean = append(clean, n)
			}
		}
		agentNames = clean
	}

	// 3. Detect language
	language, err := detectLanguage(wd, languageFlag)
	if err != nil {
		return fmt.Errorf("detect language: %w", err)
	}

	// 4. Find runtime binary (for Python)
	pythonBin := ""
	if language == "python" {
		pythonBin = findPythonBinary(wd)
		if pythonBin == "" {
			return fmt.Errorf("no Python interpreter found; install Python or set the PYTHON environment variable")
		}
	}

	// 5. Infer package
	pkg, err := inferPackage(wd, language, packageFlag)
	if err != nil {
		return fmt.Errorf("infer package: %w", err)
	}

	// 6. Load config, build env
	cfg := getConfig()
	if serverURL != "" {
		cfg.ServerURL = serverURL
	}
	env := buildEnv(cfg)

	// 7. Discover agents via subprocess
	ctx := context.Background()
	discovered, err := execDiscover(ctx, env, language, pythonBin, wd, pkg)
	if err != nil {
		return fmt.Errorf("discover agents: %w", err)
	}

	if len(discovered) == 0 {
		hint := "Define agents as module-level variables (e.g., agent = Agent(name=..., ...)).\n" +
			"  Supported: AgentSpan Agent, OpenAI, LangChain, LangGraph, Google ADK.\n" +
			"  Agents inside functions or if __name__ blocks are not discoverable.\n" +
			"  Use --package or --path to point to the right location."
		return fmt.Errorf("no agents found in %q.\n  %s", pkg.Value, hint)
	}

	// Keep the full list for JSON output
	allDiscovered := discovered

	// 8. Filter by --agents
	discovered, err = filterDiscoveredAgents(discovered, agentNames)
	if err != nil {
		return err
	}

	// 9. Show discovery table, prompt confirmation
	if !jsonOutput {
		fmt.Println(formatDiscoveryTable(discovered, pkg.Value))

		if !autoYes {
			fmt.Print("Deploy these agents? [y/N] ")
			var answer string
			fmt.Scanln(&answer)
			answer = strings.TrimSpace(strings.ToLower(answer))
			if answer != "y" && answer != "yes" {
				fmt.Println("Aborted.")
				return nil
			}
		}
	}

	// 10. Deploy definitions via subprocess (always — local and cloud)
	names := make([]string, len(discovered))
	for i, a := range discovered {
		names[i] = a.Name
	}

	results, err := execDeploy(ctx, env, language, pythonBin, wd, pkg, names)
	if err != nil {
		return fmt.Errorf("deploy agents: %w", err)
	}

	// 11. Output definition registration results
	succeeded := 0
	for _, r := range results {
		if r.Success {
			succeeded++
		}
	}

	if jsonOutput {
		out := map[string]interface{}{
			"discovered": allDiscovered,
			"deployed":   results,
			"summary": map[string]int{
				"total":     len(results),
				"succeeded": succeeded,
				"failed":    len(results) - succeeded,
			},
		}
		printJSON(out)
	} else {
		fmt.Println(formatDeployOutput(results))
	}

	// 12. Return error if any definition registration failures
	for _, r := range results {
		if !r.Success {
			return fmt.Errorf("one or more agents failed to deploy")
		}
	}

	// 13. Cloud only: package and upload code so the server can run workers remotely
	if isCloudServer(cfg.ServerURL) {
		if err := uploadAgentCode(wd, language, names, cfg, dryRun, cpu, memory, replicas, timeout); err != nil {
			return fmt.Errorf("code upload failed: %w", err)
		}
	}

	return nil
}

// isCloudServer returns true if the server URL points to a remote (non-local) instance.
func isCloudServer(serverURL string) bool {
	return !strings.Contains(serverURL, "localhost") && !strings.Contains(serverURL, "127.0.0.1")
}

// uploadAgentCode packages the project into a tar.gz and uploads it to the cloud ingest service.
func uploadAgentCode(srcDir, language string, agentNames []string, cfg *config.Config, dryRun bool, cpu, memory string, replicas, timeout int) error {
	ingestURL := strings.TrimRight(cfg.ServerURL, "/")

	manifest := &Manifest{
		ManifestVersion: "1.0",
		Name:            strings.Join(agentNames, ","),
		Version:         "1.0.0",
		Language:        language,
		RuntimeVersion:  defaultRuntimeVersion(language),
		EntryPoint:      defaultEntryPoint(language),
		AutoStart:       true,
		Resources: ResourceConfig{
			CPURequest:    cpu,
			CPULimit:      cpu,
			MemoryRequest: memory,
			MemoryLimit:   memory,
			Replicas:      replicas,
			Timeout:       timeout,
		},
		Metadata: ManifestMeta{
			CLIVersion: Version,
			CreatedAt:  time.Now().UTC(),
			GitSHA:     getGitSHA(srcDir),
		},
	}

	tarPath, err := createTar(srcDir, manifest)
	if err != nil {
		return fmt.Errorf("create tar: %w", err)
	}
	defer os.Remove(tarPath)

	tarInfo, _ := os.Stat(tarPath)
	color.New(color.FgGreen).Printf("Created package: %s (%d bytes)\n", filepath.Base(tarPath), tarInfo.Size())

	if dryRun {
		dstPath := fmt.Sprintf("agentspan-deploy-%s.tar.gz", time.Now().Format("20060102-150405"))
		if err := copyFile(tarPath, dstPath); err != nil {
			return err
		}
		color.New(color.FgYellow).Printf("Dry run: package saved to %s\n", dstPath)
		return nil
	}

	color.New(color.FgCyan).Printf("Uploading code to: %s\n", ingestURL)

	uploadResp, err := uploadPackage(ingestURL, tarPath, cfg)
	if err != nil {
		return fmt.Errorf("upload: %w", err)
	}

	color.New(color.FgGreen).Printf("Deploy ID: %s\n", uploadResp.DeployID)

	streamURL := ingestURL + uploadResp.StreamURL
	return streamDeployProgress(streamURL, cfg)
}

// detectLanguage determines the project language from marker files or the --language flag.
func detectLanguage(dir, override string) (string, error) {
	if override != "" {
		switch strings.ToLower(override) {
		case "python", "py":
			return "python", nil
		case "typescript", "ts":
			return "typescript", nil
		default:
			return "", fmt.Errorf("unsupported language %q (supported: python, typescript)", override)
		}
	}

	pythonMarkers := []string{"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"}
	hasPython := false
	for _, m := range pythonMarkers {
		if _, err := os.Stat(filepath.Join(dir, m)); err == nil {
			hasPython = true
			break
		}
	}

	hasTypeScript := false
	if _, err := os.Stat(filepath.Join(dir, "tsconfig.json")); err == nil {
		hasTypeScript = true
	} else if hasTSDependency(filepath.Join(dir, "package.json")) {
		hasTypeScript = true
	}

	if hasPython && hasTypeScript {
		return "", fmt.Errorf("both Python and TypeScript markers found; use --language to disambiguate")
	}
	if !hasPython && !hasTypeScript {
		return "", fmt.Errorf("no Python or TypeScript project markers found; use --language to specify")
	}
	if hasPython {
		return "python", nil
	}
	return "typescript", nil
}

// hasTSDependency checks if package.json has a typescript-related dependency.
func hasTSDependency(path string) bool {
	data, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	var pkg map[string]interface{}
	if err := json.Unmarshal(data, &pkg); err != nil {
		return false
	}

	tsDeps := []string{"typescript", "tsx", "ts-node"}
	for _, section := range []string{"dependencies", "devDependencies"} {
		deps, ok := pkg[section].(map[string]interface{})
		if !ok {
			continue
		}
		for _, dep := range tsDeps {
			if _, found := deps[dep]; found {
				return true
			}
		}
	}
	return false
}

// packageInfo holds the inferred package/path and how to pass it to the subprocess.
type packageInfo struct {
	Value  string // dotted module name or directory path
	IsPath bool   // true = pass as --path; false = pass as --package
}

// inferPackage determines the package/path to scan for agents.
func inferPackage(dir, language, override string) (packageInfo, error) {
	if override != "" {
		// If override looks like a path (contains / or . prefix), treat as path
		isPath := strings.Contains(override, "/") || strings.HasPrefix(override, ".")
		return packageInfo{Value: override, IsPath: isPath}, nil
	}

	switch language {
	case "python":
		// Try package name from pyproject.toml first
		pkg, err := inferPythonPackage(dir)
		if err == nil {
			return packageInfo{Value: pkg, IsPath: false}, nil
		}
		// Fall back to scanning current directory
		return packageInfo{Value: dir, IsPath: true}, nil
	case "typescript":
		srcDir := filepath.Join(dir, "src")
		if info, err := os.Stat(srcDir); err == nil && info.IsDir() {
			return packageInfo{Value: "./src", IsPath: true}, nil
		}
		return packageInfo{Value: ".", IsPath: true}, nil
	default:
		return packageInfo{}, fmt.Errorf("cannot infer package for language %q", language)
	}
}

// inferPythonPackage reads pyproject.toml to find the project name.
func inferPythonPackage(dir string) (string, error) {
	path := filepath.Join(dir, "pyproject.toml")
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("cannot infer Python package: pyproject.toml not found; use --package")
	}

	// Simple TOML parsing for [project] name = "..."
	name := parsePyprojectName(string(data))
	if name == "" {
		return "", fmt.Errorf("cannot infer Python package: no [project] name in pyproject.toml; use --package")
	}

	// PEP 503: replace hyphens with underscores for import name
	return strings.ReplaceAll(name, "-", "_"), nil
}

// parsePyprojectName extracts the name from the [project] section of a pyproject.toml file.
// This uses simple line-based parsing to avoid a TOML library dependency.
func parsePyprojectName(content string) string {
	inProject := false
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "[project]" {
			inProject = true
			continue
		}
		if inProject {
			// Another section starts
			if strings.HasPrefix(trimmed, "[") {
				return ""
			}
			if strings.HasPrefix(trimmed, "name") {
				parts := strings.SplitN(trimmed, "=", 2)
				if len(parts) == 2 {
					val := strings.TrimSpace(parts[1])
					val = strings.Trim(val, `"'`)
					return val
				}
			}
		}
	}
	return ""
}

// findPythonBinary locates a Python interpreter for the project.
func findPythonBinary(dir string) string {
	// Check PYTHON env var first
	if p := os.Getenv("PYTHON"); p != "" {
		return p
	}

	// Check local virtualenvs
	for _, venv := range []string{".venv", "venv"} {
		candidate := filepath.Join(dir, venv, "bin", "python")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}

	// Fall back to PATH
	for _, name := range []string{"python3", "python"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}

	return ""
}

// runSubprocess executes a command with a 120-second timeout, capturing stdout.
// Stderr is forwarded to os.Stderr. Returns stdout bytes even on non-zero exit if content was produced.
func runSubprocess(ctx context.Context, env []string, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 120*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Env = env
	cmd.Stderr = os.Stderr

	var stdout bytes.Buffer
	cmd.Stdout = &stdout

	err := cmd.Run()
	if err != nil && stdout.Len() > 0 {
		// Return partial output on failure — subprocess may have written results before erroring
		return stdout.Bytes(), err
	}
	if err != nil {
		return nil, fmt.Errorf("run %s: %w", name, err)
	}
	return stdout.Bytes(), nil
}

// buildEnv constructs the environment variables for subprocess calls.
func buildEnv(cfg *config.Config) []string {
	env := os.Environ()
	// Remove existing AGENTSPAN_ vars to avoid duplication
	filtered := make([]string, 0, len(env))
	for _, e := range env {
		if !strings.HasPrefix(e, "AGENTSPAN_") {
			filtered = append(filtered, e)
		}
	}
	filtered = append(filtered, "AGENTSPAN_SERVER_URL="+cfg.ServerURL)
	// Prevent the SDK from auto-starting an embedded server during deploy
	filtered = append(filtered, "AGENTSPAN_AUTO_START_SERVER=false")
	if cfg.APIKey != "" {
		filtered = append(filtered, "AGENTSPAN_API_KEY="+cfg.APIKey)
	}
	return filtered
}

// findTSBinScript locates a cli-bin script by walking up from dir
// to find the project root (where node_modules or cli-bin lives).
func findTSBinScript(dir, name string) (string, error) {
	absDir, _ := filepath.Abs(dir)
	var searched []string

	cur := absDir
	for {
		candidates := []string{
			filepath.Join(cur, "node_modules", "@agentspan", "sdk", "cli-bin", name),
			filepath.Join(cur, "node_modules", "agentspan", "cli-bin", name),
			filepath.Join(cur, "cli-bin", name),
		}
		for _, p := range candidates {
			if _, err := os.Stat(p); err == nil {
				return p, nil
			}
			searched = append(searched, p)
		}
		parent := filepath.Dir(cur)
		if parent == cur {
			break // reached filesystem root
		}
		cur = parent
	}
	return "", fmt.Errorf("cannot find %s; looked in:\n  %s", name, strings.Join(searched, "\n  "))
}

// execDiscover runs the language-specific discover subprocess.
func execDiscover(ctx context.Context, env []string, language, pythonBin, projectDir string, pkg packageInfo) ([]discoveredAgent, error) {
	var data []byte
	var err error

	switch language {
	case "python":
		flag := "--package"
		if pkg.IsPath {
			flag = "--path"
		}
		data, err = runSubprocess(ctx, env, pythonBin, "-m", "agentspan.cli.discover", flag, pkg.Value)
	case "typescript":
		script, findErr := findTSBinScript(projectDir, "discover.ts")
		if findErr != nil {
			return nil, findErr
		}
		data, err = runSubprocess(ctx, env, "npx", "tsx", script, "--path", pkg.Value)
	default:
		return nil, fmt.Errorf("unsupported language for discover: %s", language)
	}

	if err != nil && len(data) == 0 {
		return nil, err
	}

	return parseDiscoveryResult(data)
}

// execDeploy runs the language-specific deploy subprocess.
func execDeploy(ctx context.Context, env []string, language, pythonBin, projectDir string, pkg packageInfo, agentNames []string) ([]deployResult, error) {
	var data []byte
	var err error

	switch language {
	case "python":
		flag := "--package"
		if pkg.IsPath {
			flag = "--path"
		}
		args := []string{"-m", "agentspan.cli.deploy", flag, pkg.Value}
		if len(agentNames) > 0 {
			args = append(args, "--agents", strings.Join(agentNames, ","))
		}
		data, err = runSubprocess(ctx, env, pythonBin, args...)
	case "typescript":
		script, findErr := findTSBinScript(projectDir, "deploy.ts")
		if findErr != nil {
			return nil, findErr
		}
		args := []string{"tsx", script, "--path", pkg.Value}
		if len(agentNames) > 0 {
			args = append(args, "--agents", strings.Join(agentNames, ","))
		}
		data, err = runSubprocess(ctx, env, "npx", args...)
	default:
		return nil, fmt.Errorf("unsupported language for deploy: %s", language)
	}

	if err != nil && len(data) == 0 {
		return nil, err
	}

	return parseDeployResult(data)
}

// parseDiscoveryResult parses JSON output from the discover subprocess.
func parseDiscoveryResult(data []byte) ([]discoveredAgent, error) {
	var agents []discoveredAgent
	if err := json.Unmarshal(data, &agents); err != nil {
		return nil, fmt.Errorf("parse discovery result: %w", err)
	}
	return agents, nil
}

// parseDeployResult parses JSON output from the deploy subprocess.
func parseDeployResult(data []byte) ([]deployResult, error) {
	var results []deployResult
	if err := json.Unmarshal(data, &results); err != nil {
		return nil, fmt.Errorf("parse deploy result: %w", err)
	}
	return results, nil
}

// filterDiscoveredAgents filters agents by the given names, or returns all if names is empty.
func filterDiscoveredAgents(agents []discoveredAgent, names []string) ([]discoveredAgent, error) {
	if len(names) == 0 {
		return agents, nil
	}

	// Deduplicate names while preserving order
	seen := make(map[string]bool, len(names))
	deduped := make([]string, 0, len(names))
	for _, n := range names {
		if !seen[n] {
			seen[n] = true
			deduped = append(deduped, n)
		}
	}
	names = deduped

	agentMap := make(map[string]discoveredAgent)
	for _, a := range agents {
		agentMap[a.Name] = a
	}

	var filtered []discoveredAgent
	var notFound []string
	for _, name := range names {
		if a, ok := agentMap[name]; ok {
			filtered = append(filtered, a)
		} else {
			notFound = append(notFound, name)
		}
	}

	if len(notFound) > 0 {
		available := make([]string, 0, len(agents))
		for _, a := range agents {
			available = append(available, a.Name)
		}
		availStr := strings.Join(available, ", ")
		if len(available) > 10 {
			availStr = strings.Join(available[:10], ", ") + fmt.Sprintf(", ... and %d more", len(available)-10)
		}
		return nil, fmt.Errorf("agent(s) not found: %s (available: %s)", strings.Join(notFound, ", "), availStr)
	}

	return filtered, nil
}

// formatDiscoveryTable formats discovered agents as a table for display.
func formatDiscoveryTable(agents []discoveredAgent, pkg string) string {
	var buf bytes.Buffer

	fmt.Fprintf(&buf, "\nDiscovered %d agent(s) in %s:\n\n", len(agents), pkg)

	w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "NAME\tFRAMEWORK")
	fmt.Fprintln(w, "----\t---------")
	for _, a := range agents {
		fmt.Fprintf(w, "%s\t%s\n", a.Name, a.Framework)
	}
	w.Flush()

	return buf.String()
}

// formatDeployOutput formats deploy results as a colored summary.
func formatDeployOutput(results []deployResult) string {
	var buf bytes.Buffer

	green := color.New(color.FgGreen)
	red := color.New(color.FgRed)

	successes := 0
	failures := 0

	fmt.Fprintln(&buf)
	for _, r := range results {
		if r.Success {
			successes++
			green.Fprintf(&buf, "  ✓ %s", r.AgentName)
			if r.RegisteredName != nil && *r.RegisteredName != "" && *r.RegisteredName != r.AgentName {
				fmt.Fprintf(&buf, " (registered as %s)", *r.RegisteredName)
			}
			fmt.Fprintln(&buf)
		} else {
			failures++
			errMsg := "unknown error"
			if r.Error != nil {
				errMsg = *r.Error
			}
			red.Fprintf(&buf, "  ✗ %s: %s\n", r.AgentName, errMsg)
		}
	}

	fmt.Fprintln(&buf)
	if failures == 0 {
		green.Fprintf(&buf, "All %d agent(s) deployed successfully.\n", successes)
	} else if successes == 0 {
		red.Fprintf(&buf, "All %d agent(s) failed to deploy.\n", failures)
		fmt.Fprintln(&buf)
		fmt.Fprintln(&buf, "Check server status with: agentspan doctor")
	} else {
		fmt.Fprintf(&buf, "%d deployed, %d failed.\n", successes, failures)
	}

	if successes > 0 {
		fmt.Fprintln(&buf)
		fmt.Fprintln(&buf, "Run with: agentspan agent run --name <agent> \"your prompt\"")
	}

	return buf.String()
}

// --- Cloud upload helpers ---

func defaultRuntimeVersion(language string) string {
	switch language {
	case "python":
		return "3.11"
	case "typescript":
		return "20"
	default:
		return "3.11"
	}
}

func defaultEntryPoint(language string) string {
	switch language {
	case "python":
		return "agent.py"
	case "typescript":
		return "src/agent.ts"
	default:
		return "agent.py"
	}
}

func getGitSHA(dir string) string {
	headPath := filepath.Join(dir, ".git", "HEAD")
	data, err := os.ReadFile(headPath)
	if err != nil {
		return ""
	}
	content := strings.TrimSpace(string(data))
	if strings.HasPrefix(content, "ref: ") {
		refPath := filepath.Join(dir, ".git", strings.TrimPrefix(content, "ref: "))
		refData, err := os.ReadFile(refPath)
		if err != nil {
			return ""
		}
		content = strings.TrimSpace(string(refData))
	}
	if len(content) >= 7 {
		return content[:7]
	}
	return content
}

func createTar(sourceDir string, manifest *Manifest) (string, error) {
	tmpFile, err := os.CreateTemp("", "agentspan-deploy-*.tar.gz")
	if err != nil {
		return "", fmt.Errorf("create temp file: %w", err)
	}

	gzWriter := gzip.NewWriter(tmpFile)
	tarWriter := tar.NewWriter(gzWriter)

	// Write manifest.json FIRST
	manifestBytes, _ := json.MarshalIndent(manifest, "", "  ")
	if err := tarWriter.WriteHeader(&tar.Header{
		Name:    "manifest.json",
		Size:    int64(len(manifestBytes)),
		Mode:    0644,
		ModTime: time.Now(),
	}); err != nil {
		return "", err
	}
	if _, err := tarWriter.Write(manifestBytes); err != nil {
		return "", err
	}

	// Walk and add remaining files
	err = filepath.Walk(sourceDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		relPath, _ := filepath.Rel(sourceDir, path)
		if relPath == "." {
			return nil
		}

		// Check exclusions
		if shouldExclude(relPath, info.IsDir()) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		// Handle symlinks
		if info.Mode()&os.ModeSymlink != 0 {
			realPath, err := filepath.EvalSymlinks(path)
			if err != nil {
				return err
			}
			info, err = os.Stat(realPath)
			if err != nil {
				return err
			}
		}

		// Create header with normalized permissions
		header, err := tar.FileInfoHeader(info, "")
		if err != nil {
			return err
		}
		header.Name = relPath

		// Normalize permissions
		if info.IsDir() {
			header.Mode = 0755
		} else {
			header.Mode = 0644
		}

		if err := tarWriter.WriteHeader(header); err != nil {
			return err
		}

		if !info.IsDir() {
			file, err := os.Open(path)
			if err != nil {
				return err
			}
			defer file.Close()
			_, err = io.Copy(tarWriter, file)
			if err != nil {
				return err
			}
		}

		return nil
	})

	if err != nil {
		tmpFile.Close()
		os.Remove(tmpFile.Name())
		return "", err
	}

	tarWriter.Close()
	gzWriter.Close()
	tmpFile.Close()

	return tmpFile.Name(), nil
}

func shouldExclude(path string, isDir bool) bool {
	base := filepath.Base(path)

	for _, pattern := range defaultExclusions {
		if strings.Contains(pattern, "*") {
			matched, _ := filepath.Match(pattern, base)
			if matched {
				return true
			}
		} else {
			if base == pattern {
				return true
			}
			parts := strings.Split(path, string(filepath.Separator))
			for _, part := range parts {
				if part == pattern {
					return true
				}
			}
		}
	}
	return false
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

func uploadPackage(ingestURL, tarPath string, cfg *config.Config) (*UploadResponse, error) {
	file, err := os.Open(tarPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	req, err := http.NewRequest("POST", ingestURL+"/v1/ingest", file)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/octet-stream")
	if cfg.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.APIKey)
	} else {
		if cfg.AuthKey != "" {
			req.Header.Set("X-Auth-Key", cfg.AuthKey)
		}
		if cfg.AuthSecret != "" {
			req.Header.Set("X-Auth-Secret", cfg.AuthSecret)
		}
	}

	client := &http.Client{Timeout: 5 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var result UploadResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return &result, nil
}

func streamDeployProgress(streamURL string, cfg *config.Config) error {
	req, err := http.NewRequest("GET", streamURL, nil)
	if err != nil {
		return err
	}

	req.Header.Set("Accept", "text/event-stream")
	if cfg.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.APIKey)
	}

	client := &http.Client{Timeout: 0} // No timeout for SSE
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("connect to stream: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	scanner := bufio.NewScanner(resp.Body)
	var eventType, eventData string

	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			if eventData != "" {
				printDeployEvent(eventType, eventData)
				eventType, eventData = "", ""
			}
			continue
		}

		if strings.HasPrefix(line, ":") {
			continue
		}

		if strings.HasPrefix(line, "event:") {
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		} else if strings.HasPrefix(line, "data:") {
			eventData = strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		}
	}

	return scanner.Err()
}

func printDeployEvent(eventType, data string) {
	var evt map[string]interface{}
	if err := json.Unmarshal([]byte(data), &evt); err != nil {
		fmt.Printf("[%s] %s\n", eventType, data)
		return
	}

	stage, _ := evt["stage"].(string)
	message, _ := evt["message"].(string)
	progress, _ := evt["progress"].(float64)

	switch eventType {
	case "progress":
		color.New(color.FgCyan).Printf("  [%s] %s (%d%%)\n", stage, message, int(progress))
	case "log":
		color.New(color.FgHiBlack).Printf("  %s\n", message)
	case "error":
		errMsg := ""
		if errData, ok := evt["data"].(map[string]interface{}); ok {
			errMsg, _ = errData["error"].(string)
		}
		color.New(color.FgRed, color.Bold).Printf("  [%s] %s: %s\n", stage, message, errMsg)
	case "complete":
		if stage == "deploy_complete" {
			color.New(color.FgGreen, color.Bold).Println("\n✓ Deployment complete!")
			if deployData, ok := evt["data"].(map[string]interface{}); ok {
				if deployID, ok := deployData["deploy_id"].(string); ok {
					fmt.Printf("  Deploy ID: %s\n", deployID)
				}
				if workflowID, ok := deployData["workflow_id"].(string); ok {
					fmt.Printf("  Workflow ID: %s\n", workflowID)
				}
			}
		} else {
			color.New(color.FgGreen).Printf("  [%s] Complete\n", stage)
		}
	default:
		fmt.Printf("  [%s] %s\n", eventType, truncate(data, 100))
	}
}
