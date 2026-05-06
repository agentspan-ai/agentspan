// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	buildWorkflowName    = "agentspan_build"
	buildWorkflowVersion = 1
	lastBuildStateFile   = "last-build.json"
)

type lastBuildState struct {
	WorkflowID   string    `json:"workflow_id"`
	FileHandleID string    `json:"file_handle_id"`
	BundleName   string    `json:"bundle_name"`
	SourceDir    string    `json:"source_dir"`
	BuiltAt      time.Time `json:"built_at"`
}

var buildCmd = &cobra.Command{
	Use:   "build",
	Short: "Build an agent bundle from the current directory",
	Long: `Package the current directory into a deployable bundle and upload it to
the Control Plane via a Conductor build workflow.

Run from the project directory containing agentspan.yaml — the same way
you would run 'firebase deploy' from your Firebase project root.

The resulting artifact ID is saved to ~/.agentspan/last-build.json so that
'agentspan deploy' can pick it up without requiring --artifact.`,
	Args: cobra.NoArgs,
	RunE: runBuildCmd,
}

func init() {
	rootCmd.AddCommand(buildCmd)
}

func runBuildCmd(cmd *cobra.Command, args []string) error {
	abs, err := filepath.Abs(".")
	if err != nil {
		return fmt.Errorf("resolve current dir: %w", err)
	}
	if _, err := os.Stat(filepath.Join(abs, "agentspan.yaml")); err != nil {
		return fmt.Errorf("agentspan.yaml not found in %s — run this command from your project directory", abs)
	}

	cfg := getConfig()
	cc := client.NewConductorClient(cfg.ConductorURL)
	ctx := context.Background()

	bold := color.New(color.Bold)
	bold.Printf("Building agent from %s\n", abs)
	fmt.Printf("  Control Plane: %s\n\n", cfg.ConductorURL)

	workflowID, err := cc.StartWorkflow(ctx, buildWorkflowName, buildWorkflowVersion, map[string]any{
		"source_dir": abs,
	})
	if err != nil {
		return fmt.Errorf("start build workflow: %w", err)
	}

	fmt.Printf("  Workflow: %s\n", workflowID)
	fmt.Print("  Building")

	status, err := cc.WaitForWorkflow(ctx, workflowID, func(s string) {
		fmt.Print(".")
	})
	fmt.Println()
	if err != nil {
		return err
	}

	fileHandleID, _ := status.Output["file_handle_id"].(string)
	bundleName, _ := status.Output["bundle_name"].(string)
	if fileHandleID == "" {
		return fmt.Errorf("build completed but no artifact ID returned")
	}

	state := lastBuildState{
		WorkflowID:   workflowID,
		FileHandleID: fileHandleID,
		BundleName:   bundleName,
		SourceDir:    abs,
		BuiltAt:      time.Now(),
	}
	if err := saveLastBuild(state); err != nil {
		color.New(color.FgYellow).Printf("  warning: could not save build state: %v\n", err)
	}

	fmt.Println()
	color.New(color.FgGreen, color.Bold).Println("  Build complete.")
	fmt.Printf("  Artifact : %s\n", fileHandleID)
	fmt.Printf("  Bundle   : %s\n", bundleName)
	fmt.Println()
	fmt.Println("Next: agentspan deploy")
	return nil
}

func saveLastBuild(state lastBuildState) error {
	if err := os.MkdirAll(agentspanConfigDir(), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(agentspanConfigDir(), lastBuildStateFile), data, 0o600)
}

func loadLastBuild() (*lastBuildState, error) {
	data, err := os.ReadFile(filepath.Join(agentspanConfigDir(), lastBuildStateFile))
	if err != nil {
		return nil, fmt.Errorf("no previous build found — run 'agentspan build' first")
	}
	var state lastBuildState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil, fmt.Errorf("parse last build state: %w", err)
	}
	return &state, nil
}

func agentspanConfigDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".agentspan")
}
