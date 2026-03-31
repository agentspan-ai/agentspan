// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/agentspan/agentspan/cli/config"
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

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy agents from your project to the AgentSpan server",
	RunE:  runDeployCmd,
}

func init() {
	deployCmd.Flags().StringSliceP("agents", "a", nil, "Comma-separated list of agent names to deploy (default: all)")
	deployCmd.Flags().StringP("language", "l", "", "Project language: python or typescript")
	deployCmd.Flags().StringP("package", "p", "", "Package/path to scan for agents")
	deployCmd.Flags().BoolP("yes", "y", false, "Skip confirmation prompt")
	deployCmd.Flags().Bool("json", false, "Output results as JSON")
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

	// 10. Deploy via subprocess
	names := make([]string, len(discovered))
	for i, a := range discovered {
		names[i] = a.Name
	}

	results, err := execDeploy(ctx, env, language, pythonBin, wd, pkg, names)
	if err != nil {
		return fmt.Errorf("deploy agents: %w", err)
	}

	// 11. Output results
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

	// 12. Return error if any failures
	for _, r := range results {
		if !r.Success {
			return fmt.Errorf("one or more agents failed to deploy")
		}
	}

	return nil
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
	Value string // dotted module name or directory path
	IsPath bool  // true = pass as --path; false = pass as --package
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
	if cfg.AuthKey != "" {
		filtered = append(filtered, "AGENTSPAN_AUTH_KEY="+cfg.AuthKey)
	}
	if cfg.AuthSecret != "" {
		filtered = append(filtered, "AGENTSPAN_AUTH_SECRET="+cfg.AuthSecret)
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
