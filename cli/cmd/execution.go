// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"text/tabwriter"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var (
	execName   string
	execSince  string
	execWindow string
	execStatus string
)

var executionCmd = &cobra.Command{
	Use:   "execution",
	Short: "Search agent execution history",
	Long: `Search agent execution history with optional filters.

Time formats for --since and --window:
  30s, 5m, 1h, 6h, 1d, 7d, 1mo, 1y

Examples:
  agentspan agent execution --since 1h
  agentspan agent execution --name mybot --since 1d
  agentspan agent execution --status COMPLETED --since 7d`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()
		c := newClient(cfg)

		// Build freeText query for time filtering
		freeText := ""
		if execSince != "" {
			dur, err := parseTimeSpec(execSince)
			if err != nil {
				return fmt.Errorf("invalid --since value: %w", err)
			}
			startTime := time.Now().Add(-dur).UnixMilli()
			freeText = fmt.Sprintf("startTime:[%d TO *]", startTime)
		}

		if execWindow != "" {
			// Parse window format: "now-1h" or just "1h" (relative to now)
			windowStr := execWindow
			if len(windowStr) > 4 && windowStr[:4] == "now-" {
				windowStr = windowStr[4:]
			}
			dur, err := parseTimeSpec(windowStr)
			if err != nil {
				return fmt.Errorf("invalid --window value: %w", err)
			}
			endTime := time.Now().UnixMilli()
			startTime := time.Now().Add(-dur).UnixMilli()
			windowQuery := fmt.Sprintf("startTime:[%d TO %d]", startTime, endTime)
			if freeText != "" {
				freeText += " AND " + windowQuery
			} else {
				freeText = windowQuery
			}
		}

		result, err := c.SearchExecutions(0, 50, execName, execStatus, freeText)
		if err != nil {
			return fmt.Errorf("failed to search executions: %w", err)
		}

		if len(result.Results) == 0 {
			color.Yellow("No executions found.")
			return nil
		}

		w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
		fmt.Fprintln(w, "ID\tAGENT\tSTATUS\tSTART TIME\tDURATION")
		fmt.Fprintln(w, "--\t-----\t------\t----------\t--------")

		for _, ex := range result.Results {
			duration := ""
			if ex.ExecutionTime > 0 {
				duration = formatDuration(time.Duration(ex.ExecutionTime) * time.Millisecond)
			}
			startTime := ex.StartTime
			if len(startTime) > 19 {
				startTime = startTime[:19]
			}

			statusStr := ex.Status
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n",
				ex.ExecutionID, ex.AgentName, statusStr, startTime, duration)
		}
		w.Flush()

		fmt.Printf("\n%d of %d execution(s).\n", len(result.Results), result.TotalHits)
		return nil
	},
}

func init() {
	executionCmd.Flags().StringVar(&execName, "name", "", "Filter by agent name")
	executionCmd.Flags().StringVar(&execSince, "since", "", "Show executions since (e.g. 30m, 1h, 1d, 1mo)")
	executionCmd.Flags().StringVar(&execWindow, "window", "", "Time window (e.g. now-1h, now-7d)")
	executionCmd.Flags().StringVar(&execStatus, "status", "", "Filter by status (RUNNING, COMPLETED, FAILED, etc.)")
	agentCmd.AddCommand(executionCmd)
}

// parseTimeSpec parses time strings like "30s", "5m", "1h", "1d", "1mo", "1y"
func parseTimeSpec(s string) (time.Duration, error) {
	re := regexp.MustCompile(`^(\d+)(s|m|h|d|mo|y)$`)
	matches := re.FindStringSubmatch(s)
	if matches == nil {
		return 0, fmt.Errorf("expected format like 30s, 5m, 1h, 1d, 1mo, 1y; got %q", s)
	}

	n, _ := strconv.Atoi(matches[1])
	unit := matches[2]

	switch unit {
	case "s":
		return time.Duration(n) * time.Second, nil
	case "m":
		return time.Duration(n) * time.Minute, nil
	case "h":
		return time.Duration(n) * time.Hour, nil
	case "d":
		return time.Duration(n) * 24 * time.Hour, nil
	case "mo":
		return time.Duration(n) * 30 * 24 * time.Hour, nil
	case "y":
		return time.Duration(n) * 365 * 24 * time.Hour, nil
	default:
		return 0, fmt.Errorf("unknown unit: %s", unit)
	}
}

func formatDuration(d time.Duration) string {
	if d < time.Second {
		return fmt.Sprintf("%dms", d.Milliseconds())
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs", d.Seconds())
	}
	if d < time.Hour {
		return fmt.Sprintf("%.1fm", d.Minutes())
	}
	return fmt.Sprintf("%.1fh", d.Hours())
}
