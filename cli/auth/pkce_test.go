package auth

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"
)

func TestGeneratePKCE(t *testing.T) {
	verifier, challenge, err := GeneratePKCE()
	if err != nil {
		t.Fatalf("GeneratePKCE: %v", err)
	}
	sum := sha256.Sum256([]byte(verifier))
	want := base64.RawURLEncoding.EncodeToString(sum[:])
	if challenge != want {
		t.Errorf("challenge mismatch: got %q want %q", challenge, want)
	}
	if len(verifier) < 43 { // 32 bytes base64url = 43 chars, RFC 7636 minimum
		t.Errorf("verifier too short: %d", len(verifier))
	}
}

func TestBuildAuthorizeURL(t *testing.T) {
	u, err := url.Parse(BuildAuthorizeURL("tenant.auth0.com", "cid", "http://localhost:5001", "", "st8", "ch4ll"))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if u.Host != "tenant.auth0.com" || u.Path != "/authorize" {
		t.Errorf("unexpected url: %s", u)
	}
	q := u.Query()
	for k, want := range map[string]string{
		"client_id":             "cid",
		"response_type":         "code",
		"redirect_uri":          "http://localhost:5001",
		"state":                 "st8",
		"code_challenge":        "ch4ll",
		"code_challenge_method": "S256",
		"scope":                 DefaultScope,
	} {
		if got := q.Get(k); got != want {
			t.Errorf("%s = %q, want %q", k, got, want)
		}
	}
}

// freePort grabs an ephemeral port and releases it for the capture server to rebind.
func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	_ = ln.Close()
	return port
}

func TestCodeCapture(t *testing.T) {
	port := freePort(t)
	redirect := fmt.Sprintf("http://127.0.0.1:%d", port)

	capture, err := StartCodeCapture(redirect, "state-1")
	if err != nil {
		t.Fatalf("StartCodeCapture: %v", err)
	}

	// Simulate the browser redirect.
	go func() {
		resp, gerr := http.Get(fmt.Sprintf("%s/?code=auth-code-42&state=state-1", redirect))
		if gerr == nil {
			resp.Body.Close()
		}
	}()

	code, err := capture.Wait(10 * time.Second)
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if code != "auth-code-42" {
		t.Errorf("code = %q", code)
	}
}

func TestCodeCaptureStateMismatch(t *testing.T) {
	port := freePort(t)
	redirect := fmt.Sprintf("http://127.0.0.1:%d", port)

	capture, err := StartCodeCapture(redirect, "expected")
	if err != nil {
		t.Fatalf("StartCodeCapture: %v", err)
	}

	go func() {
		resp, gerr := http.Get(fmt.Sprintf("%s/?code=c&state=WRONG", redirect))
		if gerr == nil {
			resp.Body.Close()
		}
	}()

	if _, err := capture.Wait(10 * time.Second); err == nil {
		t.Fatal("expected state-mismatch error")
	}
}

func TestStartCodeCapturePortBusy(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	busy := fmt.Sprintf("http://127.0.0.1:%d", ln.Addr().(*net.TCPAddr).Port)

	// Bind must fail immediately — BEFORE any browser would be opened.
	if _, err := StartCodeCapture(busy, "s"); err == nil {
		t.Fatal("expected bind error on busy port")
	}
}

func TestExchangeCode(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/oauth/token" {
			http.NotFound(w, r)
			return
		}
		if err := r.ParseForm(); err != nil {
			http.Error(w, "bad form", http.StatusBadRequest)
			return
		}
		if r.FormValue("grant_type") != "authorization_code" ||
			r.FormValue("code") != "the-code" ||
			r.FormValue("code_verifier") != "the-verifier" ||
			r.FormValue("redirect_uri") != "http://localhost:5001" {
			http.Error(w, "bad exchange params", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": "at", "id_token": "idt", "refresh_token": "rt", "expires_in": 3600,
		})
	}))
	defer srv.Close()

	tok, err := ExchangeCode(srv.URL, "cid", "the-code", "the-verifier", "http://localhost:5001")
	if err != nil {
		t.Fatalf("ExchangeCode: %v", err)
	}
	if tok.AccessToken != "at" || tok.RefreshToken != "rt" {
		t.Errorf("unexpected token: %+v", tok)
	}
}
