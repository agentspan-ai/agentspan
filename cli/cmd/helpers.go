// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/spf13/cobra"
)

func getConfig() *config.Config {
	cfg := config.Load()
	if agentspanURL != "" {
		cfg.AgentspanURL = agentspanURL
	}
	if conductorURL != "" {
		cfg.ConductorURL = conductorURL
	}
	return cfg
}

func newClient(cfg *config.Config) *client.Client {
	return client.New(cfg)
}

// cmdContext returns cmd.Context() wrapped with the --timeout flag value (default 300s).
// The caller must call cancel when the operation completes.
func cmdContext(cmd *cobra.Command) (context.Context, context.CancelFunc) {
	secs, err := cmd.Flags().GetInt("timeout")
	if err != nil || secs <= 0 {
		secs = 300
	}
	return context.WithTimeout(cmd.Context(), time.Duration(secs)*time.Second)
}
