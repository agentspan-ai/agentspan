// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"strings"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var (
	runAgentName string
	runSessionID string
	runNoStream  bool
)

var runCmd = &cobra.Command{
	Use:   "run [prompt]",
	Short: "Start an agent and stream its output",
	Long: `Start an agent by name or config file with a prompt,
and stream the execution events in real-time.

Use --name for a previously deployed agent, or --config for a local config file.`,
	Args: cobra.MinimumNArgs(1),
	RunE: runAgent,
}

var runConfigFile string

func init() {
	runCmd.Flags().StringVar(&runAgentName, "name", "", "Name of a registered agent to run")
	runCmd.Flags().StringVar(&runConfigFile, "config", "", "Path to agent config file (YAML/JSON)")
	runCmd.Flags().StringVar(&runSessionID, "session", "", "Session ID for conversation continuity")
	runCmd.Flags().BoolVar(&runNoStream, "no-stream", false, "Don't stream events, just return the execution ID")
	agentCmd.AddCommand(runCmd)
}

func runAgent(cmd *cobra.Command, args []string) error {
	prompt := strings.Join(args, " ")

	cfg := getConfig()
	c := newClient(cfg)

	var startReq *client.StartRequest

	if runConfigFile != "" {
		// Config file mode (existing behavior)
		agentConfig, err := loadAgentConfig(runConfigFile)
		if err != nil {
			return err
		}
		bold := color.New(color.Bold)
		bold.Printf("Starting agent: %s\n", agentConfig["name"])
		startReq = &client.StartRequest{
			AgentConfig: agentConfig,
			Prompt:      prompt,
		}
	} else if runAgentName != "" {
		// Name mode: fetch agent def, then start with it
		bold := color.New(color.Bold)
		bold.Printf("Starting agent: %s\n", runAgentName)

		agentDef, err := c.GetAgent(runAgentName, nil)
		if err != nil {
			return fmt.Errorf("failed to get agent '%s': %w", runAgentName, err)
		}
		startReq = &client.StartRequest{
			AgentConfig: agentDef,
			Prompt:      prompt,
		}
	} else {
		return fmt.Errorf("specify either --name or --config")
	}

	if runSessionID != "" {
		startReq.SessionID = runSessionID
	}

	resp, err := c.Start(startReq)
	if err != nil {
		return fmt.Errorf("failed to start agent: %w", err)
	}

	fmt.Printf("Agent: %s (Execution: %s)\n", resp.AgentName, resp.ExecutionID)

	if runNoStream {
		return nil
	}

	fmt.Println()
	return streamExecution(c, resp.ExecutionID, "")
}

func streamExecution(c *client.Client, executionID string, lastEventID string) error {
	events := make(chan client.SSEEvent, 100)
	done := make(chan error, 1)

	c.Stream(executionID, lastEventID, events, done)

	// Drain all events first, then read the final error from done.
	// This avoids a non-deterministic select race where Go could pick
	// the closed events channel over a real error sitting in done.
	for evt := range events {
		printSSEEvent(evt)
	}
	return <-done
}
