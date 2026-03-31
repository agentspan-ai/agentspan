// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

var agentCmd = &cobra.Command{
	Use:     "agent",
	Aliases: []string{"a"},
	Short:   "Manage agents",
}

func init() {
	rootCmd.AddCommand(agentCmd)
}

// loadAgentConfig reads a YAML or JSON agent config file into a map
func loadAgentConfig(path string) (map[string]interface{}, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config file: %w", err)
	}

	var cfg map[string]interface{}

	// Try YAML first (superset of JSON)
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		// Fall back to JSON
		if err := json.Unmarshal(data, &cfg); err != nil {
			return nil, fmt.Errorf("parse config file (tried YAML and JSON): %w", err)
		}
	}

	return cfg, nil
}

// printJSON pretty-prints a value as JSON
func printJSON(v interface{}) {
	data, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(data))
}

// printSSEEvent formats and prints an SSE event
func printSSEEvent(evt client.SSEEvent) {
	var data map[string]interface{}
	if err := json.Unmarshal([]byte(evt.Data), &data); err != nil {
		// Not JSON, print raw
		if evt.Event != "" {
			fmt.Printf("[%s] %s\n", evt.Event, evt.Data)
		}
		return
	}

	eventType := evt.Event
	if eventType == "" {
		if t, ok := data["type"].(string); ok {
			eventType = t
		}
	}

	switch eventType {
	case "thinking":
		color.New(color.FgHiBlack).Printf("  [thinking] %s\n", truncate(dataStr(data, "message"), 120))
	case "tool_call":
		color.New(color.FgCyan).Printf("  [tool] %s(%s)\n", dataStr(data, "toolName"), truncate(dataStr(data, "input"), 100))
	case "tool_result":
		result := truncate(dataStr(data, "result"), 200)
		color.New(color.FgCyan).Printf("  [result] %s -> %s\n", dataStr(data, "toolName"), result)
	case "handoff":
		color.New(color.FgYellow).Printf("  [handoff] -> %s\n", dataStr(data, "agentName"))
	case "message":
		content := dataStr(data, "content")
		if content != "" {
			fmt.Print(content)
		}
	case "waiting":
		color.New(color.FgYellow, color.Bold).Printf("  [waiting] Human input required (execution: %s)\n", dataStr(data, "executionId"))
	case "guardrail_pass":
		color.New(color.FgGreen).Printf("  [guardrail] PASS %s\n", dataStr(data, "guardrailName"))
	case "guardrail_fail":
		color.New(color.FgRed).Printf("  [guardrail] FAIL %s: %s\n", dataStr(data, "guardrailName"), dataStr(data, "reason"))
	case "error":
		color.New(color.FgRed, color.Bold).Printf("  [error] %s\n", dataStr(data, "message"))
	case "done":
		output := dataStr(data, "output")
		if output != "" {
			fmt.Println()
			color.New(color.Bold).Println(output)
		}
	default:
		if eventType != "" {
			fmt.Printf("  [%s] %s\n", eventType, truncate(evt.Data, 150))
		}
	}
}

func dataStr(data map[string]interface{}, key string) string {
	if v, ok := data[key]; ok {
		switch val := v.(type) {
		case string:
			return val
		default:
			b, _ := json.Marshal(val)
			return string(b)
		}
	}
	return ""
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}
