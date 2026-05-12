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
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const bundleManifestFile = "bundle-manifest.json"

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

// agentspanInvokeSpec is the minimal slice of agentspan.yaml we need at invoke time.
type agentspanInvokeSpec struct {
	Metadata struct {
		Name string `yaml:"name"`
	} `yaml:"metadata"`
	Spec struct {
		Env []string `yaml:"env"`
	} `yaml:"spec"`
}

var invokeAgentName string

var invokeCmd = &cobra.Command{
	Use:   "invoke",
	Short: "Invoke a deployed agent in its execution environment",
	Long: `Boot the staged agent bundle in a Firecracker microVM via the Lima VM.

Use --name to invoke any previously deployed agent by name, from any directory.
Without --name, uses the deploy state from the current project directory.`,
	Args: cobra.NoArgs,
	RunE: runInvokeCmd,
}

func init() {
	agentCmd.AddCommand(invokeCmd)
	invokeCmd.Flags().StringVar(&invokeAgentName, "name", "", "Invoke a deployed agent by name (any directory)")
}

func runInvokeCmd(cmd *cobra.Command, args []string) error {
	if invokeAgentName != "" {
		state, err := loadGlobalAgentDeploy(invokeAgentName)
		if err != nil {
			return err
		}
		return runLimaInvoke(state)
	}

	state, err := loadLastDeploy()
	if err != nil {
		return fmt.Errorf("not deployed — run 'agentspan deploy' first")
	}
	return runLimaInvoke(state)
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

	// Collect env vars for the agent.
	// Use the Lima guest URL so agents inside the Firecracker VM can reach the Agentspan server.
	// Routes via Lima NAT → macOS LAN IP — set lima_guest_server_url in ~/.agentspan/config.json
	// since the guest cannot reach the host's localhost.
	agentspanURL := cfg.LimaGuestServerURL
	if agentspanURL == "" {
		agentspanURL = config.DefaultLimaGuestServerURL
	}
	envMap := map[string]string{
		"AGENTSPAN_SERVER_URL": agentspanURL,
	}
	if buildState, err := loadLastBuild(); err == nil && buildState.SourceDir != "" {
		agentspanPath := filepath.Join(buildState.SourceDir, "agentspan.yaml")
		if data, err := os.ReadFile(agentspanPath); err == nil {
			var spec agentspanInvokeSpec
			if yaml.Unmarshal(data, &spec) == nil {
				for _, key := range spec.Spec.Env {
					if val := os.Getenv(key); val != "" {
						envMap[key] = val
					} else if key == "AGENTSPAN_LLM_MODEL" && cfg.LLMModel != "" {
						envMap[key] = cfg.LLMModel
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

// globalAgentDeployPath returns the path for the named agent's global deploy state.
func globalAgentDeployPath(name string) string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".agentspan", "agents", name+".json")
}

// saveGlobalAgentDeploy writes deploy state to the global agent registry.
func saveGlobalAgentDeploy(name string, deploy lastDeployState) error {
	path := globalAgentDeployPath(name)
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(deploy, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o600)
}

// loadGlobalAgentDeploy reads deploy state from the global agent registry.
func loadGlobalAgentDeploy(name string) (*lastDeployState, error) {
	data, err := os.ReadFile(globalAgentDeployPath(name))
	if err != nil {
		return nil, fmt.Errorf("agent %q not found — run 'agentspan deploy' from the agent directory first", name)
	}
	var state lastDeployState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("parse global agent state for %q: %w", name, err)
	}
	return &state, nil
}

// readAgentName extracts metadata.name from an agentspan.yaml file.
func readAgentName(sourceDir string) string {
	data, err := os.ReadFile(filepath.Join(sourceDir, "agentspan.yaml"))
	if err != nil {
		return ""
	}
	var spec agentspanInvokeSpec
	if yaml.Unmarshal(data, &spec) != nil {
		return ""
	}
	return spec.Metadata.Name
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
