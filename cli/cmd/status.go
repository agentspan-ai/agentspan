// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status <execution-id>",
	Short: "Get the detailed status of an agent execution",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()
		c := newClient(cfg)

		detail, err := c.GetExecutionDetail(args[0])
		if err != nil {
			return fmt.Errorf("failed to get status: %w", err)
		}

		bold := color.New(color.Bold)
		bold.Printf("Execution: %s\n", detail.ExecutionID)
		fmt.Printf("  Agent:   %s (v%d)\n", detail.AgentName, detail.Version)

		statusColor := color.FgWhite
		switch detail.Status {
		case "RUNNING":
			statusColor = color.FgYellow
		case "PAUSED":
			statusColor = color.FgYellow
		case "COMPLETED":
			statusColor = color.FgGreen
		case "FAILED", "TERMINATED", "TIMED_OUT":
			statusColor = color.FgRed
		}
		color.New(statusColor, color.Bold).Printf("  Status:  %s\n", detail.Status)

		if detail.Input != nil {
			fmt.Printf("\nInput:\n")
			printJSON(detail.Input)
		}

		if detail.Output != nil {
			fmt.Printf("\nOutput:\n")
			printJSON(detail.Output)
		}

		if detail.CurrentTask != nil {
			fmt.Printf("\nCurrent Task:\n")
			fmt.Printf("  Name:   %s\n", detail.CurrentTask.TaskRefName)
			fmt.Printf("  Type:   %s\n", detail.CurrentTask.TaskType)
			fmt.Printf("  Status: %s\n", detail.CurrentTask.Status)
			if detail.CurrentTask.InputData != nil {
				fmt.Printf("  Input:\n")
				printJSON(detail.CurrentTask.InputData)
			}
			if detail.CurrentTask.OutputData != nil {
				fmt.Printf("  Output:\n")
				printJSON(detail.CurrentTask.OutputData)
			}
		}

		return nil
	},
}

func init() {
	agentCmd.AddCommand(statusCmd)
}
