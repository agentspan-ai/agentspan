// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const (
	defaultDevSHEnvVar   = "AGENTSPAN_DEV_SH"
	defaultStagingEnvVar = "STAGING_DIR"
	defaultEntrypoint    = "hello.py"
	bundleManifestFile   = "bundle-manifest.json"
)

type lastDeployState struct {
	WorkflowID       string    `json:"workflow_id"`
	StagingDir       string    `json:"staging_dir,omitempty"`
	BundleName       string    `json:"bundle_name"`
	RemoteBundlePath string    `json:"remote_bundle_path,omitempty"`
	VMName           string    `json:"vm_name,omitempty"`
	DeployedAt       time.Time `json:"deployed_at"`
}

type bundleManifest struct {
	Name       string `json:"name"`
	Entrypoint string `json:"entrypoint"`
	Runtime    string `json:"runtime"`
}

var invokeCmd = &cobra.Command{
	Use:   "invoke [entrypoint]",
	Short: "Invoke an agent in its execution environment",
	Long: `Run the staged agent.

For project bundles (with bundle-manifest.json): runs locally using the
bundled dependencies and the entrypoint declared in agentspan.yaml.

For plain script bundles: runs the script inside a Firecracker microVM via
dev.sh (AGENTSPAN_DEV_SH must be set).`,
	Args: cobra.MaximumNArgs(1),
	RunE: runInvokeCmd,
}

func init() {
	agentCmd.AddCommand(invokeCmd)
}

func runInvokeCmd(cmd *cobra.Command, args []string) error {
	cwd, _ := os.Getwd()
	_, inAgentspanProject := os.Stat(filepath.Join(cwd, "agentspan.yaml"))

	// Lima Firecracker path — project-local deploy state
	if inAgentspanProject == nil {
		state, err := loadLastDeploy()
		if err != nil {
			return fmt.Errorf("not deployed — run 'agentspan deploy' first")
		}
		return runLimaInvoke(state)
	}

	// Legacy paths for non-agentspan.yaml projects
	state, _ := loadLastDeploy()
	if state != nil && state.RemoteBundlePath != "" {
		return runLimaInvoke(state)
	}

	stagingDir := os.Getenv(defaultStagingEnvVar)
	if stagingDir == "" {
		if state != nil && state.StagingDir != "" {
			stagingDir = state.StagingDir
		} else {
			return fmt.Errorf("staging dir unknown: set STAGING_DIR or run 'agentspan deploy' first")
		}
	}

	// Project bundle — local execution path
	manifestPath := filepath.Join(stagingDir, bundleManifestFile)
	if _, err := os.Stat(manifestPath); err == nil {
		return runLocalInvoke(stagingDir, manifestPath)
	}

	// Plain script — Firecracker path via dev.sh
	return runFirecrackerInvoke(stagingDir, args)
}

// agentspanInvokeSpec is the minimal slice of agentspan.yaml we need at invoke time.
type agentspanInvokeSpec struct {
	Spec struct {
		Env []string `yaml:"env"`
	} `yaml:"spec"`
}

// runLimaInvoke calls the Rust API on the Lima host to boot the staged agent bundle.
func runLimaInvoke(state *lastDeployState) error {
	cfg := config.Load()
	vmName := state.VMName
	if vmName == "" {
		vmName = os.Getenv("LIMA_VM_NAME")
		if vmName == "" {
			vmName = config.DefaultLimaVMName
		}
	}

	apiPort := os.Getenv("AGENT_RUNNER_API_PORT")
	if apiPort == "" {
		apiPort = "7878"
	}

	// Collect env vars for the agent
	envMap := map[string]string{
		"AGENTSPAN_SERVER_URL": cfg.ServerURL,
	}
	if buildState, err := loadLastBuild(); err == nil && buildState.SourceDir != "" {
		agentspanPath := filepath.Join(buildState.SourceDir, "agentspan.yaml")
		if data, err := os.ReadFile(agentspanPath); err == nil {
			var spec agentspanInvokeSpec
			if yaml.Unmarshal(data, &spec) == nil {
				for _, key := range spec.Spec.Env {
					if val := os.Getenv(key); val != "" {
						envMap[key] = val
					}
				}
			}
		}
	}

	type invokeReq struct {
		BundlePath string            `json:"bundle_path"`
		Env        map[string]string `json:"env"`
	}
	payload, err := json.Marshal(invokeReq{BundlePath: state.RemoteBundlePath, Env: envMap})
	if err != nil {
		return fmt.Errorf("marshal invoke request: %w", err)
	}

	bold := color.New(color.Bold)
	bold.Printf("Invoking agent via Rust API on Lima VM %q\n", vmName)
	fmt.Printf("  Bundle : %s\n\n", state.RemoteBundlePath)

	// POST to Rust API via limactl shell + curl
	var out bytes.Buffer
	runCmd := exec.Command("limactl", "shell", vmName, "--",
		"curl", "-s",
		"-X", "POST",
		"-H", "Content-Type: application/json",
		"-d", string(payload),
		fmt.Sprintf("http://localhost:%s/invoke", apiPort))
	runCmd.Stdout = &out
	runCmd.Stderr = os.Stderr
	if err := runCmd.Run(); err != nil {
		return fmt.Errorf("invoke API call failed: %w", err)
	}

	type invokeResp struct {
		ExitCode int    `json:"exit_code"`
		Output   string `json:"output"`
		Error    string `json:"error,omitempty"`
	}
	var resp invokeResp
	if err := json.Unmarshal(out.Bytes(), &resp); err != nil {
		// Not JSON — print raw and return
		fmt.Print(out.String())
		return nil
	}
	if resp.Error != "" {
		return fmt.Errorf("invoke error: %s", resp.Error)
	}
	fmt.Print(resp.Output)
	if resp.ExitCode != 0 {
		return fmt.Errorf("agent exited with code %d", resp.ExitCode)
	}
	return nil
}

// runLocalInvoke runs a project bundle locally using the bundled lib/ dependencies.
func runLocalInvoke(stagingDir, manifestPath string) error {
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return fmt.Errorf("read bundle manifest: %w", err)
	}
	var manifest bundleManifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		return fmt.Errorf("parse bundle manifest: %w", err)
	}

	python := findPythonBinary(stagingDir)
	if python == "" {
		return fmt.Errorf("no Python interpreter found; install Python or set the PYTHON environment variable")
	}

	bold := color.New(color.Bold)
	bold.Printf("Invoking %s (%s)\n", manifest.Name, manifest.Entrypoint)
	fmt.Printf("  Staging : %s\n\n", stagingDir)

	libDir := filepath.Join(stagingDir, "lib")
	pythonPath := libDir + string(os.PathListSeparator) + stagingDir
	if existing := os.Getenv("PYTHONPATH"); existing != "" {
		pythonPath += string(os.PathListSeparator) + existing
	}

	env := setPythonPath(os.Environ(), pythonPath)

	c := exec.Command(python, "-m", manifest.Entrypoint)
	c.Env = env
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		return fmt.Errorf("agent exited with error: %w", err)
	}
	return nil
}

// runFirecrackerInvoke runs a plain script inside a Firecracker microVM via dev.sh.
func runFirecrackerInvoke(stagingDir string, args []string) error {
	entrypoint := os.Getenv("AGENTSPAN_ENTRYPOINT")
	if entrypoint == "" {
		entrypoint = defaultEntrypoint
	}
	if len(args) > 0 {
		entrypoint = args[0]
	}

	devSH := os.Getenv(defaultDevSHEnvVar)
	if devSH == "" {
		return fmt.Errorf("AGENTSPAN_DEV_SH is not set — point it to the firecracker/dev.sh script")
	}

	script := filepath.Join(stagingDir, entrypoint)
	if _, err := os.Stat(script); err != nil {
		return fmt.Errorf("staged script not found: %s (run 'agentspan deploy' first)", script)
	}

	bold := color.New(color.Bold)
	bold.Printf("Invoking %s in Firecracker\n", entrypoint)
	fmt.Printf("  Script  : %s\n", script)
	fmt.Printf("  dev.sh  : %s\n\n", devSH)

	c := exec.Command(devSH, "run", script)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		return fmt.Errorf("dev.sh run failed: %w", err)
	}
	return nil
}

// setPythonPath replaces or prepends PYTHONPATH in an env slice.
func setPythonPath(env []string, pythonPath string) []string {
	out := make([]string, 0, len(env)+1)
	for _, e := range env {
		if !strings.HasPrefix(e, "PYTHONPATH=") {
			out = append(out, e)
		}
	}
	return append(out, "PYTHONPATH="+pythonPath)
}

func saveLastDeploy(deploy lastDeployState) error {
	state := readProjectState()
	state.Deploy = &deploy
	return writeProjectState(state)
}

func loadLastDeploy() (*lastDeployState, error) {
	state := readProjectState()
	if state.Deploy == nil {
		return nil, fmt.Errorf("not deployed — run 'agentspan deploy' first")
	}
	return state.Deploy, nil
}
