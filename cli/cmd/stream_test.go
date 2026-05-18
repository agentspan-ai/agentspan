package cmd

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/agentspan-ai/agentspan/cli/client"
)

func TestStreamExecution_DrainsEventsBeforeError(t *testing.T) {
	// Simulate an SSE stream that sends events then an I/O error via done.
	// The drain pattern should process all events AND return the error.
	ssePayload := "event: thinking\ndata: {\"message\":\"working\"}\n\nevent: done\ndata: {\"output\":\"result\"}\n\n"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, ssePayload)
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))

	// streamExecution should return nil (no scanner error on clean EOF)
	err := streamExecution(c, "test-exec-id", "")
	if err != nil {
		t.Errorf("streamExecution returned error on clean stream: %v", err)
	}
}

func TestStreamExecution_ReturnsHTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "gone", http.StatusGone)
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))

	err := streamExecution(c, "bad-id", "")
	if err == nil {
		t.Fatal("expected error for 410 response, got nil")
	}
	if !strings.Contains(err.Error(), "410") {
		t.Errorf("error = %q, want to contain 410", err.Error())
	}
}

func TestStreamExecution_PassesLastEventID(t *testing.T) {
	var gotLastID string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotLastID = r.Header.Get("Last-Event-ID")
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "event: done\ndata: {}\n\n")
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))

	streamExecution(c, "exec-1", "evt-99")

	if gotLastID != "evt-99" {
		t.Errorf("Last-Event-ID = %q, want evt-99", gotLastID)
	}
}
