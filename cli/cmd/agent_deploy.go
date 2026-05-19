// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	deployV6WorkflowName    = "agentspan_deploy"
	deployV6WorkflowVersion = 6
)

var agentDeployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy a built agent to the execution plane",
	Long: `Start an agentspan_deploy v6 workflow for the current agent.

The Rust runner looks up the build artifact from Valkey using the agent identity
(or --build-id if provided). The command fails immediately if no build is found.

Run from the project directory containing agentspan.yaml.`,
	Args: cobra.NoArgs,
	RunE: runAgentDeployCmd,
}

func init() {
	agentDeployCmd.Flags().String("build-id", "", "Deploy a specific build version (default: latest)")
	agentCmd.AddCommand(agentDeployCmd)
}

func runAgentDeployCmd(cmd *cobra.Command, args []string) error {
	cfg := getConfig()

	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found — run this command from your project directory")
	}

	buildID, _ := cmd.Flags().GetString("build-id")

	bold := color.New(color.Bold)
	bold.Printf("Deploying agent: %s/%s/%s/%s\n", ref.Customer, ref.Cluster, ref.Namespace, ref.Name)
	fmt.Printf("  Conductor: %s\n", cfg.ConductorURL)
	if buildID != "" {
		fmt.Printf("  Build ID : %s\n", buildID)
	}
	fmt.Println()

	cc := client.NewConductorClient(cfg.ConductorURL)

	input := map[string]any{
		"customer":  ref.Customer,
		"cluster":   ref.Cluster,
		"namespace": ref.Namespace,
		"name":      ref.Name,
	}
	if buildID != "" {
		input["build_id"] = buildID
	}

	workflowID, err := cc.StartWorkflow(cmd.Context(), deployV6WorkflowName, deployV6WorkflowVersion, input)
	if err != nil {
		return fmt.Errorf("start deploy workflow: %w", err)
	}

	fmt.Printf("  Workflow : %s\n", workflowID)
	fmt.Print("  Deploying")

	status, err := cc.WaitForWorkflow(cmd.Context(), workflowID, func(s string) {
		fmt.Print(".")
	})
	fmt.Println()
	if err != nil {
		return err
	}

	deploymentID, _ := status.Output["deployment_id"].(string)

	fmt.Println()
	color.New(color.FgGreen, color.Bold).Println("  Deploy complete.")
	if deploymentID != "" {
		fmt.Printf("  Deployment: %s\n", deploymentID)
	}
	fmt.Println()
	fmt.Println("Next: agentspan agent invoke")
	return nil
}
