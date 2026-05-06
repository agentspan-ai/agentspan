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
	AgentspanURL string `json:"agentspan_url"`
	APIKey       string `json:"api_key,omitempty"`
	ConductorURL string `json:"conductor_url,omitempty"`
	LLMModel     string `json:"llm_model,omitempty"`
}

// IsLocalhost returns true when the server URL points to a loopback address
// (localhost, 127.0.0.1, or ::1) over any scheme (http or https).
func (c *Config) IsLocalhost() bool {
	u, err := url.Parse(c.AgentspanURL)
	if err != nil {
		return false
	}
	host := u.Hostname()
	return host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]"
}

const (
	DefaultAgentspanURL = "http://localhost:6767/api"
	DefaultConductorURL = "http://localhost:8080/api"
)

func DefaultConfig() *Config {
	return &Config{
		AgentspanURL: DefaultAgentspanURL,
		ConductorURL: DefaultConductorURL,
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

	// Step 1: file overrides code defaults.
	data, err := os.ReadFile(configPath())
	if err == nil {
		var fileCfg Config
		if json.Unmarshal(data, &fileCfg) == nil {
			// Backward compat: old configs stored "server_url" instead of "agentspan_url".
			if fileCfg.AgentspanURL == "" {
				var raw map[string]string
				if json.Unmarshal(data, &raw) == nil {
					fileCfg.AgentspanURL = raw["server_url"]
				}
			}
			if fileCfg.AgentspanURL != "" {
				cfg.AgentspanURL = fileCfg.AgentspanURL
			}
			if fileCfg.APIKey != "" {
				cfg.APIKey = fileCfg.APIKey
			}
			if fileCfg.ConductorURL != "" {
				cfg.ConductorURL = fileCfg.ConductorURL
			}
			if fileCfg.LLMModel != "" {
				cfg.LLMModel = fileCfg.LLMModel
			}
		}
	}

	// Step 2: env vars override file.
	if url := os.Getenv("AGENTSPAN_SERVER_URL"); url != "" {
		cfg.AgentspanURL = url
	}
	if apiKey := os.Getenv("AGENTSPAN_API_KEY"); apiKey != "" {
		cfg.APIKey = apiKey
	}
	if url := os.Getenv("CONDUCTOR_SERVER_URL"); url != "" {
		cfg.ConductorURL = url
	}

	// Step 3: CLI flags applied by caller via getConfig().
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

// FileServerURL returns the server URL stored in config.json (no env/default merging).
// Empty when no config file exists or it has no server_url.
func FileServerURL() string {
	data, err := os.ReadFile(configPath())
	if err != nil {
		return ""
	}
	var fileCfg Config
	if json.Unmarshal(data, &fileCfg) != nil {
		return ""
	}
	return fileCfg.ServerURL
}

// SaveDefaultServer persists serverURL as the default in config.json, preserving any
// other stored fields (e.g. a legacy api_key). Used so an explicitly passed --server
// (or the URL confirmed at login) becomes the default for subsequent commands.
func SaveDefaultServer(serverURL string) error {
	fileCfg := &Config{}
	if data, err := os.ReadFile(configPath()); err == nil {
		_ = json.Unmarshal(data, fileCfg)
	}
	fileCfg.ServerURL = serverURL
	return Save(fileCfg)
}
