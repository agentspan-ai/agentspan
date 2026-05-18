package cmd

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRespondCmd_RequiresApproveOrDeny(t *testing.T) {
	newTempHome(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	saveTestConfig(t, srv.URL)

	// Reset flags for each subtest
	tests := []struct {
		name    string
		approve bool
		deny    bool
		wantErr string
	}{
		{"neither flag", false, false, "specify either --approve or --deny"},
		{"both flags", true, true, "cannot specify both --approve and --deny"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			respondApprove = tt.approve
			respondDeny = tt.deny
			respondReason = ""
			respondMessage = ""

			cmd := respondCmd
			err := cmd.RunE(cmd, []string{"exec-123"})
			if err == nil {
				t.Fatalf("expected error, got nil")
			}
			if got := err.Error(); got != tt.wantErr {
				t.Errorf("error = %q, want %q", got, tt.wantErr)
			}
		})
	}
}

func TestRespondCmd_ApproveSendsCorrectPayload(t *testing.T) {
	newTempHome(t)

	var gotBody map[string]interface{}
	var gotPath, gotMethod string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		b, _ := io.ReadAll(r.Body)
		json.Unmarshal(b, &gotBody)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	saveTestConfig(t, srv.URL)

	respondApprove = true
	respondDeny = false
	respondReason = "looks good"
	respondMessage = ""

	cmd := respondCmd
	err := cmd.RunE(cmd, []string{"exec-456"})
	if err != nil {
		t.Fatalf("RunE: %v", err)
	}

	if gotMethod != http.MethodPost {
		t.Errorf("method = %q, want POST", gotMethod)
	}
	if gotPath != "/api/agent/exec-456/respond" {
		t.Errorf("path = %q, want /api/agent/exec-456/respond", gotPath)
	}
	if gotBody["approved"] != true {
		t.Errorf("approved = %v, want true", gotBody["approved"])
	}
	if gotBody["reason"] != "looks good" {
		t.Errorf("reason = %q, want 'looks good'", gotBody["reason"])
	}
}

func TestRespondCmd_DenySendsCorrectPayload(t *testing.T) {
	newTempHome(t)

	var gotBody map[string]interface{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		json.Unmarshal(b, &gotBody)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	saveTestConfig(t, srv.URL)

	respondApprove = false
	respondDeny = true
	respondReason = "unsafe"
	respondMessage = "do not proceed"

	cmd := respondCmd
	err := cmd.RunE(cmd, []string{"exec-789"})
	if err != nil {
		t.Fatalf("RunE: %v", err)
	}

	if gotBody["approved"] != false {
		t.Errorf("approved = %v, want false", gotBody["approved"])
	}
	if gotBody["reason"] != "unsafe" {
		t.Errorf("reason = %q, want 'unsafe'", gotBody["reason"])
	}
	if gotBody["message"] != "do not proceed" {
		t.Errorf("message = %q, want 'do not proceed'", gotBody["message"])
	}
}
