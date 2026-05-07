// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
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
	lastDeployStateFile  = "last-deploy.json"
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
	state, _ := loadLastDeploy()

	// Lima Firecracker path — bundle staged on Lima VM
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

// runLimaInvoke runs the agent bundle on the Lima VM via limactl + run-agent.sh.
func runLimaInvoke(state *lastDeployState) error {
	cfg := config.Load()
	vmName := state.VMName
	if vmName == "" {
		vmName = os.Getenv("LIMA_VM_NAME")
		if vmName == "" {
			vmName = "default"
		}
	}

	runAgentScript := os.Getenv("LIMA_RUN_AGENT_SCRIPT")
	if runAgentScript == "" {
		runAgentScript = config.DefaultLimaRunAgentScript
	}

	// Collect env vars required by the agent from agentspan.yaml.
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

	// Write env.json to a temp file, copy to Lima.
	envData, err := json.Marshal(envMap)
	if err != nil {
		return fmt.Errorf("marshal env.json: %w", err)
	}
	tmpEnv, err := os.CreateTemp("", "agentspan-env-*.json")
	if err != nil {
		return fmt.Errorf("create temp env file: %w", err)
	}
	defer os.Remove(tmpEnv.Name())
	if _, err := tmpEnv.Write(envData); err != nil {
		tmpEnv.Close()
		return fmt.Errorf("write temp env file: %w", err)
	}
	tmpEnv.Close()

	remoteEnvPath := "/tmp/agentspan-env.json"
	copyCmd := exec.Command("limactl", "copy", tmpEnv.Name(), vmName+":"+remoteEnvPath)
	copyCmd.Stdout = os.Stdout
	copyCmd.Stderr = os.Stderr
	if err := copyCmd.Run(); err != nil {
		return fmt.Errorf("copy env.json to Lima VM %q: %w", vmName, err)
	}

	bold := color.New(color.Bold)
	bold.Printf("Invoking agent in Firecracker on Lima VM %q\n", vmName)
	fmt.Printf("  Bundle : %s\n\n", state.RemoteBundlePath)

	runCmd := exec.Command("limactl", "shell", vmName, "--",
		"sudo", runAgentScript, state.RemoteBundlePath, remoteEnvPath)
	runCmd.Stdout = os.Stdout
	runCmd.Stderr = os.Stderr
	if err := runCmd.Run(); err != nil {
		return fmt.Errorf("run-agent.sh failed: %w", err)
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

func saveLastDeploy(state lastDeployState) error {
	if err := os.MkdirAll(agentspanConfigDir(), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(agentspanConfigDir(), lastDeployStateFile), data, 0o600)
}

func loadLastDeploy() (*lastDeployState, error) {
	data, err := os.ReadFile(filepath.Join(agentspanConfigDir(), lastDeployStateFile))
	if err != nil {
		return nil, fmt.Errorf("no previous deploy found")
	}
	var state lastDeployState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("parse last deploy state: %w", err)
	}
	return &state, nil
}
