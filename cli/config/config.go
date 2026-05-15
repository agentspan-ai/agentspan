// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package config

import (
	"encoding/json"
	"net/url"
	"os"
	"path/filepath"
)

type Config struct {
	ServerURL    string `json:"server_url"`
	APIKey       string `json:"api_key,omitempty"`
	ConductorURL string `json:"conductor_url,omitempty"`
	LLMModel     string `json:"llm_model,omitempty"`
	ValkeyURL    string `json:"valkey_url,omitempty"`
}

// IsLocalhost returns true when the server URL points to a loopback address
// (localhost, 127.0.0.1, or ::1) over any scheme (http or https).
func (c *Config) IsLocalhost() bool {
	u, err := url.Parse(c.ServerURL)
	if err != nil {
		return false
	}
	host := u.Hostname()
	return host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]"
}

const (
	DefaultServerURL    = "http://localhost:6767"
	DefaultConductorURL = "http://localhost:8080/api"
	DefaultValkeyURL    = "redis://127.0.0.1:6379"
)

func DefaultConfig() *Config {
	return &Config{
		ServerURL:    DefaultServerURL,
		ConductorURL: DefaultConductorURL,
		ValkeyURL:    DefaultValkeyURL,
	}
}

func ConfigDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".agentspan")
}

func configPath() string {
	return filepath.Join(ConfigDir(), "config.json")
}

func Load() *Config {
	cfg := DefaultConfig()

	// Env vars override
	if url := os.Getenv("AGENTSPAN_SERVER_URL"); url != "" {
		cfg.ServerURL = url
	} else if url := os.Getenv("AGENT_SERVER_URL"); url != "" {
		cfg.ServerURL = url
	}
	if apiKey := os.Getenv("AGENTSPAN_API_KEY"); apiKey != "" {
		cfg.APIKey = apiKey
	}
	if url := os.Getenv("CONDUCTOR_URL"); url != "" {
		cfg.ConductorURL = url
	}
	if url := os.Getenv("VALKEY_URL"); url != "" {
		cfg.ValkeyURL = url
	}

	// File overrides (env vars take precedence)
	data, err := os.ReadFile(configPath())
	if err != nil {
		return cfg
	}
	var fileCfg Config
	if json.Unmarshal(data, &fileCfg) == nil {
		if cfg.ServerURL == DefaultServerURL && fileCfg.ServerURL != "" {
			cfg.ServerURL = fileCfg.ServerURL
		}
		if cfg.APIKey == "" {
			cfg.APIKey = fileCfg.APIKey
		}
		if fileCfg.ConductorURL != "" {
			cfg.ConductorURL = fileCfg.ConductorURL
		}
		if fileCfg.LLMModel != "" {
			cfg.LLMModel = fileCfg.LLMModel
		}
		if fileCfg.ValkeyURL != "" {
			cfg.ValkeyURL = fileCfg.ValkeyURL
		}
	}

	return cfg
}

func Save(cfg *Config) error {
	dir := ConfigDir()
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(configPath(), data, 0o600)
}
