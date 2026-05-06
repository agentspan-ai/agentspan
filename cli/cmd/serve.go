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
	serveWorkflowName    = "agentspan_scale"
	serveWorkflowVersion = 1
)

// agentspanInvokeSpec is the minimal slice of agentspan.yaml we need at serve/run time.
type agentspanInvokeSpec struct {
	Metadata struct {
		Customer  string `yaml:"customer"`
		Cluster   string `yaml:"cluster"`
		Namespace string `yaml:"namespace"`
		Name      string `yaml:"name"`
	} `yaml:"metadata"`
	Spec struct {
		Env       []string       `yaml:"env"`
		Resources agentResources `yaml:"resources"`
	} `yaml:"spec"`
}

// agentResources mirrors the spec.resources block in agentspan.yaml.
type agentResources struct {
	CPU     string `yaml:"cpu"`
	CPUTime string `yaml:"cpu_time"`
	Memory  string `yaml:"memory"`
	Storage string `yaml:"storage"`
}

// agentRef holds the full agent identity read from agentspan.yaml.
type agentRef struct {
	Customer  string
	Cluster   string
	Namespace string
	Name      string
}

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Start (or stop) a deployed agent",
	Long: `Start a deployed agent by scaling to the configured replica count.

Without --scale, the runner uses the scaling.replicas value resolved from the
config layer chain (system-default → ops layers → agent manifest).

  agent serve              boot using config-resolved replica count
  agent serve --scale 3   scale to exactly 3 replicas (durable: persisted to config layer)
  agent serve --scale 0   stop all running replicas

Reads metadata from agentspan.yaml in the current directory.`,
	Args: cobra.NoArgs,
	RunE: runServeCmd,
}

func init() {
	serveCmd.Flags().Int("scale", 0, "Desired replica count (omit to use config-resolved value)")
	agentCmd.AddCommand(serveCmd)
}

func runServeCmd(cmd *cobra.Command, args []string) error {
	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found or missing required metadata fields (customer, cluster, namespace, name)")
	}

	cfg := getConfig()
	cc := client.NewConductorClient(cfg.ConductorURL)
	ctx := context.Background()

	scaleSet := cmd.Flags().Changed("scale")
	scaleVal, _ := cmd.Flags().GetInt("scale")
	if scaleSet && scaleVal < 0 {
		return fmt.Errorf("--scale must be >= 0")
	}

	bold := color.New(color.Bold)
	if scaleSet {
		bold.Printf("Serving agent: %s/%s/%s/%s  →  %d replicas\n",
			ref.Customer, ref.Cluster, ref.Namespace, ref.Name, scaleVal)
	} else {
		bold.Printf("Serving agent: %s/%s/%s/%s\n",
			ref.Customer, ref.Cluster, ref.Namespace, ref.Name)
	}
	fmt.Printf("  Conductor: %s\n\n", cfg.ConductorURL)

	// Build workflow input. Omit desired_replicas when not set → ScaleWorker uses resolved config.
	input := map[string]any{
		"customer":   ref.Customer,
		"cluster":    ref.Cluster,
		"namespace":  ref.Namespace,
		"agent_name": ref.Name,
		"env":        buildServeEnvMap(cfg),
	}
	if scaleSet {
		input["desired_replicas"] = scaleVal
	}

	workflowID, err := cc.StartWorkflow(ctx, serveWorkflowName, serveWorkflowVersion, input)
	if err != nil {
		return fmt.Errorf("start serve workflow: %w", err)
	}
	fmt.Printf("  Workflow : %s\n", workflowID)
	fmt.Print("  Reconciling")

	status, err := cc.WaitForWorkflow(ctx, workflowID, func(s string) {
		fmt.Print(".")
	})
	fmt.Println()
	if err != nil {
		return err
	}

	running, _ := status.Output["running"].(float64)
	desired, _ := status.Output["desired"].(float64)
	shortfall, _ := status.Output["shortfall"].(float64)

	fmt.Println()
	if scaleSet && scaleVal == 0 {
		color.New(color.FgGreen, color.Bold).Println("  All instances stopped.")
	} else if shortfall > 0 {
		color.New(color.FgYellow, color.Bold).Printf("  Partial: running %d / desired %d (shortfall %d — capacity limited)\n",
			int(running), int(desired), int(shortfall))
	} else {
		color.New(color.FgGreen, color.Bold).Printf("  Running: %d / %d\n", int(running), int(desired))
	}
	fmt.Println()
	return nil
}

// buildServeEnvMap reads agentspan.yaml spec.env and resolves values from
// environment variables or CLI config.
func buildServeEnvMap(cfg *config.Config) map[string]string {
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

// readResources reads spec.resources from agentspan.yaml in dir.
// Returns nil if the file is missing or spec.resources is empty.
func readResources(dir string) *agentResources {
	data, err := os.ReadFile(filepath.Join(dir, "agentspan.yaml"))
	if err != nil {
		return nil
	}
	var spec agentspanInvokeSpec
	if yaml.Unmarshal(data, &spec) != nil {
		return nil
	}
	r := spec.Spec.Resources
	if r.CPU == "" && r.CPUTime == "" && r.Memory == "" && r.Storage == "" {
		return nil
	}
	return &r
}
