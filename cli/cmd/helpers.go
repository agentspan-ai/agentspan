// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
)

func getConfig() *config.Config {
	cfg := config.Load()
	if serverURL != "" {
		cfg.ServerURL = serverURL
	}
	return cfg
}

func newClient(cfg *config.Config) *client.Client {
	return client.New(cfg)
}
