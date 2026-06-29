// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// TokenInfo is the auth token persisted at ~/.agentspan/token. It holds the Auth0
// JWT sent to orkes as the X-Authorization header, plus the refresh token and the
// issuer details needed to refresh it without re-login.
type TokenInfo struct {
	AccessToken  string `json:"access_token"`
	IDToken      string `json:"id_token,omitempty"`
	RefreshToken string `json:"refresh_token,omitempty"`
	ExpiresAt    int64  `json:"expires_at"` // unix seconds
	UseIDToken   bool   `json:"use_id_token"`
	Auth0Domain  string `json:"auth0_domain,omitempty"`
	ClientID     string `json:"client_id,omitempty"`

	// orkes internal-key (service-account) grant: re-mint via POST {ServerURL}/api/token.
	KeyID     string `json:"key_id,omitempty"`
	KeySecret string `json:"key_secret,omitempty"`
	ServerURL string `json:"server_url,omitempty"`
}

// TokenPath is the dedicated token file: ~/.agentspan/token.
func TokenPath() string {
	return filepath.Join(ConfigDir(), "token")
}

// Header returns the JWT to send as X-Authorization: the ID token when the
// deployment is configured for it, otherwise the access token (UI default).
func (t *TokenInfo) Header() string {
	if t.UseIDToken && t.IDToken != "" {
		return t.IDToken
	}
	return t.AccessToken
}

// Expired reports whether the token is at/near expiry (30s clock-skew margin).
func (t *TokenInfo) Expired() bool {
	return t.ExpiresAt > 0 && time.Now().Unix() >= t.ExpiresAt-30
}

// SaveToken writes the token file with 0600 perms.
func SaveToken(t *TokenInfo) error {
	if err := os.MkdirAll(ConfigDir(), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(t, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(TokenPath(), data, 0o600)
}

// LoadToken reads the token file. Returns (nil, nil) when no token is stored.
func LoadToken() (*TokenInfo, error) {
	data, err := os.ReadFile(TokenPath())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var t TokenInfo
	if err := json.Unmarshal(data, &t); err != nil {
		return nil, err
	}
	return &t, nil
}

// ClearToken removes the token file (logout). No-op if absent.
func ClearToken() error {
	err := os.Remove(TokenPath())
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
