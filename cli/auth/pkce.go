// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// PKCE implements the OAuth 2.0 Authorization Code flow with PKCE (RFC 7636) over a
// loopback redirect (RFC 8252 §7.3) — the browser-based login a native CLI uses when the
// Device Authorization grant is not enabled on the client. It reuses the SAME public
// clientId the orkes UI uses (authorization_code + PKCE is what the UI itself runs);
// the only requirement is that the loopback redirect URI is in the Auth0 application's
// Allowed Callback URLs (the local UI origin, e.g. http://localhost:5001, already is).

// GeneratePKCE returns a code_verifier and its S256 code_challenge.
func GeneratePKCE() (verifier, challenge string, err error) {
	buf := make([]byte, 32)
	if _, err = rand.Read(buf); err != nil {
		return "", "", fmt.Errorf("generate PKCE verifier: %w", err)
	}
	verifier = base64.RawURLEncoding.EncodeToString(buf)
	sum := sha256.Sum256([]byte(verifier))
	challenge = base64.RawURLEncoding.EncodeToString(sum[:])
	return verifier, challenge, nil
}

// RandomState returns a random opaque state value for CSRF protection.
func RandomState() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

// BuildAuthorizeURL constructs the Auth0 /authorize URL for the code+PKCE flow.
func BuildAuthorizeURL(domain, clientID, redirectURI, scope, state, challenge string) string {
	if scope == "" {
		scope = DefaultScope
	}
	q := url.Values{
		"client_id":             {clientID},
		"response_type":         {"code"},
		"redirect_uri":          {redirectURI},
		"scope":                 {scope},
		"state":                 {state},
		"code_challenge":        {challenge},
		"code_challenge_method": {"S256"},
	}
	return authURL(domain, "/authorize") + "?" + q.Encode()
}

// CodeCapture is a bound loopback listener awaiting the OAuth redirect.
type CodeCapture struct {
	srv   *http.Server
	resCh chan captureResult
}

type captureResult struct {
	code string
	err  error
}

// StartCodeCapture binds the loopback host:port of redirectURI immediately — failing fast
// if the port is busy (e.g. the UI dev server holds it) BEFORE any browser is opened — and
// starts serving the callback. Call Wait to block for the code.
func StartCodeCapture(redirectURI, expectedState string) (*CodeCapture, error) {
	u, err := url.Parse(redirectURI)
	if err != nil {
		return nil, fmt.Errorf("parse redirect uri: %w", err)
	}
	if u.Port() == "" {
		return nil, fmt.Errorf("redirect uri must include an explicit port (got %q)", redirectURI)
	}
	path := u.Path
	if path == "" {
		path = "/"
	}

	ln, err := net.Listen("tcp", u.Host)
	if err != nil {
		return nil, fmt.Errorf(
			"cannot bind %s — is something (the UI dev server?) running on that port? "+
				"Stop it during login or pass a different whitelisted --redirect-uri (%w)", u.Host, err)
	}

	resCh := make(chan captureResult, 1)
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Accept the callback on the redirect path (or root) only.
		if r.URL.Path != path && r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		q := r.URL.Query()
		if e := q.Get("error"); e != "" {
			http.Error(w, "Login failed: "+e, http.StatusBadRequest)
			resCh <- captureResult{err: fmt.Errorf("authorization failed: %s (%s)", e, q.Get("error_description"))}
			return
		}
		code := q.Get("code")
		if code == "" {
			// Not the OAuth callback (e.g. favicon) — ignore.
			http.NotFound(w, r)
			return
		}
		if q.Get("state") != expectedState {
			http.Error(w, "State mismatch", http.StatusBadRequest)
			resCh <- captureResult{err: fmt.Errorf("state mismatch in callback")}
			return
		}
		w.Header().Set("Content-Type", "text/html")
		_, _ = io.WriteString(w, "<html><body><h3>Login complete.</h3>You can close this tab and return to the terminal.</body></html>")
		resCh <- captureResult{code: code}
	})

	srv := &http.Server{Handler: mux}
	go func() { _ = srv.Serve(ln) }()
	return &CodeCapture{srv: srv, resCh: resCh}, nil
}

// Wait blocks until the redirect delivers a code, an OAuth error arrives, or timeout.
// The listener is shut down before returning.
func (c *CodeCapture) Wait(timeout time.Duration) (string, error) {
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = c.srv.Shutdown(ctx)
	}()
	select {
	case r := <-c.resCh:
		return r.code, r.err
	case <-time.After(timeout):
		return "", fmt.Errorf("timed out waiting for the browser login (after %s)", timeout)
	}
}

// ExchangeCode swaps an authorization code + PKCE verifier for tokens (public client).
func ExchangeCode(domain, clientID, code, verifier, redirectURI string) (*Token, error) {
	form := url.Values{
		"grant_type":    {"authorization_code"},
		"client_id":     {clientID},
		"code":          {code},
		"code_verifier": {verifier},
		"redirect_uri":  {redirectURI},
	}
	resp, err := http.PostForm(authURL(domain, "/oauth/token"), form)
	if err != nil {
		return nil, fmt.Errorf("exchange code: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("code exchange failed (HTTP %d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var tok Token
	if err := json.Unmarshal(body, &tok); err != nil {
		return nil, fmt.Errorf("parse token: %w", err)
	}
	return &tok, nil
}
