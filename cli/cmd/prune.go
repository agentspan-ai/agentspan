// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var (
	pruneOlderThan  int
	pruneArchive    bool
	pruneDryRun     bool
)

var serverPruneCmd = &cobra.Command{
	Use:   "prune",
	Short: "Delete completed/failed execution records older than N days",
	Long: `Bulk-delete terminal execution records (COMPLETED, FAILED, TERMINATED, TIMED_OUT)
whose end time is older than the specified number of days.

Examples:
  agentspan server prune --older-than 30
  agentspan server prune --older-than 7 --archive`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if pruneDryRun {
			color.Yellow("Dry-run: would delete executions older than %d day(s).", pruneOlderThan)
			return nil
		}

		cfg := getConfig()
		c := newClient(cfg)

		deleted, err := c.PruneExecutions(pruneOlderThan, pruneArchive)
		if err != nil {
			return fmt.Errorf("prune failed: %w", err)
		}

		if deleted == 0 {
			color.Yellow("No executions found older than %d day(s).", pruneOlderThan)
		} else {
			color.Green("Deleted %d execution record(s) older than %d day(s).", deleted, pruneOlderThan)
		}
		return nil
	},
}

func init() {
	serverPruneCmd.Flags().IntVar(&pruneOlderThan, "older-than", 30, "Delete executions older than this many days")
	serverPruneCmd.Flags().BoolVar(&pruneArchive, "archive", false, "Archive task records instead of hard-deleting them")
	serverPruneCmd.Flags().BoolVar(&pruneDryRun, "dry-run", false, "Show what would be deleted without deleting")

	serverCmd.AddCommand(serverPruneCmd)
}
