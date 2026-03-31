// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

// ── Flags ───────────────────────────────────────────────────────────────────

var (
	skillModel       string
	skillAgentModels []string
	skillSearchPaths []string
	skillParams      []string
	skillTimeout     int
	skillStream      bool
)

// ── Commands ────────────────────────────────────────────────────────────────

var skillCmd = &cobra.Command{
	Use:   "skill",
	Short: "Run, load, or serve an agentskills.io skill directory",
}

var skillRunCmd = &cobra.Command{
	Use:   "run <path> <prompt>",
	Short: "Run a skill directory with a prompt (ephemeral execution)",
	Long: `Read a skill directory, package its contents, and start an ephemeral
agent execution on the server. Streams events by default.`,
	Args: cobra.MinimumNArgs(2),
	RunE: runSkillRun,
}

var skillLoadCmd = &cobra.Command{
	Use:   "load <path>",
	Short: "Deploy a skill definition to the server",
	Long: `Read a skill directory, package its contents, and compile it on the
server for later execution via 'agentspan agent run --name <skill>'.`,
	Args: cobra.ExactArgs(1),
	RunE: runSkillLoad,
}

var skillServeCmd = &cobra.Command{
	Use:   "serve <path>",
	Short: "Start workers for a skill's scripts (placeholder)",
	Args:  cobra.ExactArgs(1),
	RunE:  runSkillServe,
}

func init() {
	// skill run flags
	skillRunCmd.Flags().StringVar(&skillModel, "model", "", "Orchestrator and default model (required)")
	skillRunCmd.Flags().StringArrayVar(&skillAgentModels, "agent-model", nil, "Sub-agent model override (name=model, repeatable)")
	skillRunCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")
	skillRunCmd.Flags().StringArrayVar(&skillParams, "param", nil, "Skill parameter override (key=value, repeatable)")
	skillRunCmd.Flags().IntVar(&skillTimeout, "timeout", 300, "Execution timeout in seconds")
	skillRunCmd.Flags().BoolVar(&skillStream, "stream", false, "Stream SSE events in real-time")

	// skill load flags
	skillLoadCmd.Flags().StringVar(&skillModel, "model", "", "Orchestrator and default model (required)")
	skillLoadCmd.Flags().StringArrayVar(&skillAgentModels, "agent-model", nil, "Sub-agent model override (name=model, repeatable)")
	skillLoadCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")

	// Wire up command tree
	skillCmd.AddCommand(skillRunCmd)
	skillCmd.AddCommand(skillLoadCmd)
	skillCmd.AddCommand(skillServeCmd)
	rootCmd.AddCommand(skillCmd)
}

// ── Run ─────────────────────────────────────────────────────────────────────

func runSkillRun(cmd *cobra.Command, args []string) error {
	skillPath := args[0]
	prompt := strings.Join(args[1:], " ")

	if skillModel == "" {
		return fmt.Errorf("--model is required for skill run")
	}

	// Parse --param flags and format prompt
	params, err := parseParamFlags(skillParams)
	if err != nil {
		return err
	}
	prompt = formatPromptWithParams(prompt, params)

	payload, skillName, err := buildSkillPayload(skillPath)
	if err != nil {
		return err
	}

	// Add prompt to payload
	payload["prompt"] = prompt

	bold := color.New(color.Bold)
	bold.Printf("Starting skill: %s\n", skillName)

	cfg := getConfig()
	c := newClient(cfg)

	// Start workers for read_skill_file and script tools BEFORE the execution
	config, _ := payload["config"].(map[string]interface{})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	startSkillWorkers(ctx, c, skillName, skillPath, config)

	// Framework agents use top-level "framework" + "rawConfig", not "agentConfig"
	startPayload := map[string]interface{}{
		"framework": "skill",
		"rawConfig": config,
		"prompt":    prompt,
	}

	resp, err := c.StartFramework(startPayload)
	if err != nil {
		return fmt.Errorf("failed to start skill: %w", err)
	}

	fmt.Printf("Skill: %s (Execution: %s)\n", resp.AgentName, resp.ExecutionID)

	var runErr error
	if skillStream {
		fmt.Println()
		runErr = streamExecution(c, resp.ExecutionID, "")
	} else {
		runErr = pollExecution(c, resp.ExecutionID, time.Duration(skillTimeout)*time.Second)
	}

	cancel() // stop workers
	return runErr
}

// ── Load ────────────────────────────────────────────────────────────────────

func runSkillLoad(cmd *cobra.Command, args []string) error {
	skillPath := args[0]

	if skillModel == "" {
		return fmt.Errorf("--model is required for skill load")
	}

	payload, skillName, err := buildSkillPayload(skillPath)
	if err != nil {
		return err
	}

	bold := color.New(color.Bold)
	bold.Printf("Loading skill: %s\n", skillName)

	cfg := getConfig()
	c := newClient(cfg)

	agentConfig := map[string]interface{}{
		"framework": "skill",
		"rawConfig": payload["config"],
	}

	result, err := c.Compile(agentConfig)
	if err != nil {
		return fmt.Errorf("failed to load skill: %w", err)
	}

	color.Green("Skill %s loaded successfully.", skillName)
	printJSON(result)
	return nil
}

// ── Serve ───────────────────────────────────────────────────────────────────

func runSkillServe(cmd *cobra.Command, args []string) error {
	skillPath := args[0]

	absPath, err := filepath.Abs(skillPath)
	if err != nil {
		return fmt.Errorf("resolve path: %w", err)
	}

	// Verify it's a valid skill directory
	if _, err := os.Stat(filepath.Join(absPath, "SKILL.md")); os.IsNotExist(err) {
		return fmt.Errorf("directory %q is not a valid skill: SKILL.md not found", absPath)
	}

	fmt.Println("Workers for skill scripts must be started via the SDK:")
	fmt.Printf("  from agentspan.agents import skill; rt.serve(skill('%s'))\n", absPath)
	return nil
}

// ── Poll ────────────────────────────────────────────────────────────────────

func pollExecution(c *client.Client, executionID string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	interval := 2 * time.Second

	for {
		if time.Now().After(deadline) {
			return fmt.Errorf("execution %s timed out after %v", executionID, timeout)
		}

		status, err := c.Status(executionID)
		if err != nil {
			return fmt.Errorf("failed to get status: %w", err)
		}

		statusStr, _ := status["status"].(string)
		switch statusStr {
		case "COMPLETED":
			color.Green("Execution %s completed.", executionID)
			if output, ok := status["output"]; ok {
				cleaned := stripNulls(output)
				// Check for empty result
				if m, ok := cleaned.(map[string]interface{}); ok {
					result, _ := m["result"].(string)
					if result == "" || result == "{}" {
						color.Yellow("\nWarning: agent returned an empty result. This can happen when the model runs out of context on long conversations. Try a larger model (e.g. --model anthropic/claude-sonnet-4-6).")
						return nil
					}
				}
				fmt.Println()
				printJSON(cleaned)
			}
			return nil
		case "FAILED", "TERMINATED", "TIMED_OUT":
			color.Red("Execution %s %s.", executionID, strings.ToLower(statusStr))
			if output, ok := status["output"]; ok {
				printJSON(stripNulls(output))
			}
			return fmt.Errorf("execution %s", strings.ToLower(statusStr))
		case "PAUSED":
			color.Yellow("Execution %s is paused (waiting for input).", executionID)
			fmt.Println("Respond with: agentspan agent respond", executionID, "--approve")
			return nil
		default:
			// RUNNING or other transient state — keep polling
			time.Sleep(interval)
		}
	}
}

// stripNulls recursively removes null values from maps for cleaner output.
func stripNulls(v interface{}) interface{} {
	switch val := v.(type) {
	case map[string]interface{}:
		clean := make(map[string]interface{})
		for k, v2 := range val {
			if v2 == nil {
				continue
			}
			clean[k] = stripNulls(v2)
		}
		return clean
	case []interface{}:
		out := make([]interface{}, 0, len(val))
		for _, item := range val {
			out = append(out, stripNulls(item))
		}
		return out
	default:
		return v
	}
}

// ── Skill Workers ───────────────────────────────────────────────────────────

// startSkillWorkers launches background goroutines that poll for and execute
// skill worker tasks (read_skill_file and script tools). Workers run until
// the context is cancelled.
func startSkillWorkers(ctx context.Context, c *client.Client, skillName, skillPath string, config map[string]interface{}) {
	absPath, _ := filepath.Abs(skillPath)

	// Collect resource files for read_skill_file validation
	resourceFiles := make(map[string]bool)
	if rf, ok := config["resourceFiles"].([]interface{}); ok {
		for _, f := range rf {
			if s, ok := f.(string); ok {
				resourceFiles[s] = true
			}
		}
	}
	// Also allow root files (non-agent, non-SKILL.md)
	entries, _ := os.ReadDir(absPath)
	for _, e := range entries {
		if !e.IsDir() && e.Name() != "SKILL.md" && !strings.HasSuffix(e.Name(), "-agent.md") {
			resourceFiles[e.Name()] = true
		}
	}

	// Worker 1: read_skill_file
	taskName := skillName + "__read_skill_file"
	go pollWorker(ctx, c, taskName, func(input map[string]interface{}) (interface{}, error) {
		path, _ := input["path"].(string)
		if path == "" {
			return nil, fmt.Errorf("missing 'path' parameter")
		}
		if !resourceFiles[path] {
			available := make([]string, 0, len(resourceFiles))
			for k := range resourceFiles {
				available = append(available, k)
			}
			return fmt.Sprintf("ERROR: '%s' not found. Available: %v", path, available), nil
		}
		fullPath := filepath.Join(absPath, path)
		data, err := os.ReadFile(fullPath)
		if err != nil {
			return fmt.Sprintf("ERROR: failed to read '%s': %v", path, err), nil
		}
		return string(data), nil
	})

	// Worker 2+: script tools
	if scripts, ok := config["scripts"].(map[string]interface{}); ok {
		for scriptName, scriptInfo := range scripts {
			sName := skillName + "__" + scriptName
			info, _ := scriptInfo.(map[string]interface{})
			filename, _ := info["filename"].(string)
			language, _ := info["language"].(string)
			scriptPath := filepath.Join(absPath, "scripts", filename)

			go pollWorker(ctx, c, sName, func(input map[string]interface{}) (interface{}, error) {
				command, _ := input["command"].(string)
				return executeScript(scriptPath, language, command)
			})
		}
	}
}

// pollWorker polls for tasks of the given type and executes the handler.
func pollWorker(ctx context.Context, c *client.Client, taskType string, handler func(map[string]interface{}) (interface{}, error)) {
	var once sync.Once
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		task, err := c.PollTask(taskType)
		if err != nil || task == nil {
			time.Sleep(100 * time.Millisecond)
			continue
		}

		once.Do(func() {
			color.HiBlack("  Worker registered: %s", taskType)
		})

		taskID, _ := task["taskId"].(string)
		workflowID, _ := task["workflowInstanceId"].(string)
		if taskID == "" {
			continue
		}

		inputData, _ := task["inputData"].(map[string]interface{})
		output, execErr := handler(inputData)

		result := map[string]interface{}{
			"taskId":             taskID,
			"workflowInstanceId": workflowID,
			"workerId":           "agentspan-cli",
			"status":             "COMPLETED",
			"outputData":         map[string]interface{}{"result": output},
		}
		if execErr != nil {
			result["status"] = "FAILED"
			result["reasonForIncompletion"] = execErr.Error()
		}

		if err := c.UpdateTask(result); err != nil {
			color.Red("  Worker error (%s): %v", taskType, err)
		}
	}
}

// executeScript runs a script file with the given language and command args.
func executeScript(scriptPath, language, command string) (interface{}, error) {
	var cmd *exec.Cmd
	switch language {
	case "python":
		cmd = exec.Command("python3", scriptPath, command)
	case "node":
		cmd = exec.Command("node", scriptPath, command)
	case "ruby":
		cmd = exec.Command("ruby", scriptPath, command)
	case "go":
		cmd = exec.Command("go", "run", scriptPath, command)
	default: // bash
		cmd = exec.Command("bash", scriptPath, command)
	}

	out, err := cmd.CombinedOutput()
	if err != nil {
		return string(out), fmt.Errorf("script failed: %w\n%s", err, string(out))
	}
	return string(out), nil
}

// ── Skill Directory Reading ─────────────────────────────────────────────────

// buildSkillPayload reads a skill directory and returns the packaged JSON
// payload and the skill name. The payload matches the raw config format:
//
//	{"config": {...}, "prompt": "..."}
func buildSkillPayload(skillPath string) (map[string]interface{}, string, error) {
	absPath, err := filepath.Abs(skillPath)
	if err != nil {
		return nil, "", fmt.Errorf("resolve path: %w", err)
	}

	// 1. Read and parse SKILL.md
	skillMdContent, err := os.ReadFile(filepath.Join(absPath, "SKILL.md"))
	if err != nil {
		if os.IsNotExist(err) {
			return nil, "", fmt.Errorf("directory %q is not a valid skill: SKILL.md not found", absPath)
		}
		return nil, "", fmt.Errorf("read SKILL.md: %w", err)
	}

	frontmatter, err := parseFrontmatter(string(skillMdContent))
	if err != nil {
		return nil, "", fmt.Errorf("parse SKILL.md frontmatter: %w", err)
	}

	skillName, _ := frontmatter["name"].(string)
	if skillName == "" {
		return nil, "", fmt.Errorf("SKILL.md missing required 'name' field in frontmatter")
	}

	// 2. Discover *-agent.md files
	agentFiles, err := discoverAgentFiles(absPath)
	if err != nil {
		return nil, "", fmt.Errorf("discover agent files: %w", err)
	}

	// 3. Discover scripts
	scripts, err := discoverScripts(absPath)
	if err != nil {
		return nil, "", fmt.Errorf("discover scripts: %w", err)
	}

	// 4. Collect resource files
	resourceFiles, err := collectResourceFiles(absPath)
	if err != nil {
		return nil, "", fmt.Errorf("collect resource files: %w", err)
	}

	// 5. Parse agent model overrides
	agentModels, err := parseAgentModelFlags(skillAgentModels)
	if err != nil {
		return nil, "", err
	}

	// 6. Build config
	config := map[string]interface{}{
		"model":          skillModel,
		"agentModels":    agentModels,
		"skillMd":        string(skillMdContent),
		"agentFiles":     agentFiles,
		"scripts":        scripts,
		"resourceFiles":  resourceFiles,
		"crossSkillRefs": map[string]interface{}{},
	}

	payload := map[string]interface{}{
		"config": config,
	}

	return payload, skillName, nil
}

// parseFrontmatter extracts YAML frontmatter from a SKILL.md string.
// Returns the parsed frontmatter fields as a map. The frontmatter is
// delimited by "---" on its own line.
func parseFrontmatter(content string) (map[string]interface{}, error) {
	content = strings.TrimSpace(content)
	if !strings.HasPrefix(content, "---") {
		return nil, fmt.Errorf("SKILL.md does not start with YAML frontmatter (---)")
	}

	// Find the closing ---
	rest := content[3:] // skip opening ---
	rest = strings.TrimPrefix(rest, "\n")
	endIdx := strings.Index(rest, "\n---")
	if endIdx < 0 {
		return nil, fmt.Errorf("SKILL.md frontmatter not closed (missing second ---)")
	}

	yamlStr := rest[:endIdx]

	var result map[string]interface{}
	if err := yaml.Unmarshal([]byte(yamlStr), &result); err != nil {
		return nil, fmt.Errorf("invalid YAML in frontmatter: %w", err)
	}

	if result == nil {
		result = make(map[string]interface{})
	}

	return result, nil
}

// extractBody returns the markdown body after the frontmatter.
func extractBody(content string) string {
	content = strings.TrimSpace(content)
	if !strings.HasPrefix(content, "---") {
		return content
	}

	rest := content[3:]
	rest = strings.TrimPrefix(rest, "\n")
	endIdx := strings.Index(rest, "\n---")
	if endIdx < 0 {
		return content
	}

	body := rest[endIdx+4:] // skip \n---
	return strings.TrimPrefix(body, "\n")
}

// discoverAgentFiles globs *-agent.md files in the skill directory and
// returns a map of agent name -> file contents.
func discoverAgentFiles(skillDir string) (map[string]string, error) {
	result := make(map[string]string)

	pattern := filepath.Join(skillDir, "*-agent.md")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil, fmt.Errorf("glob agent files: %w", err)
	}

	for _, match := range matches {
		base := filepath.Base(match)
		agentName := strings.TrimSuffix(base, "-agent.md")

		content, err := os.ReadFile(match)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", base, err)
		}

		result[agentName] = string(content)
	}

	return result, nil
}

// scriptInfo holds metadata about a discovered script file.
type scriptInfo struct {
	Filename string `json:"filename"`
	Language string `json:"language"`
}

// discoverScripts lists executable files in the scripts/ directory and
// returns a map of tool name -> script info.
func discoverScripts(skillDir string) (map[string]scriptInfo, error) {
	result := make(map[string]scriptInfo)

	scriptsDir := filepath.Join(skillDir, "scripts")
	entries, err := os.ReadDir(scriptsDir)
	if err != nil {
		if os.IsNotExist(err) {
			return result, nil // scripts/ is optional
		}
		return nil, fmt.Errorf("read scripts directory: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		filename := entry.Name()
		ext := filepath.Ext(filename)
		toolName := strings.TrimSuffix(filename, ext)
		if toolName == "" {
			toolName = filename // no extension
		}

		result[toolName] = scriptInfo{
			Filename: filename,
			Language: detectScriptLanguage(filename),
		}
	}

	return result, nil
}

// detectScriptLanguage maps a filename to its script language based on
// the file extension. No extension defaults to "bash".
func detectScriptLanguage(filename string) string {
	ext := strings.ToLower(filepath.Ext(filename))
	switch ext {
	case ".py":
		return "python"
	case ".sh":
		return "bash"
	case ".js", ".mjs":
		return "node"
	case ".ts":
		return "node"
	case ".rb":
		return "ruby"
	case ".go":
		return "go"
	default:
		return "bash"
	}
}

// collectResourceFiles lists files in references/, examples/, assets/,
// and other root files (excluding SKILL.md and *-agent.md) as relative paths.
func collectResourceFiles(skillDir string) ([]string, error) {
	var result []string

	// Scan resource subdirectories
	for _, subdir := range []string{"references", "examples", "assets"} {
		dir := filepath.Join(skillDir, subdir)
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			continue
		}
		err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if info.IsDir() {
				return nil
			}
			rel, err := filepath.Rel(skillDir, path)
			if err != nil {
				return err
			}
			result = append(result, rel)
			return nil
		})
		if err != nil {
			return nil, fmt.Errorf("walk %s: %w", subdir, err)
		}
	}

	// Collect other root files (excluding SKILL.md, *-agent.md, and scripts/)
	entries, err := os.ReadDir(skillDir)
	if err != nil {
		return nil, fmt.Errorf("read skill directory: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if name == "SKILL.md" {
			continue
		}
		if strings.HasSuffix(name, "-agent.md") {
			continue
		}
		result = append(result, name)
	}

	return result, nil
}

// parseAgentModelFlags parses --agent-model flags in "name=model" format
// into a map.
func parseAgentModelFlags(flags []string) (map[string]string, error) {
	result := make(map[string]string)
	for _, flag := range flags {
		parts := strings.SplitN(flag, "=", 2)
		if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
			return nil, fmt.Errorf("invalid --agent-model value %q: expected name=model", flag)
		}
		result[parts[0]] = parts[1]
	}
	return result, nil
}

// parseParamFlags parses --param flags in "key=value" format into an
// ordered slice of key-value pairs. The slice preserves flag order so the
// prompt prefix is deterministic.
func parseParamFlags(flags []string) ([][2]string, error) {
	var result [][2]string
	for _, flag := range flags {
		parts := strings.SplitN(flag, "=", 2)
		if len(parts) != 2 || parts[0] == "" {
			return nil, fmt.Errorf("invalid --param value %q: expected key=value", flag)
		}
		result = append(result, [2]string{parts[0], parts[1]})
	}
	return result, nil
}

// formatPromptWithParams prepends a [Skill Parameters] block to the prompt
// when params are provided. Returns the original prompt unchanged when
// params is empty.
func formatPromptWithParams(prompt string, params [][2]string) string {
	if len(params) == 0 {
		return prompt
	}
	var sb strings.Builder
	sb.WriteString("[Skill Parameters]\n")
	for _, kv := range params {
		sb.WriteString(kv[0])
		sb.WriteString(": ")
		sb.WriteString(kv[1])
		sb.WriteString("\n")
	}
	sb.WriteString("\n[User Request]\n")
	sb.WriteString(prompt)
	return sb.String()
}
