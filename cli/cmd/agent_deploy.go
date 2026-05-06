// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	deployWorkflowName    = "agentspan_deploy"
	deployWorkflowVersion = 7
	flagArtifact          = "artifact"
)

var agentDeployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Upload the built bundle and deploy the agent",
	Long: `Upload the locally-built bundle and provision the agent.

Reads ./dist/agent-bundle.tar.gz (override with --artifact) produced by
"agentspan agent build", uploads it, and runs the agentspan_deploy workflow.

Run from the project directory containing agentspan.yaml.`,
	Args: cobra.NoArgs,
	RunE: runAgentDeployCmd,
}

func init() {
	agentDeployCmd.Flags().String(flagArtifact, "", "Path to the built bundle (default: ./dist/agent-bundle.tar.gz)")
	agentCmd.AddCommand(agentDeployCmd)
}

func runAgentDeployCmd(cmd *cobra.Command, _ []string) error {
	cfg := getConfig()

	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found — run this command from your project directory")
	}

	artifactPath, _ := cmd.Flags().GetString(flagArtifact)
	if artifactPath == "" {
		artifactPath = filepath.Join(defaultOutputSubdir, artifactFileName)
	}
	info, err := os.Stat(artifactPath)
	if err != nil {
		return fmt.Errorf("no artifact at %s — run 'agentspan agent build' first", artifactPath)
	}

	bold := color.New(color.Bold)
	bold.Printf("Deploying agent: %s/%s/%s/%s\n", ref.Customer, ref.Cluster, ref.Namespace, ref.Name)
	fmt.Printf("  Conductor: %s\n", cfg.ConductorURL)
	fmt.Printf("  Artifact : %s (%.1f MB)\n\n", artifactPath, float64(info.Size())/1e6)

	cc := client.NewConductorClient(cfg.ConductorURL)

	// Ephemeral worker handles the UPLOAD_BUNDLE task; the artifact path stays in this
	// process and never enters the workflow input.
	worker := newBundleUploadWorker(cc, artifactPath, filepath.Base(artifactPath), artifactContentType, info.Size())
	taskDone := make(chan uploadResult, 1)
	workerCtx, stopWorker := context.WithCancel(cmd.Context())
	defer stopWorker()
	go worker.Run(workerCtx, taskDone)

	// Workflow input is the agent ref only — no path, no build id.
	workflowID, err := cc.StartWorkflow(cmd.Context(), deployWorkflowName, deployWorkflowVersion, map[string]any{
		"customer":  ref.Customer,
		"cluster":   ref.Cluster,
		"namespace": ref.Namespace,
		"name":      ref.Name,
	})
	if err != nil {
		return fmt.Errorf("start deploy workflow: %w", err)
	}
	fmt.Printf("  Workflow : %s\n", workflowID)
	fmt.Print("  Uploading + deploying")

	status, err := cc.WaitForWorkflow(cmd.Context(), workflowID, func(string) { fmt.Print(".") })
	fmt.Println()
	if err != nil {
		// Prefer the upload-side error if the failure originated there.
		select {
		case r := <-taskDone:
			if r.err != nil {
				return fmt.Errorf("upload bundle: %w", r.err)
			}
		default:
		}
		return err
	}
	stopWorker()

	deploymentID, _ := status.Output["deployment_id"].(string)
	fmt.Println()
	color.New(color.FgGreen, color.Bold).Println("  Deploy complete.")
	if deploymentID != "" {
		fmt.Printf("  Deployment: %s\n", deploymentID)
	}
	fmt.Println()
	fmt.Println("Next: agentspan agent serve")
	return nil
}
