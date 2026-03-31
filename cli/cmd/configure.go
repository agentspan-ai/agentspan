// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"

	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var configureCmd = &cobra.Command{
	Use:   "configure",
	Short: "Configure the CLI (server URL, auth credentials)",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := config.Load()

		if url, _ := cmd.Flags().GetString("url"); url != "" {
			cfg.ServerURL = url
		}
		if key, _ := cmd.Flags().GetString("auth-key"); key != "" {
			cfg.AuthKey = key
		}
		if secret, _ := cmd.Flags().GetString("auth-secret"); secret != "" {
			cfg.AuthSecret = secret
		}

		if err := config.Save(cfg); err != nil {
			return fmt.Errorf("failed to save config: %w", err)
		}

		color.Green("Configuration saved!")
		fmt.Printf("  Server URL: %s\n", cfg.ServerURL)
		if cfg.AuthKey != "" {
			fmt.Printf("  Auth Key:   %s\n", cfg.AuthKey)
		}
		return nil
	},
}

func init() {
	configureCmd.Flags().String("url", "", "Runtime server URL")
	configureCmd.Flags().String("auth-key", "", "Auth key")
	configureCmd.Flags().String("auth-secret", "", "Auth secret")
	rootCmd.AddCommand(configureCmd)
}
