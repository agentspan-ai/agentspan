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
	ServerURL  string `json:"server_url"`
	AuthKey    string `json:"auth_key,omitempty"`
	AuthSecret string `json:"auth_secret,omitempty"`
	APIKey     string `json:"api_key,omitempty"`
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

func DefaultConfig() *Config {
	return &Config{
		ServerURL: "http://localhost:8080",
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

	// Env vars override (AGENTSPAN_* primary, CONDUCTOR_* fallback)
	if url := os.Getenv("AGENTSPAN_SERVER_URL"); url != "" {
		cfg.ServerURL = url
	} else if url := os.Getenv("AGENT_SERVER_URL"); url != "" {
		cfg.ServerURL = url
	}
	if key := os.Getenv("AGENTSPAN_AUTH_KEY"); key != "" {
		cfg.AuthKey = key
	} else if key := os.Getenv("CONDUCTOR_AUTH_KEY"); key != "" {
		cfg.AuthKey = key
	}
	if secret := os.Getenv("AGENTSPAN_AUTH_SECRET"); secret != "" {
		cfg.AuthSecret = secret
	} else if secret := os.Getenv("CONDUCTOR_AUTH_SECRET"); secret != "" {
		cfg.AuthSecret = secret
	}

	// File overrides (env vars take precedence)
	data, err := os.ReadFile(configPath())
	if err != nil {
		return cfg
	}
	var fileCfg Config
	if json.Unmarshal(data, &fileCfg) == nil {
		if cfg.ServerURL == "http://localhost:8080" && fileCfg.ServerURL != "" {
			cfg.ServerURL = fileCfg.ServerURL
		}
		if cfg.AuthKey == "" && fileCfg.AuthKey != "" {
			cfg.AuthKey = fileCfg.AuthKey
		}
		if cfg.AuthSecret == "" && fileCfg.AuthSecret != "" {
			cfg.AuthSecret = fileCfg.AuthSecret
		}
		if cfg.APIKey == "" {
			cfg.APIKey = fileCfg.APIKey
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
