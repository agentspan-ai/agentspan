// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var pruneOlderThan string

var serverPruneCmd = &cobra.Command{
	Use:   "prune",
	Short: "Delete completed execution records older than a given age",
	Long: `Search for completed (COMPLETED, FAILED, TERMINATED) execution records
older than the specified duration and permanently delete them from the database.

Duration format: 30s, 5m, 1h, 6h, 1d, 7d, 1mo, 1y

Examples:
  agentspan server prune --older-than 30d
  agentspan server prune --older-than 7d`,
	RunE: runServerPrune,
}

func init() {
	serverPruneCmd.Flags().StringVar(&pruneOlderThan, "older-than", "", "Delete executions older than this duration (e.g. 30d, 7d, 1mo) [required]")
	_ = serverPruneCmd.MarkFlagRequired("older-than")
	serverCmd.AddCommand(serverPruneCmd)
}

func runServerPrune(cmd *cobra.Command, args []string) error {
	dur, err := parseTimeSpec(pruneOlderThan)
	if err != nil {
		return fmt.Errorf("invalid --older-than value: %w", err)
	}

	cutoff := time.Now().Add(-dur)
	cutoffMs := cutoff.UnixMilli()

	cfg := getConfig()
	c := newClient(cfg)

	// Search for terminal executions older than the cutoff across all statuses.
	terminalStatuses := []string{"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"}

	var allIDs []string
	for _, status := range terminalStatuses {
		freeText := fmt.Sprintf("startTime:[* TO %d]", cutoffMs)
		result, err := c.SearchExecutions(0, 1000, "", status, freeText)
		if err != nil {
			return fmt.Errorf("failed to search %s executions: %w", status, err)
		}
		for _, ex := range result.Results {
			allIDs = append(allIDs, ex.ExecutionID)
		}
	}

	if len(allIDs) == 0 {
		color.Yellow("No executions found older than %s.", pruneOlderThan)
		return nil
	}

	color.Yellow("Found %d execution(s) older than %s (before %s).",
		len(allIDs), pruneOlderThan, cutoff.Format("2006-01-02 15:04:05"))
	fmt.Printf("Deleting %d execution record(s)...\n", len(allIDs))

	if err := c.BulkDeleteExecutions(allIDs); err != nil {
		return fmt.Errorf("bulk delete failed: %w", err)
	}

	color.Green("Successfully deleted %d execution record(s).", len(allIDs))
	return nil
}
