// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"strings"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

// Flags for deploy get command
var (
	deployGetJSON bool
)

var deployGetCmd = &cobra.Command{
	Use:   "get <deploy-id>",
	Short: "Get deployment details",
	Long: `Get detailed information about a specific deployment.

Example:
  agentspan deploy get deploy-abc123
  agentspan deploy get deploy-abc123 --json
`,
	Args: cobra.ExactArgs(1),
	RunE: runDeployGet,
}

func init() {
	deployGetCmd.Flags().BoolVar(&deployGetJSON, "json", false, "Output as JSON")

	deployCmd.AddCommand(deployGetCmd)
}

func runDeployGet(cmd *cobra.Command, args []string) error {
	deployID := args[0]

	cfg := config.Load()
	if serverURL != "" {
		cfg.ServerURL = serverURL
	}

	// Derive ingest URL
	ingestURL := strings.TrimRight(cfg.ServerURL, "/")

	// Make request
	reqURL := ingestURL + "/v1/deployments/" + deployID
	req, err := http.NewRequest("GET", reqURL, nil)
	if err != nil {
		return err
	}

	// Add auth headers
	if cfg.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.APIKey)
	} else {
		if cfg.AuthKey != "" {
			req.Header.Set("X-Auth-Key", cfg.AuthKey)
		}
		if cfg.AuthSecret != "" {
			req.Header.Set("X-Auth-Secret", cfg.AuthSecret)
		}
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("deployment not found: %s", deployID)
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var d Deployment
	if err := json.NewDecoder(resp.Body).Decode(&d); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	// Output
	if deployGetJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(d)
	}

	// Pretty print
	printDeploymentDetails(&d)
	return nil
}

func printDeploymentDetails(d *Deployment) {
	statusColor := statusToColor(d.Status)

	fmt.Println()
	color.New(color.Bold).Printf("Deployment: %s\n", d.DeployID)
	fmt.Println()

	fmt.Printf("  Agent:     %s@%s\n", d.AgentName, d.AgentVersion)
	fmt.Printf("  Language:  %s\n", d.Language)
	fmt.Printf("  Entry:     %s\n", d.EntryPoint)
	fmt.Printf("  Status:    %s\n", statusColor.Sprint(d.Status))

	if d.ImageTag != "" {
		fmt.Printf("  Image:     %s\n", d.ImageTag)
	}
	if d.WorkflowID != "" {
		fmt.Printf("  Workflow:  %s\n", d.WorkflowID)
	}
	if d.Error != "" {
		color.New(color.FgRed).Printf("  Error:     %s\n", d.Error)
	}

	fmt.Println()
	fmt.Printf("  Resources:\n")
	fmt.Printf("    CPU:       %s (limit: %s)\n", d.Resources.CPURequest, d.Resources.CPULimit)
	fmt.Printf("    Memory:    %s (limit: %s)\n", d.Resources.MemoryRequest, d.Resources.MemoryLimit)
	fmt.Printf("    Replicas:  %d\n", d.Resources.Replicas)
	fmt.Printf("    Timeout:   %ds\n", d.Resources.Timeout)

	fmt.Println()
	fmt.Printf("  AutoStart:  %t\n", d.AutoStart)
	fmt.Printf("  Created:    %s (%s)\n", d.CreatedAt.Format(time.RFC3339), formatRelativeTime(d.CreatedAt))
	if d.CompletedAt != nil {
		fmt.Printf("  Completed:  %s (%s)\n", d.CompletedAt.Format(time.RFC3339), formatRelativeTime(*d.CompletedAt))
	}
	fmt.Println()
}
