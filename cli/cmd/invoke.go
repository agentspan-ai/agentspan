// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const (
	invokeWorkflowName    = "agentspan_invoke"
	invokeWorkflowVersion = 1
)

// agentspanInvokeSpec is the minimal slice of agentspan.yaml we need at invoke/run time.
type agentspanInvokeSpec struct {
	Metadata struct {
		Customer  string `yaml:"customer"`
		Cluster   string `yaml:"cluster"`
		Namespace string `yaml:"namespace"`
		Name      string `yaml:"name"`
	} `yaml:"metadata"`
	Spec struct {
		Env []string `yaml:"env"`
	} `yaml:"spec"`
}

// agentRef holds the full agent identity read from agentspan.yaml.
type agentRef struct {
	Customer  string
	Cluster   string
	Namespace string
	Name      string
}

var invokeCmd = &cobra.Command{
	Use:   "invoke",
	Short: "Invoke a deployed agent in its execution environment",
	Long: `Boot the staged agent bundle in a Firecracker microVM via the Conductor workflow.

Reads metadata.customer/cluster/namespace/name from agentspan.yaml in the
current directory. The Rust worker resolves the bundle path from Valkey.`,
	Args: cobra.NoArgs,
	RunE: runInvokeCmd,
}

func init() {
	agentCmd.AddCommand(invokeCmd)
}

func runInvokeCmd(cmd *cobra.Command, args []string) error {
	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found or missing required metadata fields (customer, cluster, namespace, name)")
	}

	cfg := config.Load()
	cc := client.NewConductorClient(cfg.ConductorURL)
	ctx := context.Background()

	// Build env map from agentspan.yaml spec.env
	envMap := buildInvokeEnvMap(cfg)

	bold := color.New(color.Bold)
	bold.Printf("Invoking agent %q (%s/%s/%s)\n\n",
		ref.Name, ref.Customer, ref.Cluster, ref.Namespace)

	input := map[string]any{
		"customer":   ref.Customer,
		"cluster":    ref.Cluster,
		"namespace":  ref.Namespace,
		"agent_name": ref.Name,
		"env":        envMap,
	}

	workflowID, err := cc.StartWorkflow(ctx, invokeWorkflowName, invokeWorkflowVersion, input)
	if err != nil {
		return fmt.Errorf("start invoke workflow: %w", err)
	}
	fmt.Printf("  Workflow: %s\n", workflowID)
	fmt.Print("  Invoking")

	status, err := cc.WaitForWorkflow(ctx, workflowID, func(s string) {
		fmt.Print(".")
	})
	fmt.Println()
	if err != nil {
		return err
	}

	// Print agent output from workflow result
	fmt.Println()
	if output, ok := status.Output["output"].(string); ok && output != "" {
		fmt.Print(output)
	}

	exitCode := 0
	if ec, ok := status.Output["exit_code"].(float64); ok {
		exitCode = int(ec)
	}
	if exitCode != 0 {
		return fmt.Errorf("agent exited with code %d", exitCode)
	}
	return nil
}

// buildInvokeEnvMap reads agentspan.yaml spec.env and resolves values from
// environment variables or CLI config.
func buildInvokeEnvMap(cfg *config.Config) map[string]string {
	envMap := map[string]string{}
	data, err := os.ReadFile(filepath.Join(".", "agentspan.yaml"))
	if err != nil {
		return envMap
	}
	var spec agentspanInvokeSpec
	if yaml.Unmarshal(data, &spec) != nil {
		return envMap
	}
	for _, key := range spec.Spec.Env {
		if val := os.Getenv(key); val != "" {
			envMap[key] = val
		} else if key == "AGENTSPAN_LLM_MODEL" && cfg.LLMModel != "" {
			envMap[key] = cfg.LLMModel
		}
	}
	return envMap
}

// readAgentRef reads the full agent identity from agentspan.yaml in dir.
// Returns nil if any required field (customer, cluster, namespace, name) is missing.
func readAgentRef(dir string) *agentRef {
	data, err := os.ReadFile(filepath.Join(dir, "agentspan.yaml"))
	if err != nil {
		return nil
	}
	var spec agentspanInvokeSpec
	if yaml.Unmarshal(data, &spec) != nil {
		return nil
	}
	m := spec.Metadata
	if m.Customer == "" || m.Cluster == "" || m.Namespace == "" || m.Name == "" {
		return nil
	}
	return &agentRef{
		Customer:  m.Customer,
		Cluster:   m.Cluster,
		Namespace: m.Namespace,
		Name:      m.Name,
	}
}
