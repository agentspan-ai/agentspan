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
	runSessionID string
	runNoStream  bool
)

var runCmd = &cobra.Command{
	Use:   "run [prompt]",
	Short: "Start an agent and stream its output",
	Long: `Start an agent with a prompt and stream the execution events in real-time.

Reads metadata.name from agentspan.yaml in the current directory, or use
--config to provide an explicit agent config file.`,
	Args: cobra.MinimumNArgs(1),
	RunE: runAgent,
}

var runConfigFile string

func init() {
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
	} else {
		ref := readAgentRef(".")
		if ref == nil {
			return fmt.Errorf("agentspan.yaml not found or missing required metadata fields — run from the agent project directory")
		}
		agentName := fmt.Sprintf("%s__%s__%s__%s", ref.Customer, ref.Cluster, ref.Namespace, ref.Name)
		bold := color.New(color.Bold)
		bold.Printf("Starting agent: %s\n", agentName)

		agentDef, err := c.GetAgent(agentName, nil)
		if err != nil {
			return fmt.Errorf("failed to get agent %q: %w", agentName, err)
		}
		startReq = &client.StartRequest{
			AgentConfig: agentDef,
			Prompt:      prompt,
		}
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

	for evt := range events {
		printSSEEvent(evt)
	}
	return <-done
}
