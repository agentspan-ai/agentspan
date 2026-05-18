// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var streamLastEventID string

var streamCmd = &cobra.Command{
	Use:   "stream <execution-id>",
	Short: "Stream events from a running agent",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()
		c := newClient(cfg)

		executionID := args[0]
		fmt.Printf("Streaming events for %s...\n\n", executionID)

		return streamExecution(c, executionID, streamLastEventID)
	},
}

func init() {
	streamCmd.Flags().StringVar(&streamLastEventID, "last-event-id", "", "Resume from a specific event ID")
	agentCmd.AddCommand(streamCmd)
}
