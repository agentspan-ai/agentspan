// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"errors"
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

var (
	startTUI   = tui.Start
	isTerminal = term.IsTerminal
)

var rootCmd = &cobra.Command{
	Use:   "agentspan",
	Short: "CLI for the AgentSpan runtime",
	Long:  "Create, run, and manage AI agents powered by the AgentSpan runtime.",
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print the CLI version",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("agentspan %s (commit: %s, built: %s)\n", Version, Commit, Date)
	},
}

var tuiCmd = &cobra.Command{
	Use:          "tui",
	Short:        "Launch the interactive terminal UI",
	SilenceUsage: true,
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := requireInteractiveTerminal(os.Stdin, os.Stdout); err != nil {
			return err
		}
		return startTUI(Version)
	},
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func init() {
	rootCmd.PersistentFlags().StringVar(&serverURL, "server", "", "Runtime server URL (default: http://localhost:6767)")
	rootCmd.AddCommand(versionCmd)
	rootCmd.AddCommand(tuiCmd)
}

func requireInteractiveTerminal(stdin, stdout *os.File) error {
	if stdin == nil || stdout == nil {
		return errors.New("agentspan tui requires an interactive terminal (TTY)")
	}
	if !isTerminal(int(stdin.Fd())) || !isTerminal(int(stdout.Fd())) {
		return errors.New("agentspan tui requires an interactive terminal (TTY)")
	}
	return nil
}
