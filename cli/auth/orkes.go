// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package auth

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// MintOrkesToken exchanges an orkes application access key (keyId/keySecret) for a JWT
// via POST {server}/api/token — orkes' internal/service-account auth path (no external IdP).
// Returns the JWT and its expiry (unix seconds, decoded from the token's exp claim).
func MintOrkesToken(serverBase, keyID, keySecret string) (token string, expiresAt int64, err error) {
	base := strings.TrimRight(serverBase, "/")
	body, _ := json.Marshal(map[string]string{"keyId": keyID, "keySecret": keySecret})
	resp, err := http.Post(base+"/api/token", "application/json", bytes.NewReader(body))
	if err != nil {
		return "", 0, fmt.Errorf("mint token: %w", err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return "", 0, fmt.Errorf("token request failed (HTTP %d): %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	var r struct {
		Token string `json:"token"`
	}
	if json.Unmarshal(b, &r) != nil || r.Token == "" {
		return "", 0, fmt.Errorf("no token in response: %s", strings.TrimSpace(string(b)))
	}
	return r.Token, TokenExp(r.Token), nil
}

// TokenExp decodes the `exp` (unix seconds) claim from a JWT without verifying the signature.
// Returns 0 when the token is opaque or has no exp.
func TokenExp(jwt string) int64 {
	parts := strings.Split(jwt, ".")
	if len(parts) < 2 {
		return 0
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		if payload, err = base64.URLEncoding.DecodeString(parts[1]); err != nil {
			return 0
		}
	}
	var claims struct {
		Exp int64 `json:"exp"`
	}
	if json.Unmarshal(payload, &claims) != nil {
		return 0
	}
	return claims.Exp
}
