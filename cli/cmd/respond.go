// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var (
	respondApprove bool
	respondDeny    bool
	respondReason  string
	respondMessage string
)

var respondCmd = &cobra.Command{
	Use:   "respond <execution-id>",
	Short: "Respond to a human-in-the-loop task",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if respondApprove && respondDeny {
			return fmt.Errorf("cannot specify both --approve and --deny")
		}
		if !respondApprove && !respondDeny {
			return fmt.Errorf("specify either --approve or --deny")
		}

		cfg := getConfig()
		c := newClient(cfg)

		approved := respondApprove

		if err := c.Respond(args[0], approved, respondReason, respondMessage); err != nil {
			return fmt.Errorf("failed to respond: %w", err)
		}

		if approved {
			color.Green("Response sent: approved")
		} else {
			color.Yellow("Response sent: denied")
		}
		if respondReason != "" {
			fmt.Printf("  Reason: %s\n", respondReason)
		}

		return nil
	},
}

func init() {
	respondCmd.Flags().BoolVar(&respondApprove, "approve", false, "Approve the pending action")
	respondCmd.Flags().BoolVar(&respondDeny, "deny", false, "Deny the pending action")
	respondCmd.Flags().StringVar(&respondReason, "reason", "", "Reason for the response")
	respondCmd.Flags().StringVarP(&respondMessage, "message", "m", "", "Message to send back")
	agentCmd.AddCommand(respondCmd)
}
