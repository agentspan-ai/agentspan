// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"text/tabwriter"
	"time"

	"strings"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

// Flags for deploy list command
var (
	deployListAgent  string
	deployListStatus string
	deployListLimit  int
	deployListOffset int
	deployListJSON   bool
)

// DeploymentListResult from the ingest service
type DeploymentListResult struct {
	Deployments []*Deployment `json:"deployments"`
	Total       int           `json:"total"`
	Limit       int           `json:"limit"`
	Offset      int           `json:"offset"`
}

// Deployment represents a deployment record
type Deployment struct {
	DeployID     string         `json:"deployId"`
	TenantID     string         `json:"tenantId"`
	UserID       string         `json:"userId"`
	AgentName    string         `json:"agentName"`
	AgentVersion string         `json:"agentVersion"`
	Language     string         `json:"language"`
	EntryPoint   string         `json:"entryPoint"`
	ImageTag     string         `json:"imageTag,omitempty"`
	Resources    ResourceConfig `json:"resources"`
	AutoStart    bool           `json:"autoStart"`
	Status       string         `json:"status"`
	WorkflowID   string         `json:"workflowId,omitempty"`
	Error        string         `json:"error,omitempty"`
	CreatedAt    time.Time      `json:"createdAt"`
	CompletedAt  *time.Time     `json:"completedAt,omitempty"`
}

var deployListCmd = &cobra.Command{
	Use:   "list",
	Short: "List deployments",
	Long: `List deployments for the current tenant.

Deployments are build/deploy operations tracked in the system.
Use --status to filter by status: pending, building, completed, failed.

Example:
  agentspan deploy list
  agentspan deploy list --agent my-agent
  agentspan deploy list --status completed
  agentspan deploy list --json
`,
	RunE: runDeployList,
}

func init() {
	deployListCmd.Flags().StringVar(&deployListAgent, "agent", "", "Filter by agent name")
	deployListCmd.Flags().StringVar(&deployListStatus, "status", "", "Filter by status: pending, building, completed, failed")
	deployListCmd.Flags().IntVar(&deployListLimit, "limit", 20, "Maximum number of results")
	deployListCmd.Flags().IntVar(&deployListOffset, "offset", 0, "Offset for pagination")
	deployListCmd.Flags().BoolVar(&deployListJSON, "json", false, "Output as JSON")

	deployCmd.AddCommand(deployListCmd)
}

func runDeployList(cmd *cobra.Command, args []string) error {
	cfg := config.Load()
	if serverURL != "" {
		cfg.ServerURL = serverURL
	}

	// Derive ingest URL
	ingestURL := strings.TrimRight(cfg.ServerURL, "/")

	// Build query parameters
	params := url.Values{}
	if deployListAgent != "" {
		params.Set("agent", deployListAgent)
	}
	if deployListStatus != "" {
		params.Set("status", deployListStatus)
	}
	params.Set("limit", fmt.Sprintf("%d", deployListLimit))
	params.Set("offset", fmt.Sprintf("%d", deployListOffset))

	// Make request
	reqURL := ingestURL + "/v1/deployments?" + params.Encode()
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

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var result DeploymentListResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	// Output
	if deployListJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(result)
	}

	// Table output
	if len(result.Deployments) == 0 {
		fmt.Println("No deployments found")
		return nil
	}

	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "DEPLOY ID\tAGENT\tVERSION\tLANGUAGE\tSTATUS\tCREATED")
	for _, d := range result.Deployments {
		statusColor := statusToColor(d.Status)
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\n",
			d.DeployID,
			d.AgentName,
			d.AgentVersion,
			d.Language,
			statusColor.Sprint(d.Status),
			formatRelativeTime(d.CreatedAt),
		)
	}
	w.Flush()

	if result.Total > result.Limit+result.Offset {
		fmt.Printf("\nShowing %d-%d of %d (use --offset for more)\n",
			result.Offset+1, result.Offset+len(result.Deployments), result.Total)
	}

	return nil
}

func statusToColor(status string) *color.Color {
	switch status {
	case "completed":
		return color.New(color.FgGreen)
	case "failed":
		return color.New(color.FgRed)
	case "building", "pushing", "deploying":
		return color.New(color.FgYellow)
	default:
		return color.New(color.FgWhite)
	}
}

func formatRelativeTime(t time.Time) string {
	diff := time.Since(t)
	switch {
	case diff < time.Minute:
		return "just now"
	case diff < time.Hour:
		return fmt.Sprintf("%dm ago", int(diff.Minutes()))
	case diff < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(diff.Hours()))
	case diff < 7*24*time.Hour:
		return fmt.Sprintf("%dd ago", int(diff.Hours()/24))
	default:
		return t.Format("2006-01-02")
	}
}
