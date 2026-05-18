// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

var (
	initModel    string
	initStrategy string
	initFormat   string
)

var initCmd = &cobra.Command{
	Use:   "init <agent-name>",
	Short: "Create a new agent config file",
	Long:  "Generate a starter agent config YAML/JSON file with sensible defaults.",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		model := initModel
		if model == "" {
			model = "openai/gpt-4o"
		}

		agentConfig := map[string]interface{}{
			"name":         name,
			"description":  fmt.Sprintf("%s agent", name),
			"model":        model,
			"instructions": fmt.Sprintf("You are %s, a helpful AI assistant.", name),
			"maxTurns":     25,
			"tools":        []interface{}{},
		}

		if initStrategy != "" {
			agentConfig["strategy"] = initStrategy
		}

		var data []byte
		var ext string
		var err error

		if initFormat == "json" {
			ext = "json"
			data, err = marshalJSON(agentConfig)
		} else {
			ext = "yaml"
			data, err = yaml.Marshal(agentConfig)
		}
		if err != nil {
			return err
		}

		filename := fmt.Sprintf("%s.%s", name, ext)
		if err := os.WriteFile(filename, data, 0o644); err != nil {
			return fmt.Errorf("write file: %w", err)
		}

		color.Green("Created %s", filename)
		fmt.Println("\nEdit the file to add tools, instructions, and other settings.")
		fmt.Printf("Run with: agentspan agent run --config %s.%s \"your prompt here\"\n", name, ext)
		return nil
	},
}

func marshalJSON(v interface{}) ([]byte, error) {
	return json.MarshalIndent(v, "", "  ")
}

func init() {
	initCmd.Flags().StringVarP(&initModel, "model", "m", "", "LLM model (default: openai/gpt-4o)")
	initCmd.Flags().StringVarP(&initStrategy, "strategy", "s", "", "Multi-agent strategy (handoff, sequential, parallel, etc.)")
	initCmd.Flags().StringVarP(&initFormat, "format", "f", "yaml", "Output format: yaml or json")
	agentCmd.AddCommand(initCmd)
}
