// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	pathpkg "path"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	cliConfig "github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

// ── Flags ───────────────────────────────────────────────────────────────────

var (
	skillModel              string
	skillAgentModels        []string
	skillSearchPaths        []string
	skillParams             []string
	skillTimeout            int
	skillStream             bool
	skillVersion            string
	skillAllVersions        bool
	skillDeleteYes          bool
	skillScriptTimeout      int
	skillScriptOutputLimit  int
	skillWorkspace          string
	skillNoWorkspace        bool
	skillFileSystems        []string
	skillWorkspaceFileLimit int
)

// ── Commands ────────────────────────────────────────────────────────────────

var skillCmd = &cobra.Command{
	Use:   "skill",
	Short: "Run, register, load, or serve agentskills.io skills",
}

var skillRunCmd = &cobra.Command{
	Use:   "run <path-or-name> <prompt>",
	Short: "Run a local or server-registered skill with a prompt",
	Long: `Run a local skill directory or a server-registered skill by name.
Registered skills are downloaded into ~/.agentspan/skills and reused until
their server checksum changes. Streams events by default.`,
	Args: cobra.MinimumNArgs(2),
	RunE: runSkillRun,
}

var skillLoadCmd = &cobra.Command{
	Use:   "load <path>",
	Short: "Deploy a skill definition to the server",
	Long: `Read a skill directory, package its contents, and deploy it on the
server for later execution via 'agentspan agent run --name <skill>'.`,
	Args: cobra.ExactArgs(1),
	RunE: runSkillLoad,
}

var skillServeCmd = &cobra.Command{
	Use:   "serve <path-or-name>",
	Short: "Start workers for a skill's scripts and resource files",
	Args:  cobra.ExactArgs(1),
	RunE:  runSkillServe,
}

var skillRegisterCmd = &cobra.Command{
	Use:   "register <path>",
	Short: "Upload and register a skill package on the server",
	Long: `Read a skill directory, package the full folder as an immutable
server-side artifact, and register it for UI browsing and later execution.`,
	Args: cobra.ExactArgs(1),
	RunE: runSkillRegister,
}

var skillListCmd = &cobra.Command{
	Use:   "list",
	Short: "List server-registered skills",
	Args:  cobra.NoArgs,
	RunE:  runSkillList,
}

var skillGetCmd = &cobra.Command{
	Use:   "get <name> [version]",
	Short: "Show a server-registered skill",
	Args:  cobra.RangeArgs(1, 2),
	RunE:  runSkillGet,
}

var skillPullCmd = &cobra.Command{
	Use:   "pull <name> [destination]",
	Short: "Download a server-registered skill package",
	Args:  cobra.RangeArgs(1, 2),
	RunE:  runSkillPull,
}

var skillDeleteCmd = &cobra.Command{
	Use:   "delete <name> [version]",
	Short: "Delete a server-registered skill version",
	Args:  cobra.RangeArgs(1, 2),
	RunE:  runSkillDelete,
}

func init() {
	// skill run flags
	skillRunCmd.Flags().StringVar(&skillModel, "model", "", "Orchestrator and default model (required)")
	skillRunCmd.Flags().StringArrayVar(&skillAgentModels, "agent-model", nil, "Sub-agent model override (name=model, repeatable)")
	skillRunCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")
	skillRunCmd.Flags().StringArrayVar(&skillParams, "param", nil, "Skill parameter override (key=value, repeatable)")
	skillRunCmd.Flags().IntVar(&skillTimeout, "timeout", 300, "Execution timeout in seconds")
	skillRunCmd.Flags().BoolVar(&skillStream, "stream", false, "Stream SSE events in real-time")
	skillRunCmd.Flags().StringVar(&skillVersion, "version", "", "Registered skill version or checksum prefix")
	skillRunCmd.Flags().IntVar(&skillScriptTimeout, "script-timeout", 300, "Skill script timeout in seconds")
	skillRunCmd.Flags().IntVar(&skillScriptOutputLimit, "script-output-limit", 10*1024*1024, "Maximum bytes captured from skill script output")
	skillRunCmd.Flags().StringVar(&skillWorkspace, "workspace", ".", "Workspace directory exposed to workspace tools")
	skillRunCmd.Flags().BoolVar(&skillNoWorkspace, "no-workspace", false, "Disable exposing the current workspace")
	skillRunCmd.Flags().StringArrayVar(&skillFileSystems, "filesystem", nil, "Additional read-only filesystem root name=path (repeatable)")
	skillRunCmd.Flags().IntVar(&skillWorkspaceFileLimit, "workspace-file-limit", 1024*1024, "Maximum bytes returned by workspace file tools")

	// skill load flags
	skillLoadCmd.Flags().StringVar(&skillModel, "model", "", "Orchestrator and default model (required)")
	skillLoadCmd.Flags().StringArrayVar(&skillAgentModels, "agent-model", nil, "Sub-agent model override (name=model, repeatable)")
	skillLoadCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")

	// skill serve flags
	skillServeCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")
	skillServeCmd.Flags().StringVar(&skillVersion, "version", "", "Registered skill version or checksum prefix")
	skillServeCmd.Flags().IntVar(&skillScriptTimeout, "script-timeout", 300, "Skill script timeout in seconds")
	skillServeCmd.Flags().IntVar(&skillScriptOutputLimit, "script-output-limit", 10*1024*1024, "Maximum bytes captured from skill script output")
	skillServeCmd.Flags().StringVar(&skillWorkspace, "workspace", ".", "Workspace directory exposed to workspace tools")
	skillServeCmd.Flags().BoolVar(&skillNoWorkspace, "no-workspace", false, "Disable exposing the current workspace")
	skillServeCmd.Flags().StringArrayVar(&skillFileSystems, "filesystem", nil, "Additional read-only filesystem root name=path (repeatable)")
	skillServeCmd.Flags().IntVar(&skillWorkspaceFileLimit, "workspace-file-limit", 1024*1024, "Maximum bytes returned by workspace file tools")

	// skill register flags
	skillRegisterCmd.Flags().StringVar(&skillModel, "model", "", "Orchestrator and default model")
	skillRegisterCmd.Flags().StringArrayVar(&skillAgentModels, "agent-model", nil, "Sub-agent model override (name=model, repeatable)")
	skillRegisterCmd.Flags().StringArrayVar(&skillSearchPaths, "search-path", nil, "Cross-skill search directory (repeatable)")
	skillRegisterCmd.Flags().StringVar(&skillVersion, "version", "", "Optional skill version label (defaults to content hash prefix)")

	// skill list flags
	skillListCmd.Flags().BoolVar(&skillAllVersions, "all-versions", false, "List all versions instead of only latest")

	// skill get / pull flags
	skillGetCmd.Flags().StringVar(&skillVersion, "version", "", "Skill version or checksum prefix")
	skillPullCmd.Flags().StringVar(&skillVersion, "version", "", "Skill version or checksum prefix")
	skillDeleteCmd.Flags().StringVar(&skillVersion, "version", "", "Skill version or checksum prefix")
	skillDeleteCmd.Flags().BoolVar(&skillDeleteYes, "yes", false, "Confirm deletion without prompting")

	// Wire up command tree
	skillCmd.AddCommand(skillRunCmd)
	skillCmd.AddCommand(skillLoadCmd)
	skillCmd.AddCommand(skillServeCmd)
	skillCmd.AddCommand(skillRegisterCmd)
	skillCmd.AddCommand(skillListCmd)
	skillCmd.AddCommand(skillGetCmd)
	skillCmd.AddCommand(skillPullCmd)
	skillCmd.AddCommand(skillDeleteCmd)
	rootCmd.AddCommand(skillCmd)
}

// ── Run ─────────────────────────────────────────────────────────────────────

func runSkillRun(cmd *cobra.Command, args []string) error {
	skillArg := args[0]
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

	cfg := getConfig()
	c := newClient(cfg)

	skillPath, cleanup, registered, err := materializeSkillArg(c, skillArg)
	if err != nil {
		return err
	}
	defer cleanup()

	payload, skillName, err := buildSkillPayload(skillPath)
	if err != nil {
		return err
	}

	bold := color.New(color.Bold)
	bold.Printf("Starting skill: %s\n", skillName)

	// Start workers for read_skill_file and script tools BEFORE the execution
	config, _ := payload["config"].(map[string]interface{})
	workspaceCfg, err := resolveSkillWorkspaceConfig()
	if err != nil {
		return err
	}
	if workspaceCfg.Enabled {
		config["workspace"] = workspaceCfg.RawConfig()
	}
	if registered != nil {
		if refs, ok := registered.RawConfig["crossSkillRefs"]; ok {
			config["crossSkillRefs"] = refs
		}
		if err := hydrateRegisteredCrossSkillRefs(c, config, map[string]bool{}); err != nil {
			return err
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	startSkillWorkers(ctx, c, skillName, skillPath, config, workspaceCfg)

	// Framework agents use top-level "framework" + "rawConfig", not "agentConfig"
	startPayload := map[string]interface{}{
		"framework": "skill",
		"prompt":    prompt,
	}
	if registered != nil {
		skillRef := map[string]interface{}{
			"name":    registered.Name,
			"version": registered.Version,
			"model":   skillModel,
		}
		if agentModels, ok := config["agentModels"].(map[string]string); ok && len(agentModels) > 0 {
			skillRef["agentModels"] = agentModels
		}
		if workspaceCfg.Enabled {
			skillRef["workspace"] = workspaceCfg.RawConfig()
		}
		paramMap, err := parseParamMap(skillParams)
		if err != nil {
			return err
		}
		if len(paramMap) > 0 {
			skillRef["params"] = paramMap
		}
		startPayload["skillRef"] = skillRef
	} else {
		startPayload["rawConfig"] = stripLocalSkillFields(config)
	}
	if workspaceCfg.Enabled {
		startPayload["context"] = map[string]interface{}{
			"workspace": workspaceCfg.Context(),
		}
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

	deployPayload := map[string]interface{}{
		"framework": "skill",
		"rawConfig": stripLocalSkillFields(payload["config"].(map[string]interface{})),
	}

	result, err := c.DeployFramework(deployPayload)
	if err != nil {
		return fmt.Errorf("failed to load skill: %w", err)
	}

	color.Green("Skill %s loaded successfully.", skillName)
	printJSON(result)
	return nil
}

// ── Serve ───────────────────────────────────────────────────────────────────

func runSkillServe(cmd *cobra.Command, args []string) error {
	skillArg := args[0]

	cfg := getConfig()
	c := newClient(cfg)

	skillPath, cleanup, _, err := materializeSkillArg(c, skillArg)
	if err != nil {
		return err
	}
	defer cleanup()

	payload, skillName, err := buildSkillPayload(skillPath)
	if err != nil {
		return err
	}
	config, _ := payload["config"].(map[string]interface{})
	workspaceCfg, err := resolveSkillWorkspaceConfig()
	if err != nil {
		return err
	}
	if workspaceCfg.Enabled {
		config["workspace"] = workspaceCfg.RawConfig()
	}

	baseCtx := context.Background()
	if cmd != nil && cmd.Context() != nil {
		baseCtx = cmd.Context()
	}
	ctx, stop := signal.NotifyContext(baseCtx, os.Interrupt, syscall.SIGTERM)
	defer stop()

	startSkillWorkers(ctx, c, skillName, skillPath, config, workspaceCfg)
	color.Green("Serving workers for skill %s. Press Ctrl-C to stop.", skillName)
	<-ctx.Done()
	return nil
}

// ── Register / List / Get / Pull ────────────────────────────────────────────

func runSkillRegister(cmd *cobra.Command, args []string) error {
	skillPath := args[0]

	payload, skillName, err := buildSkillPayload(skillPath)
	if err != nil {
		return err
	}
	config := payload["config"].(map[string]interface{})

	packageBytes, fileEntries, err := buildSkillPackage(skillPath)
	if err != nil {
		return err
	}

	skillMd, _ := config["skillMd"].(string)
	frontmatter, _ := parseFrontmatter(skillMd)
	description, _ := frontmatter["description"].(string)

	manifest := map[string]interface{}{
		"name":        skillName,
		"version":     skillVersion,
		"description": description,
		"metadata":    frontmatter["metadata"],
		"model":       skillModel,
		"agentModels": config["agentModels"],
		"files":       fileEntries,
	}

	cfg := getConfig()
	c := newClient(cfg)

	result, err := c.RegisterSkill(manifest, packageBytes)
	if err != nil {
		return fmt.Errorf("failed to register skill: %w", err)
	}

	color.Green("Skill %s registered as version %s.", result.Name, result.Version)
	printJSON(result)
	return nil
}

func runSkillList(cmd *cobra.Command, args []string) error {
	cfg := getConfig()
	c := newClient(cfg)

	skills, err := c.ListSkills(skillAllVersions)
	if err != nil {
		return fmt.Errorf("failed to list skills: %w", err)
	}
	if len(skills) == 0 {
		fmt.Println("No skills registered.")
		return nil
	}

	fmt.Printf("%-28s %-14s %-8s %-7s %-7s %-9s %s\n", "NAME", "VERSION", "FILES", "AGENTS", "SCRIPTS", "RESOURCES", "DESCRIPTION")
	for _, s := range skills {
		fmt.Printf("%-28s %-14s %-8d %-7d %-7d %-9d %s\n",
			s.Name,
			shortVersion(s.Version),
			s.FileCount,
			s.SubAgentCount,
			s.ScriptCount,
			s.ResourceCount,
			s.Description)
	}
	return nil
}

func runSkillGet(cmd *cobra.Command, args []string) error {
	name := args[0]
	version := skillVersion
	if len(args) > 1 {
		version = args[1]
	}

	cfg := getConfig()
	c := newClient(cfg)
	detail, err := c.GetSkill(name, version)
	if err != nil {
		return fmt.Errorf("failed to get skill: %w", err)
	}
	printJSON(detail)
	return nil
}

func runSkillPull(cmd *cobra.Command, args []string) error {
	name := args[0]
	dest := name
	if len(args) > 1 {
		dest = args[1]
	}

	cfg := getConfig()
	c := newClient(cfg)
	detail, err := c.GetSkill(name, skillVersion)
	if err != nil {
		return fmt.Errorf("failed to get skill: %w", err)
	}
	data, err := c.DownloadSkillPackage(name, detail.Version)
	if err != nil {
		return fmt.Errorf("failed to download skill package: %w", err)
	}
	if err := extractSkillPackage(data, dest); err != nil {
		return err
	}
	color.Green("Skill %s@%s pulled to %s.", detail.Name, detail.Version, dest)
	return nil
}

func runSkillDelete(cmd *cobra.Command, args []string) error {
	name := args[0]
	version := skillVersion
	if len(args) > 1 {
		version = args[1]
	}
	if version == "" {
		version = "latest"
	}
	if !skillDeleteYes {
		return fmt.Errorf("refusing to delete %s@%s without --yes", name, version)
	}

	cfg := getConfig()
	c := newClient(cfg)
	if err := c.DeleteSkill(name, version); err != nil {
		return fmt.Errorf("failed to delete skill: %w", err)
	}
	color.Green("Deleted skill %s@%s.", name, version)
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

type skillWorkspaceConfig struct {
	Enabled bool
	Roots   []skillWorkspaceRoot
}

type skillWorkspaceRoot struct {
	Name string
	Path string
	Kind string
}

func (cfg skillWorkspaceConfig) Root(name string) (skillWorkspaceRoot, bool) {
	if name == "" && len(cfg.Roots) > 0 {
		return cfg.Roots[0], true
	}
	for _, root := range cfg.Roots {
		if root.Name == name {
			return root, true
		}
	}
	return skillWorkspaceRoot{}, false
}

func (cfg skillWorkspaceConfig) RawConfig() map[string]interface{} {
	roots := make([]map[string]interface{}, 0, len(cfg.Roots))
	for _, root := range cfg.Roots {
		roots = append(roots, map[string]interface{}{
			"name": root.Name,
			"kind": root.Kind,
		})
	}
	return map[string]interface{}{
		"enabled": cfg.Enabled,
		"roots":   roots,
	}
}

func (cfg skillWorkspaceConfig) Context() map[string]interface{} {
	roots := make([]map[string]interface{}, 0, len(cfg.Roots))
	for _, root := range cfg.Roots {
		roots = append(roots, map[string]interface{}{
			"name": root.Name,
			"kind": root.Kind,
			"path": root.Path,
		})
	}
	return map[string]interface{}{
		"roots": roots,
		"tools": []string{
			"list_workspace_files",
			"read_workspace_file",
			"search_workspace",
			"git_status",
			"git_diff",
		},
	}
}

func resolveSkillWorkspaceConfig() (skillWorkspaceConfig, error) {
	cfg := skillWorkspaceConfig{}
	seen := map[string]bool{}

	addRoot := func(name, pathValue, kind string) error {
		root, err := resolveWorkspaceRoot(name, pathValue, kind)
		if err != nil {
			return err
		}
		if seen[root.Name] {
			return fmt.Errorf("duplicate filesystem root %q", root.Name)
		}
		seen[root.Name] = true
		cfg.Roots = append(cfg.Roots, root)
		return nil
	}

	if !skillNoWorkspace {
		workspacePath := skillWorkspace
		if strings.TrimSpace(workspacePath) == "" {
			workspacePath = "."
		}
		if err := addRoot("workspace", workspacePath, "workspace"); err != nil {
			return cfg, err
		}
	}

	for _, spec := range skillFileSystems {
		name, pathValue, ok := strings.Cut(spec, "=")
		if !ok || strings.TrimSpace(name) == "" || strings.TrimSpace(pathValue) == "" {
			return cfg, fmt.Errorf("invalid --filesystem value %q: expected name=path", spec)
		}
		if err := addRoot(strings.TrimSpace(name), strings.TrimSpace(pathValue), "filesystem"); err != nil {
			return cfg, err
		}
	}

	cfg.Enabled = len(cfg.Roots) > 0
	return cfg, nil
}

func resolveWorkspaceRoot(name, pathValue, kind string) (skillWorkspaceRoot, error) {
	if !regexp.MustCompile(`^[A-Za-z0-9._-]+$`).MatchString(name) {
		return skillWorkspaceRoot{}, fmt.Errorf("invalid filesystem root name %q: use letters, numbers, dot, underscore, or dash", name)
	}
	absPath, err := filepath.Abs(expandUserPath(pathValue))
	if err != nil {
		return skillWorkspaceRoot{}, fmt.Errorf("resolve filesystem root %q: %w", name, err)
	}
	info, err := os.Stat(absPath)
	if err != nil {
		return skillWorkspaceRoot{}, fmt.Errorf("filesystem root %q does not exist: %w", name, err)
	}
	if !info.IsDir() {
		return skillWorkspaceRoot{}, fmt.Errorf("filesystem root %q is not a directory: %s", name, absPath)
	}
	if resolved, err := filepath.EvalSymlinks(absPath); err == nil {
		absPath = resolved
	}
	return skillWorkspaceRoot{Name: name, Path: absPath, Kind: kind}, nil
}

// startSkillWorkers launches background goroutines that poll for and execute
// skill worker tasks (read_skill_file and script tools). Workers run until
// the context is cancelled.
func startSkillWorkers(ctx context.Context, c *client.Client, skillName, skillPath string, config map[string]interface{}, workspaceCfg skillWorkspaceConfig) {
	if localPath, ok := config["_skillPath"].(string); ok && localPath != "" {
		skillPath = localPath
	}
	absPath, _ := filepath.Abs(expandUserPath(skillPath))

	// Collect resource files for read_skill_file validation
	resourceFiles := make(map[string]bool)
	for _, f := range stringSlice(config["resourceFiles"]) {
		resourceFiles[f] = true
	}
	for sectionName := range skillSectionsFromConfig(config) {
		resourceFiles["skill_section:"+sectionName] = true
	}

	// Also allow root files (non-agent, non-SKILL.md)
	if entries, err := os.ReadDir(absPath); err == nil {
		for _, e := range entries {
			if !e.IsDir() && e.Name() != "SKILL.md" && !strings.HasSuffix(e.Name(), "-agent.md") {
				resourceFiles[e.Name()] = true
			}
		}
	}

	if len(resourceFiles) > 0 {
		startReadSkillFileWorker(ctx, c, skillName, absPath, resourceFiles, skillSectionsFromConfig(config))
	}

	// Script tools
	for scriptName, info := range scriptMap(config["scripts"]) {
		sName := skillName + "__" + scriptName
		scriptPath := filepath.Join(absPath, "scripts", info.Filename)

		go pollWorker(ctx, c, sName, func(input map[string]interface{}) (interface{}, error) {
			command, _ := input["command"].(string)
			return executeScript(scriptPath, info.Language, command, workspaceCfg)
		})
	}

	if workspaceCfg.Enabled {
		startWorkspaceWorkers(ctx, c, skillName, workspaceCfg)
	}

	for refName, refConfig := range crossSkillRefMap(config["crossSkillRefs"]) {
		refPath, _ := refConfig["_skillPath"].(string)
		if refPath == "" {
			continue
		}
		startSkillWorkers(ctx, c, skillNameFromConfig(refConfig, refName), refPath, refConfig, workspaceCfg)
	}
}

func startReadSkillFileWorker(ctx context.Context, c *client.Client, skillName, absPath string, resourceFiles map[string]bool, sections map[string]string) {
	taskName := skillName + "__read_skill_file"
	go pollWorker(ctx, c, taskName, func(input map[string]interface{}) (interface{}, error) {
		path, _ := input["path"].(string)
		if path == "" {
			return nil, fmt.Errorf("missing 'path' parameter")
		}
		path = normalizeSkillResourcePath(path)
		if !resourceFiles[path] {
			available := make([]string, 0, len(resourceFiles))
			for k := range resourceFiles {
				available = append(available, k)
			}
			return fmt.Sprintf("ERROR: '%s' not found. Available: %v", path, available), nil
		}
		if strings.HasPrefix(path, "skill_section:") {
			sectionName := strings.TrimPrefix(path, "skill_section:")
			if section, ok := sections[sectionName]; ok {
				return section, nil
			}
			return fmt.Sprintf("ERROR: section '%s' not found", sectionName), nil
		}
		fullPath, err := safeSkillPath(absPath, path)
		if err != nil {
			return fmt.Sprintf("ERROR: %v", err), nil
		}
		data, err := os.ReadFile(fullPath)
		if err != nil {
			return fmt.Sprintf("ERROR: failed to read '%s': %v", path, err), nil
		}
		return string(data), nil
	})
}

func normalizeSkillResourcePath(path string) string {
	if strings.HasPrefix(path, "skill_section:") {
		return path
	}
	return pathpkg.Clean(strings.ReplaceAll(path, "\\", "/"))
}

func startWorkspaceWorkers(ctx context.Context, c *client.Client, skillName string, cfg skillWorkspaceConfig) {
	go pollWorker(ctx, c, skillName+"__list_workspace_files", func(input map[string]interface{}) (interface{}, error) {
		root, err := workspaceRootFromInput(cfg, input)
		if err != nil {
			return nil, err
		}
		pathValue, _ := input["path"].(string)
		pattern, _ := input["glob"].(string)
		limit := intInput(input, "limit", 500, 5000)
		return listWorkspaceFiles(root, pathValue, pattern, limit)
	})

	go pollWorker(ctx, c, skillName+"__read_workspace_file", func(input map[string]interface{}) (interface{}, error) {
		root, err := workspaceRootFromInput(cfg, input)
		if err != nil {
			return nil, err
		}
		pathValue, _ := input["path"].(string)
		if strings.TrimSpace(pathValue) == "" {
			return nil, fmt.Errorf("missing 'path' parameter")
		}
		limit := intInput(input, "limit", skillWorkspaceFileLimit, 5*1024*1024)
		return readWorkspaceFile(root, pathValue, limit)
	})

	go pollWorker(ctx, c, skillName+"__search_workspace", func(input map[string]interface{}) (interface{}, error) {
		root, err := workspaceRootFromInput(cfg, input)
		if err != nil {
			return nil, err
		}
		query, _ := input["query"].(string)
		if query == "" {
			return nil, fmt.Errorf("missing 'query' parameter")
		}
		pathValue, _ := input["path"].(string)
		pattern, _ := input["glob"].(string)
		ignoreCase := boolInput(input, "ignoreCase", true)
		limit := intInput(input, "limit", 100, 1000)
		return searchWorkspace(root, pathValue, pattern, query, ignoreCase, limit)
	})

	go pollWorker(ctx, c, skillName+"__git_status", func(input map[string]interface{}) (interface{}, error) {
		root, err := workspaceRootFromInput(cfg, input)
		if err != nil {
			return nil, err
		}
		return runGitWorkspaceCommand(root, []string{"status", "--short"}, skillWorkspaceFileLimit)
	})

	go pollWorker(ctx, c, skillName+"__git_diff", func(input map[string]interface{}) (interface{}, error) {
		root, err := workspaceRootFromInput(cfg, input)
		if err != nil {
			return nil, err
		}
		args := []string{"diff", "--no-ext-diff", "--color=never"}
		if boolInput(input, "staged", false) {
			args = append(args, "--cached")
		}
		if base, _ := input["base"].(string); strings.TrimSpace(base) != "" {
			args = append(args, strings.TrimSpace(base))
		}
		if pathValue, _ := input["path"].(string); strings.TrimSpace(pathValue) != "" {
			fullPath, err := safeWorkspacePath(root.Path, pathValue)
			if err != nil {
				return nil, err
			}
			rel, err := filepath.Rel(resolvedWorkspaceRootPath(root.Path), fullPath)
			if err != nil {
				return nil, err
			}
			args = append(args, "--", filepath.ToSlash(rel))
		}
		return runGitWorkspaceCommand(root, args, skillWorkspaceFileLimit)
	})
}

func workspaceRootFromInput(cfg skillWorkspaceConfig, input map[string]interface{}) (skillWorkspaceRoot, error) {
	rootName, _ := input["root"].(string)
	root, ok := cfg.Root(rootName)
	if ok {
		return root, nil
	}
	available := make([]string, 0, len(cfg.Roots))
	for _, candidate := range cfg.Roots {
		available = append(available, candidate.Name)
	}
	return skillWorkspaceRoot{}, fmt.Errorf("unknown filesystem root %q; available: %s", rootName, strings.Join(available, ", "))
}

func listWorkspaceFiles(root skillWorkspaceRoot, pathValue, pattern string, limit int) (map[string]interface{}, error) {
	rootPath := resolvedWorkspaceRootPath(root.Path)
	startPath, err := safeWorkspacePath(root.Path, defaultString(pathValue, "."))
	if err != nil {
		return nil, err
	}
	info, err := os.Stat(startPath)
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("path is not a directory: %s", pathValue)
	}

	files := []string{}
	truncated := false
	err = filepath.WalkDir(startPath, func(current string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if current == startPath {
			return nil
		}
		if entry.IsDir() && shouldSkipWorkspaceDir(entry.Name()) {
			return filepath.SkipDir
		}
		if entry.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(rootPath, current)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if !matchesWorkspacePattern(pattern, rel) {
			return nil
		}
		files = append(files, rel)
		if limit > 0 && len(files) >= limit {
			truncated = true
			return filepath.SkipAll
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{
		"root":      root.Name,
		"path":      defaultString(pathValue, "."),
		"files":     files,
		"truncated": truncated,
	}, nil
}

func readWorkspaceFile(root skillWorkspaceRoot, pathValue string, limit int) (map[string]interface{}, error) {
	rootPath := resolvedWorkspaceRootPath(root.Path)
	fullPath, err := safeWorkspacePath(root.Path, pathValue)
	if err != nil {
		return nil, err
	}
	info, err := os.Stat(fullPath)
	if err != nil {
		return nil, err
	}
	if info.IsDir() {
		return nil, fmt.Errorf("path is a directory: %s", pathValue)
	}
	content, truncated, err := readLimitedTextFile(fullPath, limit)
	if err != nil {
		return nil, err
	}
	rel, _ := filepath.Rel(rootPath, fullPath)
	return map[string]interface{}{
		"root":      root.Name,
		"path":      filepath.ToSlash(rel),
		"content":   content,
		"truncated": truncated,
	}, nil
}

func searchWorkspace(root skillWorkspaceRoot, pathValue, pattern, query string, ignoreCase bool, limit int) (map[string]interface{}, error) {
	rootPath := resolvedWorkspaceRootPath(root.Path)
	startPath, err := safeWorkspacePath(root.Path, defaultString(pathValue, "."))
	if err != nil {
		return nil, err
	}
	info, err := os.Stat(startPath)
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("path is not a directory: %s", pathValue)
	}

	needle := query
	if ignoreCase {
		needle = strings.ToLower(needle)
	}
	matches := []map[string]interface{}{}
	truncated := false
	err = filepath.WalkDir(startPath, func(current string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if current == startPath {
			return nil
		}
		if entry.IsDir() && shouldSkipWorkspaceDir(entry.Name()) {
			return filepath.SkipDir
		}
		if entry.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(rootPath, current)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if !matchesWorkspacePattern(pattern, rel) {
			return nil
		}
		content, _, err := readLimitedTextFile(current, skillWorkspaceFileLimit)
		if err != nil || strings.Contains(content, "\x00") {
			return nil
		}
		lines := strings.Split(content, "\n")
		for i, line := range lines {
			haystack := line
			if ignoreCase {
				haystack = strings.ToLower(haystack)
			}
			if strings.Contains(haystack, needle) {
				matches = append(matches, map[string]interface{}{
					"path": rel,
					"line": i + 1,
					"text": trimLongLine(line, 500),
				})
				if limit > 0 && len(matches) >= limit {
					truncated = true
					return filepath.SkipAll
				}
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{
		"root":      root.Name,
		"query":     query,
		"matches":   matches,
		"truncated": truncated,
	}, nil
}

func runGitWorkspaceCommand(root skillWorkspaceRoot, args []string, limit int) (map[string]interface{}, error) {
	timeout := 30 * time.Second
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "git", append([]string{"-C", root.Path}, args...)...)
	output := &limitedOutputBuffer{limit: limit}
	cmd.Stdout = output
	cmd.Stderr = output
	err := cmd.Run()
	out := output.String()
	if ctx.Err() == context.DeadlineExceeded {
		return nil, fmt.Errorf("git command timed out after %s\n%s", timeout, out)
	}
	if err != nil {
		return nil, fmt.Errorf("git command failed: %w\n%s", err, out)
	}
	return map[string]interface{}{
		"root":   root.Name,
		"output": out,
	}, nil
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
func executeScript(scriptPath, language, command string, workspaceCfg skillWorkspaceConfig) (interface{}, error) {
	timeoutSeconds := skillScriptTimeout
	if timeoutSeconds <= 0 {
		timeoutSeconds = 300
	}
	outputLimit := skillScriptOutputLimit
	if outputLimit <= 0 {
		outputLimit = 10 * 1024 * 1024
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSeconds)*time.Second)
	defer cancel()

	var cmd *exec.Cmd
	switch language {
	case "python":
		cmd = buildPythonCmd(ctx, scriptPath, command)
	case "node":
		cmd = exec.CommandContext(ctx, "node", append([]string{scriptPath}, splitCommandArgs(command)...)...)
	case "ruby":
		cmd = exec.CommandContext(ctx, "ruby", append([]string{scriptPath}, splitCommandArgs(command)...)...)
	case "go":
		cmd = exec.CommandContext(ctx, "go", append([]string{"run", scriptPath}, splitCommandArgs(command)...)...)
	case "batch":
		cmd = exec.CommandContext(ctx, "cmd", append([]string{"/c", scriptPath}, splitCommandArgs(command)...)...)
	default: // bash/shell
		cmd = buildShellCmd(ctx, scriptPath, command)
	}

	if skillRoot := skillRootFromScriptPath(scriptPath); skillRoot != "" {
		cmd.Dir = skillRoot
		env := append(os.Environ(), "AGENTSPAN_SKILL_DIR="+skillRoot)
		if workspaceRoot, ok := workspaceCfg.Root("workspace"); ok {
			env = append(env, "AGENTSPAN_WORKSPACE_DIR="+workspaceRoot.Path)
		}
		for _, root := range workspaceCfg.Roots {
			env = append(env, "AGENTSPAN_FILESYSTEM_ROOT_"+filesystemEnvName(root.Name)+"="+root.Path)
		}
		cmd.Env = env
	}

	output := &limitedOutputBuffer{limit: outputLimit}
	cmd.Stdout = output
	cmd.Stderr = output
	err := cmd.Run()
	out := output.String()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return out, fmt.Errorf("script timed out after %ds\n%s", timeoutSeconds, out)
		}
		return out, fmt.Errorf("script failed: %w\n%s", err, out)
	}
	return out, nil
}

// buildPythonCmd returns a command to run a Python script.
// Tries python3 first, falls back to python (Windows ships python, not python3).
func buildPythonCmd(ctx context.Context, scriptPath, command string) *exec.Cmd {
	py := "python3"
	if _, err := exec.LookPath("python3"); err != nil {
		py = "python"
	}
	return exec.CommandContext(ctx, py, append([]string{scriptPath}, splitCommandArgs(command)...)...)
}

// buildShellCmd returns a command to run a shell/bash script.
// On Windows, tries bash (Git Bash / WSL) and falls back to cmd /c.
func buildShellCmd(ctx context.Context, scriptPath, command string) *exec.Cmd {
	if runtime.GOOS != "windows" {
		return exec.CommandContext(ctx, "bash", append([]string{scriptPath}, splitCommandArgs(command)...)...)
	}
	if _, err := exec.LookPath("bash"); err == nil {
		return exec.CommandContext(ctx, "bash", append([]string{scriptPath}, splitCommandArgs(command)...)...)
	}
	return exec.CommandContext(ctx, "cmd", append([]string{"/c", scriptPath}, splitCommandArgs(command)...)...)
}

func skillRootFromScriptPath(scriptPath string) string {
	scriptsDir := filepath.Dir(scriptPath)
	if filepath.Base(scriptsDir) != "scripts" {
		return ""
	}
	return filepath.Dir(scriptsDir)
}

type limitedOutputBuffer struct {
	buf       bytes.Buffer
	limit     int
	truncated bool
}

func (b *limitedOutputBuffer) Write(p []byte) (int, error) {
	if b.limit <= 0 {
		return len(p), nil
	}
	remaining := b.limit - b.buf.Len()
	if remaining <= 0 {
		b.truncated = true
		return len(p), nil
	}
	if len(p) > remaining {
		b.truncated = true
		_, _ = b.buf.Write(p[:remaining])
		return len(p), nil
	}
	_, _ = b.buf.Write(p)
	return len(p), nil
}

func (b *limitedOutputBuffer) String() string {
	out := b.buf.String()
	if b.truncated {
		out += fmt.Sprintf("\n[output truncated after %d bytes]", b.limit)
	}
	return out
}

// ── Skill Directory Reading ─────────────────────────────────────────────────

type skillPackageFile struct {
	Path        string `json:"path"`
	Size        int64  `json:"size"`
	SHA256      string `json:"sha256"`
	ContentType string `json:"contentType"`
}

type skillPackageSource struct {
	FullPath string
	RelPath  string
	Mode     os.FileMode
}

func materializeSkillArg(c *client.Client, skillArg string) (string, func(), *client.SkillDetail, error) {
	if isSkillDirectory(skillArg) {
		return skillArg, func() {}, nil, nil
	}

	detail, err := c.GetSkill(skillArg, skillVersion)
	if err != nil {
		return "", nil, nil, fmt.Errorf("skill %q is not a local skill directory and was not found on the server: %w", skillArg, err)
	}
	dir, err := ensureCachedSkillPackage(c, detail)
	if err != nil {
		return "", nil, nil, err
	}
	return dir, func() {}, detail, nil
}

func ensureCachedSkillPackage(c *client.Client, detail *client.SkillDetail) (string, error) {
	cacheDir, filesDir, checksumPath := skillCachePaths(detail)
	if isCachedSkillCurrent(filesDir, checksumPath, detail.Checksum) {
		return filesDir, nil
	}

	data, err := c.DownloadSkillPackage(detail.Name, detail.Version)
	if err != nil {
		return "", err
	}
	if checksum := strings.TrimSpace(detail.Checksum); checksum != "" {
		actual := skillPackageChecksum(data)
		if !strings.EqualFold(actual, checksum) {
			return "", fmt.Errorf(
				"downloaded skill package checksum mismatch for %s@%s: expected %s, got %s",
				detail.Name,
				detail.Version,
				checksum,
				actual,
			)
		}
	}

	parentDir := filepath.Dir(cacheDir)
	if err := os.MkdirAll(parentDir, 0o700); err != nil {
		return "", fmt.Errorf("create skill cache parent: %w", err)
	}

	tmpDir, err := os.MkdirTemp(parentDir, "."+filepath.Base(cacheDir)+"-*")
	if err != nil {
		return "", fmt.Errorf("create temp skill cache: %w", err)
	}
	cleanupTmp := true
	defer func() {
		if cleanupTmp {
			_ = os.RemoveAll(tmpDir)
		}
	}()

	tmpFilesDir := filepath.Join(tmpDir, "files")
	if err := extractSkillPackage(data, tmpFilesDir); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "checksum"), []byte(detail.Checksum), 0o600); err != nil {
		return "", fmt.Errorf("write skill cache checksum: %w", err)
	}

	if err := os.RemoveAll(cacheDir); err != nil {
		return "", fmt.Errorf("clear stale skill cache: %w", err)
	}
	if err := os.Rename(tmpDir, cacheDir); err != nil {
		return "", fmt.Errorf("install skill cache: %w", err)
	}
	cleanupTmp = false
	return filesDir, nil
}

func hydrateRegisteredCrossSkillRefs(c *client.Client, config map[string]interface{}, seen map[string]bool) error {
	skillMd, _ := config["skillMd"].(string)
	if skillMd == "" {
		return nil
	}
	skillName := skillNameFromConfig(config, "")
	if skillName != "" {
		if seen[skillName] {
			return fmt.Errorf("circular skill reference detected: %s", skillName)
		}
		seen[skillName] = true
		defer delete(seen, skillName)
	}

	refs := make(map[string]interface{})
	refVersions := registeredCrossSkillRefVersions(config["crossSkillRefs"])
	refNames := make([]string, 0, len(refVersions))
	for refName := range refVersions {
		refNames = append(refNames, refName)
	}
	if len(refNames) == 0 {
		refNames = referencedSkillNames(skillMd)
	}
	sort.Strings(refNames)
	for _, refName := range refNames {
		if seen[refName] {
			return fmt.Errorf("circular skill reference detected: %s", refName)
		}
		detail, err := c.GetSkill(refName, refVersions[refName])
		if err != nil {
			continue
		}
		refDir, err := ensureCachedSkillPackage(c, detail)
		if err != nil {
			return fmt.Errorf("cache referenced skill %q: %w", refName, err)
		}
		payload, _, err := buildSkillPayloadInternal(refDir, map[string]bool{})
		if err != nil {
			return fmt.Errorf("load referenced skill %q: %w", refName, err)
		}
		refConfig, _ := payload["config"].(map[string]interface{})
		if refConfig == nil {
			continue
		}
		refConfig["skillRef"] = map[string]interface{}{
			"name":     detail.Name,
			"version":  detail.Version,
			"checksum": detail.Checksum,
		}
		nextSeen := make(map[string]bool, len(seen)+1)
		for k, v := range seen {
			nextSeen[k] = v
		}
		if err := hydrateRegisteredCrossSkillRefs(c, refConfig, nextSeen); err != nil {
			return err
		}
		refs[refName] = refConfig
	}
	config["crossSkillRefs"] = refs
	return nil
}

func registeredCrossSkillRefVersions(v interface{}) map[string]string {
	versions := make(map[string]string)
	refs, ok := v.(map[string]interface{})
	if !ok {
		return versions
	}
	for refName, raw := range refs {
		refConfig, ok := raw.(map[string]interface{})
		if !ok {
			continue
		}
		skillRef, ok := refConfig["skillRef"].(map[string]interface{})
		if !ok {
			continue
		}
		if version, _ := skillRef["version"].(string); version != "" {
			versions[refName] = version
		}
	}
	return versions
}

func skillCachePaths(detail *client.SkillDetail) (cacheDir string, filesDir string, checksumPath string) {
	cacheDir = filepath.Join(
		cliConfig.ConfigDir(),
		"skills",
		safeCacheSegment(detail.Name),
		safeCacheSegment(detail.Version),
	)
	filesDir = filepath.Join(cacheDir, "files")
	checksumPath = filepath.Join(cacheDir, "checksum")
	return cacheDir, filesDir, checksumPath
}

func safeCacheSegment(value string) string {
	cleaned := regexp.MustCompile(`[^A-Za-z0-9._-]+`).ReplaceAllString(value, "_")
	cleaned = strings.Trim(cleaned, "._-")
	if cleaned == "" {
		cleaned = "unnamed"
	}
	if cleaned != value {
		sum := sha256.Sum256([]byte(value))
		cleaned = cleaned + "-" + hex.EncodeToString(sum[:])[:8]
	}
	return cleaned
}

func skillPackageChecksum(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func isCachedSkillCurrent(filesDir string, checksumPath string, checksum string) bool {
	if !isSkillDirectory(filesDir) {
		return false
	}
	if checksum == "" {
		return true
	}
	data, err := os.ReadFile(checksumPath)
	return err == nil && strings.TrimSpace(string(data)) == checksum
}

func isSkillDirectory(path string) bool {
	expanded := expandUserPath(path)
	info, err := os.Stat(expanded)
	if err != nil || !info.IsDir() {
		return false
	}
	_, err = os.Stat(filepath.Join(expanded, "SKILL.md"))
	return err == nil
}

func buildSkillPackage(skillPath string) ([]byte, []skillPackageFile, error) {
	absPath, err := filepath.Abs(expandUserPath(skillPath))
	if err != nil {
		return nil, nil, fmt.Errorf("resolve path: %w", err)
	}
	absPath, err = filepath.EvalSymlinks(absPath)
	if err != nil {
		return nil, nil, fmt.Errorf("resolve path: %w", err)
	}
	ignoreMatcher, err := loadSkillPackageIgnore(absPath)
	if err != nil {
		return nil, nil, err
	}

	var sources []skillPackageSource
	err = filepath.WalkDir(absPath, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(absPath, path)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if rel == "." {
			return nil
		}
		if entry.IsDir() {
			if shouldExcludeSkillPackagePath(rel, true, ignoreMatcher) {
				return filepath.SkipDir
			}
			switch entry.Name() {
			case ".git", "__pycache__", "node_modules":
				return filepath.SkipDir
			default:
				return nil
			}
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return nil
		}
		if shouldExcludeSkillPackagePath(rel, false, ignoreMatcher) {
			return nil
		}
		sources = append(sources, skillPackageSource{
			FullPath: path,
			RelPath:  rel,
			Mode:     info.Mode(),
		})
		return nil
	})
	if err != nil {
		return nil, nil, fmt.Errorf("walk skill directory: %w", err)
	}
	sort.Slice(sources, func(i, j int) bool { return sources[i].RelPath < sources[j].RelPath })

	var packageBytes bytes.Buffer
	zipWriter := zip.NewWriter(&packageBytes)
	files := make([]skillPackageFile, 0, len(sources))
	for _, source := range sources {
		data, err := os.ReadFile(source.FullPath)
		if err != nil {
			zipWriter.Close()
			return nil, nil, fmt.Errorf("read %s: %w", source.RelPath, err)
		}
		sum := sha256.Sum256(data)

		header := &zip.FileHeader{
			Name:     source.RelPath,
			Method:   zip.Deflate,
			Modified: time.Unix(0, 0).UTC(),
		}
		header.SetMode(source.Mode.Perm())
		writer, err := zipWriter.CreateHeader(header)
		if err != nil {
			zipWriter.Close()
			return nil, nil, fmt.Errorf("create zip entry %s: %w", source.RelPath, err)
		}
		if _, err := writer.Write(data); err != nil {
			zipWriter.Close()
			return nil, nil, fmt.Errorf("write zip entry %s: %w", source.RelPath, err)
		}
		files = append(files, skillPackageFile{
			Path:        source.RelPath,
			Size:        int64(len(data)),
			SHA256:      hex.EncodeToString(sum[:]),
			ContentType: guessContentType(source.RelPath),
		})
	}
	if err := zipWriter.Close(); err != nil {
		return nil, nil, fmt.Errorf("close skill package: %w", err)
	}
	return packageBytes.Bytes(), files, nil
}

func extractSkillPackage(data []byte, dest string) error {
	targetRoot, err := filepath.Abs(expandUserPath(dest))
	if err != nil {
		return fmt.Errorf("resolve destination: %w", err)
	}
	if entries, err := os.ReadDir(targetRoot); err == nil && len(entries) > 0 {
		return fmt.Errorf("destination %q already exists and is not empty", targetRoot)
	}
	if err := os.MkdirAll(targetRoot, 0o755); err != nil {
		return fmt.Errorf("create destination: %w", err)
	}

	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return fmt.Errorf("open skill package: %w", err)
	}
	for _, file := range reader.File {
		if file.FileInfo().IsDir() {
			continue
		}
		target, err := safePackagePath(targetRoot, file.Name)
		if err != nil {
			return err
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return fmt.Errorf("create directory for %s: %w", file.Name, err)
		}
		rc, err := file.Open()
		if err != nil {
			return fmt.Errorf("open package entry %s: %w", file.Name, err)
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, file.Mode().Perm())
		if err != nil {
			rc.Close()
			return fmt.Errorf("create %s: %w", target, err)
		}
		_, copyErr := io.Copy(out, rc)
		closeErr := out.Close()
		rc.Close()
		if copyErr != nil {
			return fmt.Errorf("extract %s: %w", file.Name, copyErr)
		}
		if closeErr != nil {
			return fmt.Errorf("close %s: %w", target, closeErr)
		}
	}
	return nil
}

type skillPackageIgnoreMatcher struct {
	patterns []string
}

func loadSkillPackageIgnore(skillRoot string) (skillPackageIgnoreMatcher, error) {
	matcher := skillPackageIgnoreMatcher{}
	data, err := os.ReadFile(filepath.Join(skillRoot, ".agentspanignore"))
	if err != nil {
		if os.IsNotExist(err) {
			return matcher, nil
		}
		return matcher, fmt.Errorf("read .agentspanignore: %w", err)
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		matcher.patterns = append(matcher.patterns, filepath.ToSlash(line))
	}
	return matcher, nil
}

func shouldExcludeSkillPackagePath(relPath string, isDir bool, matcher skillPackageIgnoreMatcher) bool {
	relPath = filepath.ToSlash(strings.TrimPrefix(relPath, "./"))
	if relPath == "" || relPath == "." {
		return false
	}
	base := pathpkg.Base(relPath)
	if base == ".agentspanignore" || isDefaultSecretSkillFile(base) {
		return true
	}
	if isDir && isDefaultGeneratedSkillDir(base) {
		return true
	}
	return matcher.matches(relPath, isDir)
}

func (m skillPackageIgnoreMatcher) matches(relPath string, isDir bool) bool {
	for _, pattern := range m.patterns {
		if skillIgnorePatternMatches(pattern, relPath, isDir) {
			return true
		}
	}
	return false
}

func skillIgnorePatternMatches(pattern, relPath string, isDir bool) bool {
	pattern = filepath.ToSlash(strings.TrimSpace(pattern))
	if pattern == "" || strings.HasPrefix(pattern, "!") {
		return false
	}
	dirOnly := strings.HasSuffix(pattern, "/")
	pattern = strings.TrimSuffix(pattern, "/")
	if dirOnly && !isDir {
		if relPath == pattern || strings.HasPrefix(relPath, pattern+"/") {
			return true
		}
		return false
	}
	if strings.Contains(pattern, "/") {
		if ok, err := pathpkg.Match(pattern, relPath); err == nil && ok {
			return true
		}
		if relPath == pattern || strings.HasPrefix(relPath, pattern+"/") {
			return true
		}
		return false
	}
	parts := strings.Split(relPath, "/")
	for _, part := range parts {
		if ok, err := pathpkg.Match(pattern, part); err == nil && ok {
			return true
		}
	}
	return false
}

func isDefaultGeneratedSkillDir(name string) bool {
	switch name {
	case ".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build", "target", ".gradle", ".pytest_cache", ".mypy_cache":
		return true
	default:
		return false
	}
}

func isDefaultSecretSkillFile(name string) bool {
	lower := strings.ToLower(name)
	if lower == ".ds_store" || lower == ".env" || strings.HasPrefix(lower, ".env.") {
		return true
	}
	switch lower {
	case "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "known_hosts":
		return true
	}
	for _, suffix := range []string{".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt", ".cer"} {
		if strings.HasSuffix(lower, suffix) {
			return true
		}
	}
	return false
}

func safePackagePath(root, relPath string) (string, error) {
	cleanRel := filepath.Clean(filepath.FromSlash(relPath))
	if filepath.IsAbs(cleanRel) || cleanRel == ".." || strings.HasPrefix(cleanRel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("package path %q is outside the skill directory", relPath)
	}
	target := filepath.Join(root, cleanRel)
	if rel, err := filepath.Rel(root, target); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("package path %q is outside the skill directory", relPath)
	}
	return target, nil
}

func shortVersion(version string) string {
	if len(version) > 12 {
		return version[:12]
	}
	return version
}

func guessContentType(path string) string {
	lower := strings.ToLower(path)
	switch {
	case strings.HasSuffix(lower, ".md"), strings.HasSuffix(lower, ".txt"):
		return "text/plain"
	case strings.HasSuffix(lower, ".json"):
		return "application/json"
	case strings.HasSuffix(lower, ".yaml"), strings.HasSuffix(lower, ".yml"):
		return "application/yaml"
	case strings.HasSuffix(lower, ".html"), strings.HasSuffix(lower, ".htm"):
		return "text/html"
	case strings.HasSuffix(lower, ".css"):
		return "text/css"
	case strings.HasSuffix(lower, ".js"), strings.HasSuffix(lower, ".mjs"):
		return "text/javascript"
	case strings.HasSuffix(lower, ".png"):
		return "image/png"
	case strings.HasSuffix(lower, ".jpg"), strings.HasSuffix(lower, ".jpeg"):
		return "image/jpeg"
	case strings.HasSuffix(lower, ".svg"):
		return "image/svg+xml"
	default:
		return "application/octet-stream"
	}
}

// buildSkillPayload reads a skill directory and returns the packaged JSON
// payload and the skill name. The payload matches the raw config format:
//
//	{"config": {...}, "prompt": "..."}
func buildSkillPayload(skillPath string) (map[string]interface{}, string, error) {
	return buildSkillPayloadInternal(skillPath, map[string]bool{})
}

func buildSkillPayloadInternal(skillPath string, seen map[string]bool) (map[string]interface{}, string, error) {
	absPath, err := filepath.Abs(expandUserPath(skillPath))
	if err != nil {
		return nil, "", fmt.Errorf("resolve path: %w", err)
	}
	absPath, err = filepath.EvalSymlinks(absPath)
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

	// 5. Resolve cross-skill references
	crossRefs, err := resolveCrossSkills(string(skillMdContent), absPath, seen)
	if err != nil {
		return nil, "", err
	}

	// 6. Parse params and inject them into SKILL.md for server visibility
	defaultParams := extractDefaultParams(frontmatter)
	paramOverrides, err := parseParamMap(skillParams)
	if err != nil {
		return nil, "", err
	}
	mergedParams := mergeParams(defaultParams, paramOverrides)
	skillMd := string(skillMdContent)
	if len(mergedParams) > 0 {
		skillMd = skillMd + "\n\n" + formatParamMap(mergedParams) + "\n"
	}

	// 7. Split large instruction bodies into virtual sections for CLI workers.
	sections := splitSkillSections(extractBody(skillMd))

	// 8. Parse agent model overrides
	agentModels, err := parseAgentModelFlags(skillAgentModels)
	if err != nil {
		return nil, "", err
	}

	// 9. Build config
	config := map[string]interface{}{
		"model":          skillModel,
		"agentModels":    agentModels,
		"skillMd":        skillMd,
		"agentFiles":     agentFiles,
		"scripts":        scripts,
		"resourceFiles":  resourceFiles,
		"crossSkillRefs": crossRefs,
		"defaultParams":  defaultParams,
		"params":         mergedParams,
		"_skillPath":     absPath,
		"_skillSections": sections,
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
	case ".bat", ".cmd":
		return "batch"
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
	ignoreMatcher, err := loadSkillPackageIgnore(skillDir)
	if err != nil {
		return nil, err
	}

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
			rel = filepath.ToSlash(rel)
			if shouldExcludeSkillPackagePath(rel, false, ignoreMatcher) {
				return nil
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
		if shouldExcludeSkillPackagePath(name, false, ignoreMatcher) {
			continue
		}
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

// resolveCrossSkills packages referenced sibling/project/user skills recursively.
func resolveCrossSkills(skillMd, skillDir string, seen map[string]bool) (map[string]interface{}, error) {
	refNames := referencedSkillNames(skillMd)
	if len(refNames) == 0 {
		return map[string]interface{}{}, nil
	}

	searchDirs := []string{filepath.Dir(skillDir), filepath.Join(".", ".agents", "skills")}
	if home, err := os.UserHomeDir(); err == nil {
		searchDirs = append(searchDirs, filepath.Join(home, ".agents", "skills"))
	}
	searchDirs = append(searchDirs, skillSearchPaths...)

	refs := make(map[string]interface{})
	for _, refName := range refNames {
		refDir, ok := findSkillDir(refName, searchDirs)
		if !ok {
			continue
		}
		refAbs, err := filepath.Abs(refDir)
		if err != nil {
			return nil, err
		}
		refAbs, err = filepath.EvalSymlinks(refAbs)
		if err != nil {
			return nil, err
		}
		if refAbs == skillDir {
			continue
		}
		if seen[refAbs] {
			return nil, fmt.Errorf("circular skill reference detected: %s", refName)
		}
		nextSeen := make(map[string]bool, len(seen)+1)
		for k, v := range seen {
			nextSeen[k] = v
		}
		nextSeen[skillDir] = true

		payload, _, err := buildSkillPayloadInternal(refAbs, nextSeen)
		if err != nil {
			return nil, fmt.Errorf("resolve cross-skill %q: %w", refName, err)
		}
		refs[refName] = payload["config"]
	}
	return refs, nil
}

func referencedSkillNames(skillMd string) []string {
	body := extractBody(skillMd)
	pattern := regexp.MustCompile(`(?i)(?:invoke|use|call)\s+(?:the\s+)?([a-z][a-z0-9-]*)\s+skill`)
	matches := pattern.FindAllStringSubmatch(body, -1)
	seen := make(map[string]bool)
	var names []string
	for _, match := range matches {
		refName := strings.ToLower(match[1])
		if seen[refName] {
			continue
		}
		seen[refName] = true
		names = append(names, refName)
	}
	sort.Strings(names)
	return names
}

func findSkillDir(name string, dirs []string) (string, bool) {
	for _, dir := range dirs {
		if dir == "" {
			continue
		}
		base := expandUserPath(dir)
		candidate := filepath.Join(base, name)
		if _, err := os.Stat(filepath.Join(candidate, "SKILL.md")); err == nil {
			return candidate, true
		}
	}
	return "", false
}

func expandUserPath(path string) string {
	if path == "~" {
		if home, err := os.UserHomeDir(); err == nil {
			return home
		}
	}
	if strings.HasPrefix(path, "~/") || strings.HasPrefix(path, "~"+string(os.PathSeparator)) {
		if home, err := os.UserHomeDir(); err == nil {
			return filepath.Join(home, strings.TrimPrefix(strings.TrimPrefix(path, "~/"), "~"+string(os.PathSeparator)))
		}
	}
	return path
}

func extractDefaultParams(frontmatter map[string]interface{}) map[string]interface{} {
	defaults := make(map[string]interface{})
	params, ok := frontmatter["params"].(map[string]interface{})
	if !ok {
		return defaults
	}
	for name, raw := range params {
		if def, ok := raw.(map[string]interface{}); ok {
			if value, exists := def["default"]; exists {
				defaults[name] = value
				continue
			}
		}
		defaults[name] = raw
	}
	return defaults
}

func parseParamMap(flags []string) (map[string]interface{}, error) {
	pairs, err := parseParamFlags(flags)
	if err != nil {
		return nil, err
	}
	result := make(map[string]interface{}, len(pairs))
	for _, pair := range pairs {
		result[pair[0]] = parseParamValue(pair[1])
	}
	return result, nil
}

func parseParamValue(value string) interface{} {
	switch strings.ToLower(value) {
	case "true":
		return true
	case "false":
		return false
	default:
		return value
	}
}

func mergeParams(defaults, overrides map[string]interface{}) map[string]interface{} {
	merged := make(map[string]interface{}, len(defaults)+len(overrides))
	for k, v := range defaults {
		merged[k] = v
	}
	for k, v := range overrides {
		merged[k] = v
	}
	return merged
}

func formatParamMap(params map[string]interface{}) string {
	if len(params) == 0 {
		return ""
	}
	keys := make([]string, 0, len(params))
	for k := range params {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var sb strings.Builder
	sb.WriteString("[Skill Parameters]\n")
	for i, k := range keys {
		if i > 0 {
			sb.WriteString("\n")
		}
		sb.WriteString(k)
		sb.WriteString(": ")
		sb.WriteString(fmt.Sprint(params[k]))
	}
	return sb.String()
}

const cliSectionSplitThreshold = 50000

func splitSkillSections(body string) map[string]string {
	if len(body) <= cliSectionSplitThreshold {
		return map[string]string{}
	}
	sections := make(map[string]string)
	parts := regexp.MustCompile(`(?m)(?=^## )`).Split(body, -1)
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if !strings.HasPrefix(trimmed, "## ") {
			continue
		}
		firstLine := strings.SplitN(trimmed, "\n", 2)[0]
		slug := slugifyHeading(strings.TrimSpace(strings.TrimPrefix(firstLine, "## ")))
		if slug != "" {
			sections[slug] = trimmed
		}
	}
	return sections
}

func slugifyHeading(text string) string {
	text = strings.ToLower(text)
	var sb strings.Builder
	lastDash := false
	for _, r := range text {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9':
			sb.WriteRune(r)
			lastDash = false
		case r == ' ' || r == '\t' || r == '-':
			if !lastDash && sb.Len() > 0 {
				sb.WriteByte('-')
				lastDash = true
			}
		}
	}
	return strings.Trim(sb.String(), "-")
}

func stringSlice(v interface{}) []string {
	switch val := v.(type) {
	case []string:
		return val
	case []interface{}:
		out := make([]string, 0, len(val))
		for _, item := range val {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func scriptMap(v interface{}) map[string]scriptInfo {
	out := make(map[string]scriptInfo)
	switch val := v.(type) {
	case map[string]scriptInfo:
		return val
	case map[string]interface{}:
		for name, raw := range val {
			switch info := raw.(type) {
			case scriptInfo:
				out[name] = info
			case map[string]interface{}:
				filename, _ := info["filename"].(string)
				language, _ := info["language"].(string)
				if filename != "" {
					out[name] = scriptInfo{Filename: filename, Language: language}
				}
			}
		}
	}
	return out
}

func crossSkillRefMap(v interface{}) map[string]map[string]interface{} {
	out := make(map[string]map[string]interface{})
	if refs, ok := v.(map[string]interface{}); ok {
		for name, raw := range refs {
			if cfg, ok := raw.(map[string]interface{}); ok {
				out[name] = cfg
			}
		}
	}
	return out
}

func skillSectionsFromConfig(config map[string]interface{}) map[string]string {
	out := make(map[string]string)
	switch val := config["_skillSections"].(type) {
	case map[string]string:
		return val
	case map[string]interface{}:
		for k, raw := range val {
			if s, ok := raw.(string); ok {
				out[k] = s
			}
		}
	}
	return out
}

func skillNameFromConfig(config map[string]interface{}, fallback string) string {
	skillMd, _ := config["skillMd"].(string)
	if skillMd == "" {
		return fallback
	}
	frontmatter, err := parseFrontmatter(skillMd)
	if err != nil {
		return fallback
	}
	if name, _ := frontmatter["name"].(string); name != "" {
		return name
	}
	return fallback
}

func stripLocalSkillFields(config map[string]interface{}) map[string]interface{} {
	clean := make(map[string]interface{}, len(config))
	for k, v := range config {
		if strings.HasPrefix(k, "_skill") {
			continue
		}
		if k == "crossSkillRefs" {
			if refs, ok := v.(map[string]interface{}); ok {
				cleanRefs := make(map[string]interface{}, len(refs))
				for name, raw := range refs {
					if refConfig, ok := raw.(map[string]interface{}); ok {
						cleanRefs[name] = stripLocalSkillFields(refConfig)
					} else {
						cleanRefs[name] = raw
					}
				}
				clean[k] = cleanRefs
				continue
			}
		}
		clean[k] = v
	}
	return clean
}

func safeSkillPath(absSkillDir, relPath string) (string, error) {
	cleanRel := filepath.Clean(relPath)
	if filepath.IsAbs(cleanRel) || cleanRel == ".." || strings.HasPrefix(cleanRel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("'%s' is outside the skill directory", relPath)
	}
	target := filepath.Join(absSkillDir, cleanRel)
	resolvedTarget, err := filepath.EvalSymlinks(target)
	if err != nil {
		return target, nil
	}
	resolvedDir, err := filepath.EvalSymlinks(absSkillDir)
	if err != nil {
		resolvedDir = absSkillDir
	}
	if rel, err := filepath.Rel(resolvedDir, resolvedTarget); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("'%s' is outside the skill directory", relPath)
	}
	return resolvedTarget, nil
}

func safeWorkspacePath(absRoot, relPath string) (string, error) {
	cleanRel := filepath.Clean(filepath.FromSlash(defaultString(relPath, ".")))
	if filepath.IsAbs(cleanRel) || cleanRel == ".." || strings.HasPrefix(cleanRel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("'%s' is outside the filesystem root", relPath)
	}
	target := filepath.Join(absRoot, cleanRel)
	resolvedRoot, err := filepath.EvalSymlinks(absRoot)
	if err != nil {
		resolvedRoot = absRoot
	}
	resolvedTarget, err := filepath.EvalSymlinks(target)
	if err != nil {
		resolvedTarget = target
	}
	if rel, err := filepath.Rel(resolvedRoot, resolvedTarget); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("'%s' is outside the filesystem root", relPath)
	}
	return resolvedTarget, nil
}

func resolvedWorkspaceRootPath(absRoot string) string {
	resolved, err := filepath.EvalSymlinks(absRoot)
	if err != nil {
		return absRoot
	}
	return resolved
}

func readLimitedTextFile(pathValue string, limit int) (string, bool, error) {
	if limit <= 0 {
		limit = 1024 * 1024
	}
	file, err := os.Open(pathValue)
	if err != nil {
		return "", false, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, int64(limit)+1))
	if err != nil {
		return "", false, err
	}
	truncated := len(data) > limit
	if truncated {
		data = data[:limit]
	}
	return string(data), truncated, nil
}

func shouldSkipWorkspaceDir(name string) bool {
	switch name {
	case ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build", "target", ".gradle", ".idea", ".mypy_cache", ".pytest_cache":
		return true
	default:
		return false
	}
}

func matchesWorkspacePattern(pattern, relPath string) bool {
	pattern = filepath.ToSlash(strings.TrimSpace(pattern))
	if pattern == "" {
		return true
	}
	relPath = filepath.ToSlash(relPath)
	if ok, err := pathpkg.Match(pattern, relPath); err == nil && ok {
		return true
	}
	if strings.Contains(pattern, "**") {
		re := regexp.QuoteMeta(pattern)
		re = strings.ReplaceAll(re, `\*\*`, `.*`)
		re = strings.ReplaceAll(re, `\*`, `[^/]*`)
		re = strings.ReplaceAll(re, `\?`, `[^/]`)
		ok, err := regexp.MatchString("^"+re+"$", relPath)
		return err == nil && ok
	}
	if strings.HasPrefix(pattern, "*") || strings.HasSuffix(pattern, "*") {
		return strings.Contains(relPath, strings.Trim(pattern, "*"))
	}
	return relPath == pattern
}

func intInput(input map[string]interface{}, key string, fallback int, maxValue int) int {
	value, ok := input[key]
	if !ok || value == nil {
		return fallback
	}
	var out int
	switch v := value.(type) {
	case int:
		out = v
	case int64:
		out = int(v)
	case float64:
		out = int(v)
	case string:
		parsed, err := strconv.Atoi(v)
		if err != nil {
			return fallback
		}
		out = parsed
	default:
		return fallback
	}
	if out <= 0 {
		return fallback
	}
	if maxValue > 0 && out > maxValue {
		return maxValue
	}
	return out
}

func boolInput(input map[string]interface{}, key string, fallback bool) bool {
	value, ok := input[key]
	if !ok || value == nil {
		return fallback
	}
	switch v := value.(type) {
	case bool:
		return v
	case string:
		parsed, err := strconv.ParseBool(v)
		if err != nil {
			return fallback
		}
		return parsed
	default:
		return fallback
	}
}

func defaultString(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func trimLongLine(value string, limit int) string {
	if limit <= 0 || len(value) <= limit {
		return value
	}
	return value[:limit] + "...[truncated]"
}

func filesystemEnvName(name string) string {
	replacer := regexp.MustCompile(`[^A-Za-z0-9]+`)
	return strings.ToUpper(strings.Trim(replacer.ReplaceAllString(name, "_"), "_"))
}

func splitCommandArgs(command string) []string {
	var args []string
	var current strings.Builder
	inSingle := false
	inDouble := false
	escaped := false
	for _, r := range command {
		switch {
		case escaped:
			current.WriteRune(r)
			escaped = false
		case r == '\\' && !inSingle:
			escaped = true
		case r == '\'' && !inDouble:
			inSingle = !inSingle
		case r == '"' && !inSingle:
			inDouble = !inDouble
		case (r == ' ' || r == '\t' || r == '\n') && !inSingle && !inDouble:
			if current.Len() > 0 {
				args = append(args, current.String())
				current.Reset()
			}
		default:
			current.WriteRune(r)
		}
	}
	if current.Len() > 0 {
		args = append(args, current.String())
	}
	return args
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
