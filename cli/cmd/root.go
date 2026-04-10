// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"os"

	"github.com/agentspan-ai/agentspan/cli/tui"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var (
	serverURL string
	Version   = "dev"
	Commit    = "none"
	Date      = "unknown"
)

var rootCmd = &cobra.Command{
	Use:   "agentspan",
	Short: "CLI for the AgentSpan runtime",
	Long:  "Create, run, and manage AI agents powered by the AgentSpan runtime.",
	// When invoked with no subcommand and stdout is a TTY, launch the TUI.
	RunE: func(cmd *cobra.Command, args []string) error {
		if isTTY() {
			return tui.Start(Version)
		}
		return cmd.Help()
	},
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print the CLI version",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("agentspan %s (commit: %s, built: %s)\n", Version, Commit, Date)
	},
}

// isTTY returns true if stdout is connected to a terminal.
func isTTY() bool {
	return term.IsTerminal(int(os.Stdout.Fd()))
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func init() {
	rootCmd.PersistentFlags().StringVar(&serverURL, "server", "", "Runtime server URL (default: http://localhost:6767)")
	rootCmd.AddCommand(versionCmd)
}
