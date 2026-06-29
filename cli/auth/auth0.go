// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

// Package auth implements the Auth0 OAuth Device Authorization Grant (RFC 8628)
// for browser-based CLI login. This mirrors how the orkes-conductor UI authenticates:
// it obtains an Auth0-issued JWT and sends it to the backend as the X-Authorization
// header — there is no orkes-side token exchange. The device flow delegates the actual
// login to Auth0's hosted page, so it supports whatever the tenant allows
// (username/password, Google, SSO, MFA, ...).
package auth

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

// DefaultScope requests an OIDC token plus a refresh token. No audience is requested,
// matching the UI (which relies on the Auth0 tenant's default audience / ID token).
const DefaultScope = "openid profile email offline_access"

// DeviceCode is the response from POST /oauth/device/code.
type DeviceCode struct {
	DeviceCode              string `json:"device_code"`
	UserCode                string `json:"user_code"`
	VerificationURI         string `json:"verification_uri"`
	VerificationURIComplete string `json:"verification_uri_complete"`
	ExpiresIn               int    `json:"expires_in"`
	Interval                int    `json:"interval"`
}

// Token is the response from POST /oauth/token.
type Token struct {
	AccessToken  string `json:"access_token"`
	IDToken      string `json:"id_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
	TokenType    string `json:"token_type"`
	Scope        string `json:"scope"`
}

// Auth0Config is the subset of the server's window.authConfig the CLI needs.
type Auth0Config struct {
	Domain     string
	ClientID   string
	UseIDToken bool
}

// RequestDeviceCode starts the device authorization flow.
func RequestDeviceCode(domain, clientID, scope string) (*DeviceCode, error) {
	if scope == "" {
		scope = DefaultScope
	}
	form := url.Values{"client_id": {clientID}, "scope": {scope}}
	resp, err := http.PostForm(authURL(domain, "/oauth/device/code"), form)
	if err != nil {
		return nil, fmt.Errorf("request device code: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("device code request failed (HTTP %d): %s", resp.StatusCode, string(body))
	}
	var dc DeviceCode
	if err := json.Unmarshal(body, &dc); err != nil {
		return nil, fmt.Errorf("parse device code: %w", err)
	}
	if dc.Interval <= 0 {
		dc.Interval = 5
	}
	return &dc, nil
}

// PollForToken polls the token endpoint until the user completes login in the browser,
// the code expires, or login is denied. Honors authorization_pending and slow_down.
func PollForToken(domain, clientID string, dc *DeviceCode) (*Token, error) {
	deadline := time.Now().Add(time.Duration(dc.ExpiresIn) * time.Second)
	interval := time.Duration(dc.Interval) * time.Second
	for {
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("device code expired before login completed")
		}
		time.Sleep(interval)

		form := url.Values{
			"grant_type":  {"urn:ietf:params:oauth:grant-type:device_code"},
			"device_code": {dc.DeviceCode},
			"client_id":   {clientID},
		}
		resp, err := http.PostForm(authURL(domain, "/oauth/token"), form)
		if err != nil {
			return nil, fmt.Errorf("poll token: %w", err)
		}
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			var tok Token
			if err := json.Unmarshal(body, &tok); err != nil {
				return nil, fmt.Errorf("parse token: %w", err)
			}
			return &tok, nil
		}

		var e struct {
			Error string `json:"error"`
		}
		_ = json.Unmarshal(body, &e)
		switch e.Error {
		case "authorization_pending":
			// keep waiting
		case "slow_down":
			interval += 5 * time.Second
		case "expired_token":
			return nil, fmt.Errorf("device code expired before login completed")
		case "access_denied":
			return nil, fmt.Errorf("login was denied")
		default:
			return nil, fmt.Errorf("token poll failed (HTTP %d): %s", resp.StatusCode, string(body))
		}
	}
}

// Refresh exchanges a refresh token for a fresh access/ID token.
func Refresh(domain, clientID, refreshToken string) (*Token, error) {
	form := url.Values{
		"grant_type":    {"refresh_token"},
		"client_id":     {clientID},
		"refresh_token": {refreshToken},
	}
	resp, err := http.PostForm(authURL(domain, "/oauth/token"), form)
	if err != nil {
		return nil, fmt.Errorf("refresh token: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("refresh failed (HTTP %d): %s", resp.StatusCode, string(body))
	}
	var tok Token
	if err := json.Unmarshal(body, &tok); err != nil {
		return nil, fmt.Errorf("parse refreshed token: %w", err)
	}
	return &tok, nil
}

// DiscoverConfig fetches the server's /context.js and extracts the Auth0 config — the
// same runtime config the UI consumes, with the UI's exact resolution order
// (auth0-config.ts): authConfig.domain || auth0Identifiers.domain, same for clientId.
// Handles the real orkes serialization (quoted keys, e.g. {"clientId" : "..."}) as well
// as bare-key JS object literals.
func DiscoverConfig(serverBaseURL string) (*Auth0Config, error) {
	base := strings.TrimRight(serverBaseURL, "/")
	resp, err := http.Get(base + "/context.js")
	if err != nil {
		return nil, fmt.Errorf("fetch /context.js: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("/context.js returned HTTP %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	js := string(body)

	authBlock := sliceBlock(js, "window.authConfig")
	idsBlock := sliceBlock(js, "window.auth0Identifiers")

	domain := extract(authBlock, "domain")
	if domain == "" {
		domain = extract(idsBlock, "domain")
	}
	clientID := extract(authBlock, "clientId")
	if clientID == "" {
		clientID = extract(idsBlock, "clientId")
	}

	cfg := &Auth0Config{
		Domain:     domain,
		ClientID:   clientID,
		UseIDToken: useIDTokenTrueRe.MatchString(authBlock),
	}
	if cfg.Domain == "" || cfg.ClientID == "" {
		return nil, fmt.Errorf("server has no Auth0 config in /context.js (is auth enabled?)")
	}
	return cfg, nil
}

var useIDTokenTrueRe = regexp.MustCompile(`["']?useIdToken["']?\s*:\s*true`)

// sliceBlock returns the {...} object literal assigned at `marker` (e.g. "window.authConfig"),
// or "" when absent. The blocks served by orkes/the UI are flat objects, so the first `}`
// after the marker closes the block.
func sliceBlock(js, marker string) string {
	start := strings.Index(js, marker)
	if start < 0 {
		return ""
	}
	rest := js[start:]
	end := strings.Index(rest, "}")
	if end < 0 {
		return rest
	}
	return rest[:end+1]
}

// extract pulls a string value for `key` from a JS/JSON object literal, tolerating both
// quoted and bare keys and arbitrary spacing around the colon.
func extract(js, key string) string {
	m := regexp.MustCompile(`["']?` + key + `["']?\s*:\s*["']([^"']+)["']`).FindStringSubmatch(js)
	if len(m) == 2 {
		return m[1]
	}
	return ""
}

func authURL(domain, path string) string {
	domain = strings.TrimRight(domain, "/")
	if !strings.HasPrefix(domain, "http") {
		domain = "https://" + domain
	}
	return domain + path
}
