// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var deleteVersion int

var deleteCmd = &cobra.Command{
	Use:   "delete <name>",
	Short: "Delete an agent definition",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()
		c := newClient(cfg)

		var versionPtr *int
		if cmd.Flags().Changed("version") {
			versionPtr = &deleteVersion
		}

		if err := c.DeleteAgent(args[0], versionPtr); err != nil {
			return fmt.Errorf("failed to delete agent: %w", err)
		}

		if versionPtr != nil {
			color.Green("Deleted agent '%s' version %d", args[0], *versionPtr)
		} else {
			color.Green("Deleted agent '%s' (latest version)", args[0])
		}
		return nil
	},
}

func init() {
	deleteCmd.Flags().IntVar(&deleteVersion, "version", 0, "Agent version to delete (default: latest)")
	agentCmd.AddCommand(deleteCmd)
}
