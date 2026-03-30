package client

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/agentspan/agentspan/cli/config"
)

// newTestServer creates an httptest server and a Client pointing at it.
func newTestServer(t *testing.T, handler http.Handler) (*httptest.Server, *Client) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	c := New(&config.Config{ServerURL: srv.URL})
	return srv, c
}

// ─── HealthCheck ─────────────────────────────────────────────────────────────

func TestHealthCheck_UsesHealthEndpoint(t *testing.T) {
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	}))

	if err := c.HealthCheck(); err != nil {
		t.Fatalf("HealthCheck: %v", err)
	}
	if gotPath != "/health" {
		t.Errorf("path = %q, want /health", gotPath)
	}
}

// ─── Start ───────────────────────────────────────────────────────────────────

func TestStart_ReturnsExecutionIDAndAgentName(t *testing.T) {
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/agent/start" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{
			"executionId": "exec-123",
			"agentName":   "my-agent",
		})
	}))

	resp, err := c.Start(&StartRequest{Prompt: "hello"})
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	if resp.ExecutionID != "exec-123" {
		t.Errorf("ExecutionID = %q, want exec-123", resp.ExecutionID)
	}
	if resp.AgentName != "my-agent" {
		t.Errorf("AgentName = %q, want my-agent", resp.AgentName)
	}
}

// ─── PathEscape ──────────────────────────────────────────────────────────────

func TestStatus_PathEscapesExecutionID(t *testing.T) {
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "COMPLETED"})
	}))

	_, err := c.Status("id/with/slashes")
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !strings.Contains(gotPath, "id%2Fwith%2Fslashes") {
		t.Errorf("path = %q, want escaped slashes", gotPath)
	}
}

func TestRespond_PathEscapesExecutionID(t *testing.T) {
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.WriteHeader(http.StatusOK)
	}))

	err := c.Respond("id/with/slashes", true, "", "")
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !strings.Contains(gotPath, "id%2Fwith%2Fslashes") {
		t.Errorf("path = %q, want escaped slashes", gotPath)
	}
}

// ─── SSE Streaming ───────────────────────────────────────────────────────────

func TestStream_ParsesSingleLineEvents(t *testing.T) {
	ssePayload := "event: thinking\ndata: {\"message\":\"hmm\"}\n\nevent: done\ndata: {\"output\":\"hello\"}\n\n"

	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, ssePayload)
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("test-id", "", events, done)

	var got []SSEEvent
	timeout := time.After(5 * time.Second)
	for {
		select {
		case evt, ok := <-events:
			if !ok {
				goto check
			}
			got = append(got, evt)
		case <-timeout:
			t.Fatal("timed out waiting for events")
		}
	}
check:
	if err := <-done; err != nil {
		t.Fatalf("stream error: %v", err)
	}

	if len(got) != 2 {
		t.Fatalf("got %d events, want 2", len(got))
	}
	if got[0].Event != "thinking" || got[0].Data != `{"message":"hmm"}` {
		t.Errorf("event[0] = %+v", got[0])
	}
	if got[1].Event != "done" || got[1].Data != `{"output":"hello"}` {
		t.Errorf("event[1] = %+v", got[1])
	}
}

func TestStream_MultilineDataJoinedWithNewline(t *testing.T) {
	ssePayload := "event: message\ndata: line1\ndata: line2\ndata: line3\n\n"

	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, ssePayload)
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("test-id", "", events, done)

	var got SSEEvent
	select {
	case evt := <-events:
		got = evt
	case <-time.After(5 * time.Second):
		t.Fatal("timed out")
	}

	if err := <-done; err != nil {
		t.Fatalf("stream error: %v", err)
	}

	if got.Data != "line1\nline2\nline3" {
		t.Errorf("multiline data = %q, want \"line1\\nline2\\nline3\"", got.Data)
	}
}

func TestStream_SingleLeadingSpaceStripped(t *testing.T) {
	// Per SSE spec: strip exactly one leading space after the colon
	ssePayload := "event:  two-spaces\ndata:  {\"x\":1}\n\n"

	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, ssePayload)
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("test-id", "", events, done)

	var got SSEEvent
	select {
	case evt := <-events:
		got = evt
	case <-time.After(5 * time.Second):
		t.Fatal("timed out")
	}

	<-done

	// "event:  two-spaces" -> strip prefix "event:" -> " two-spaces" -> strip one space -> "two-spaces"
	// Wait no: " two-spaces" -> strip one leading space -> "two-spaces"
	// Actually: "event:  two-spaces" has TWO spaces after colon. After stripping prefix we get " two-spaces".
	// TrimPrefix(" ") removes one space -> "two-spaces". But the original has TWO spaces.
	// Let me recalculate: TrimPrefix(line, "event:") = " two-spaces", TrimPrefix(v, " ") = "two-spaces"
	// Hmm, the original line is "event:  two-spaces" (two spaces after colon).
	// TrimPrefix("  two-spaces", " ") = " two-spaces" (one space remains). That's correct per spec.
	if got.Event != " two-spaces" {
		t.Errorf("event = %q, want %q (one leading space preserved)", got.Event, " two-spaces")
	}
	if got.Data != " {\"x\":1}" {
		t.Errorf("data = %q, want %q (one leading space preserved)", got.Data, " {\"x\":1}")
	}
}

func TestStream_SendsLastEventIDHeader(t *testing.T) {
	var gotLastID string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotLastID = r.Header.Get("Last-Event-ID")
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "event: done\ndata: {}\n\n")
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("test-id", "evt-42", events, done)

	// drain
	for range events {
	}
	<-done

	if gotLastID != "evt-42" {
		t.Errorf("Last-Event-ID = %q, want evt-42", gotLastID)
	}
}

func TestStream_SkipsCommentLines(t *testing.T) {
	ssePayload := ": heartbeat\nevent: done\ndata: {\"ok\":true}\n\n"

	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, ssePayload)
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("test-id", "", events, done)

	var got []SSEEvent
	for evt := range events {
		got = append(got, evt)
	}
	<-done

	if len(got) != 1 {
		t.Fatalf("got %d events, want 1 (comment should be skipped)", len(got))
	}
	if got[0].Event != "done" {
		t.Errorf("event = %q, want done", got[0].Event)
	}
}

func TestStream_HTTP4xxReturnsError(t *testing.T) {
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("bad-id", "", events, done)

	// drain events
	for range events {
	}
	err := <-done

	if err == nil {
		t.Fatal("expected error for 404, got nil")
	}
	if !strings.Contains(err.Error(), "404") {
		t.Errorf("error = %q, want to contain 404", err.Error())
	}
}

func TestStream_PathEscapesExecutionID(t *testing.T) {
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "event: done\ndata: {}\n\n")
	}))

	events := make(chan SSEEvent, 10)
	done := make(chan error, 1)
	c.Stream("id/slash", "", events, done)
	for range events {
	}
	<-done

	if !strings.Contains(gotPath, "id%2Fslash") {
		t.Errorf("path = %q, want escaped slash", gotPath)
	}
}

// ─── Auth Headers ────────────────────────────────────────────────────────────

func TestDoRequest_SendsBearerToken(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	c := New(&config.Config{ServerURL: srv.URL, APIKey: "my-jwt"})
	resp, err := c.doRequest("GET", "/health", nil)
	if err != nil {
		t.Fatalf("doRequest: %v", err)
	}
	resp.Body.Close()

	if gotAuth != "Bearer my-jwt" {
		t.Errorf("Authorization = %q, want \"Bearer my-jwt\"", gotAuth)
	}
}

func TestDoRequest_SendsAuthKeyAndSecret(t *testing.T) {
	var gotKey, gotSecret string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotKey = r.Header.Get("X-Auth-Key")
		gotSecret = r.Header.Get("X-Auth-Secret")
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	c := New(&config.Config{ServerURL: srv.URL, AuthKey: "k", AuthSecret: "s"})
	resp, err := c.doRequest("GET", "/health", nil)
	if err != nil {
		t.Fatalf("doRequest: %v", err)
	}
	resp.Body.Close()

	if gotKey != "k" || gotSecret != "s" {
		t.Errorf("auth headers = (%q, %q), want (k, s)", gotKey, gotSecret)
	}
}

func TestDoRequest_BearerTakesPrecedence(t *testing.T) {
	var gotAuth, gotKey string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotKey = r.Header.Get("X-Auth-Key")
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	c := New(&config.Config{ServerURL: srv.URL, APIKey: "jwt", AuthKey: "k"})
	resp, err := c.doRequest("GET", "/health", nil)
	if err != nil {
		t.Fatalf("doRequest: %v", err)
	}
	resp.Body.Close()

	if gotAuth != "Bearer jwt" {
		t.Errorf("Authorization = %q, want Bearer jwt", gotAuth)
	}
	if gotKey != "" {
		t.Errorf("X-Auth-Key = %q, want empty (Bearer takes precedence)", gotKey)
	}
}

// ─── Credentials CRUD ────────────────────────────────────────────────────────

func TestSetCredential_PostsCorrectBody(t *testing.T) {
	var gotBody map[string]string
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		b, _ := io.ReadAll(r.Body)
		json.Unmarshal(b, &gotBody)
		w.WriteHeader(http.StatusOK)
	}))

	if err := c.SetCredential("TOKEN", "secret-val"); err != nil {
		t.Fatalf("SetCredential: %v", err)
	}
	if gotPath != "/api/credentials" {
		t.Errorf("path = %q, want /api/credentials", gotPath)
	}
	if gotBody["name"] != "TOKEN" || gotBody["value"] != "secret-val" {
		t.Errorf("body = %v, want name=TOKEN value=secret-val", gotBody)
	}
}

func TestDeleteCredential_EscapesName(t *testing.T) {
	var gotPath string
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.WriteHeader(http.StatusOK)
	}))

	if err := c.DeleteCredential("my/key"); err != nil {
		t.Fatalf("DeleteCredential: %v", err)
	}
	if !strings.Contains(gotPath, "my%2Fkey") {
		t.Errorf("path = %q, want escaped name", gotPath)
	}
}

// ─── sseFieldValue ───────────────────────────────────────────────────────────

func TestSSEFieldValue(t *testing.T) {
	tests := []struct {
		name   string
		line   string
		prefix string
		want   string
	}{
		{"single space", "data: hello", "data:", "hello"},
		{"no space", "data:hello", "data:", "hello"},
		{"two spaces preserves one", "data:  hello", "data:", " hello"},
		{"tabs not stripped", "data:\thello", "data:", "\thello"},
		{"empty after colon", "data:", "data:", ""},
		{"trailing space preserved", "data: hello ", "data:", "hello "},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := sseFieldValue(tt.line, tt.prefix)
			if got != tt.want {
				t.Errorf("sseFieldValue(%q, %q) = %q, want %q", tt.line, tt.prefix, got, tt.want)
			}
		})
	}
}

// ─── HTTP error handling ─────────────────────────────────────────────────────

func TestDoRequest_Returns4xxError(t *testing.T) {
	_, c := newTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad request", http.StatusBadRequest)
	}))

	_, err := c.doRequest("GET", "/api/agent", nil)
	if err == nil {
		t.Fatal("expected error for 400")
	}
	if !strings.Contains(err.Error(), "400") {
		t.Errorf("error = %q, want to contain 400", err.Error())
	}
}
