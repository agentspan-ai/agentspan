// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"fmt"
	"os"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
)

func getConfig() *config.Config {
	cfg := config.Load()
	if serverURL != "" {
		cfg.ServerURL = serverURL
		// An explicitly passed --server becomes the default for subsequent commands.
		// Notice goes to stderr so piped stdout (JSON output etc.) stays clean.
		if config.FileServerURL() != serverURL {
			if err := config.SaveDefaultServer(serverURL); err == nil {
				fmt.Fprintf(os.Stderr, "Default server set to %s (%s)\n", serverURL, config.ConfigDir())
			}
		}
	}
	return cfg
}

func newClient(cfg *config.Config) *client.Client {
	return client.New(cfg)
}
