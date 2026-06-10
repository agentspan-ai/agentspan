package auth

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMintOrkesToken(t *testing.T) {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS512","typ":"JWT"}`))
	payload := base64.RawURLEncoding.EncodeToString([]byte(`{"exp":4102444800,"orkes_conductor_token":true}`))
	jwt := header + "." + payload + ".sig"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/token" || r.Method != http.MethodPost {
			http.NotFound(w, r)
			return
		}
		var body map[string]string
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["keyId"] != "kid" || body["keySecret"] != "ksecret" {
			http.Error(w, "bad creds", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"token": jwt})
	}))
	defer srv.Close()

	token, exp, err := MintOrkesToken(srv.URL, "kid", "ksecret")
	if err != nil {
		t.Fatalf("MintOrkesToken: %v", err)
	}
	if token != jwt {
		t.Errorf("token mismatch")
	}
	if exp != 4102444800 {
		t.Errorf("exp = %d, want 4102444800", exp)
	}
}

func TestMintOrkesTokenBadCreds(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}))
	defer srv.Close()
	if _, _, err := MintOrkesToken(srv.URL, "x", "y"); err == nil {
		t.Fatal("expected error on 401")
	}
}

func TestTokenExp(t *testing.T) {
	payload := base64.RawURLEncoding.EncodeToString([]byte(`{"exp":1700000000}`))
	if got := TokenExp("h." + payload + ".s"); got != 1700000000 {
		t.Errorf("TokenExp = %d, want 1700000000", got)
	}
	if got := TokenExp("opaque-token"); got != 0 {
		t.Errorf("TokenExp(opaque) = %d, want 0", got)
	}
}
