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

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
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
	Long: `Boot the staged agent bundle in a Firecracker microVM via the Lima VM.

Reads metadata.customer/cluster/namespace/name from agentspan.yaml in the
current directory. The Rust API resolves the bundle path from Valkey.`,
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
	return runLimaInvoke(ref)
}

// runLimaInvoke calls the Rust API on the Lima host to boot the staged agent bundle.
func runLimaInvoke(ref *agentRef) error {
	cfg := config.Load()
	vmName := os.Getenv("LIMA_VM_NAME")
	if vmName == "" {
		vmName = os.Getenv("LIMA_VM")
	}
	if vmName == "" && cfg.LimaVMName != "" {
		vmName = cfg.LimaVMName
	}
	if vmName == "" {
		vmName = config.DefaultLimaVMName
	}

	apiPort := os.Getenv("AGENT_RUNNER_API_PORT")
	if apiPort == "" {
		apiPort = "7878"
	}

	// AGENTSPAN_SERVER_URL is injected by the runner from runner.local.toml [host] name.
	envMap := map[string]string{}
	if data, err := os.ReadFile(filepath.Join(".", "agentspan.yaml")); err == nil {
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

	type invokeReq struct {
		Customer  string            `json:"customer"`
		Cluster   string            `json:"cluster"`
		Namespace string            `json:"namespace"`
		AgentName string            `json:"agent_name"`
		Env       map[string]string `json:"env"`
	}
	payload, err := json.Marshal(invokeReq{
		Customer:  ref.Customer,
		Cluster:   ref.Cluster,
		Namespace: ref.Namespace,
		AgentName: ref.Name,
		Env:       envMap,
	})
	if err != nil {
		return fmt.Errorf("marshal invoke request: %w", err)
	}

	bold := color.New(color.Bold)
	bold.Printf("Invoking agent %q (%s/%s/%s) via Rust API on Lima VM %q\n",
		ref.Name, ref.Customer, ref.Cluster, ref.Namespace, vmName)
	fmt.Println()

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
