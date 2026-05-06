// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	lastDeployStateFile  = "last-deploy.json"
	defaultDevSHEnvVar   = "AGENTSPAN_DEV_SH"
	defaultStagingEnvVar = "STAGING_DIR"
	defaultEntrypoint    = "hello.py"
)

type lastDeployState struct {
	WorkflowID string    `json:"workflow_id"`
	StagingDir string    `json:"staging_dir"`
	BundleName string    `json:"bundle_name"`
	DeployedAt time.Time `json:"deployed_at"`
}

var invokeCmd = &cobra.Command{
	Use:   "invoke [entrypoint]",
	Short: "Invoke an agent in its Firecracker microVM",
	Long: `Run the staged agent script inside a Firecracker microVM via dev.sh.

The entrypoint defaults to the value of AGENTSPAN_ENTRYPOINT (or hello.py).
The staging directory is read from STAGING_DIR or ~/.agentspan/last-deploy.json.
The path to dev.sh is read from AGENTSPAN_DEV_SH.`,
	Args: cobra.MaximumNArgs(1),
	RunE: runInvokeCmd,
}

func init() {
	agentCmd.AddCommand(invokeCmd)
}

func runInvokeCmd(cmd *cobra.Command, args []string) error {
	// Resolve entrypoint
	entrypoint := os.Getenv("AGENTSPAN_ENTRYPOINT")
	if entrypoint == "" {
		entrypoint = defaultEntrypoint
	}
	if len(args) > 0 {
		entrypoint = args[0]
	}

	// Resolve staging dir
	stagingDir := os.Getenv(defaultStagingEnvVar)
	if stagingDir == "" {
		state, err := loadLastDeploy()
		if err != nil {
			return fmt.Errorf("staging dir unknown: set STAGING_DIR or run 'agentspan deploy' first")
		}
		stagingDir = state.StagingDir
	}

	// Resolve dev.sh
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
