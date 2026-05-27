// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRunAgent_ByNameSkillUsesFrameworkPayload(t *testing.T) {
	var gotStart map[string]interface{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/cli-skill":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"model":         "openai/gpt-4o-mini",
				"skillMd":       "---\nname: cli-skill\n---\n# CLI Skill\n",
				"agentFiles":    map[string]string{},
				"scripts":       map[string]interface{}{},
				"resourceFiles": []string{},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/api/agent/start":
			json.NewDecoder(r.Body).Decode(&gotStart)
			json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-skill",
				"agentName":   "cli-skill",
			})
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	oldName := runAgentName
	oldConfig := runConfigFile
	oldNoStream := runNoStream
	oldSession := runSessionID
	oldServerURL := serverURL
	defer func() {
		runAgentName = oldName
		runConfigFile = oldConfig
		runNoStream = oldNoStream
		runSessionID = oldSession
		serverURL = oldServerURL
	}()

	runAgentName = "cli-skill"
	runConfigFile = ""
	runNoStream = true
	runSessionID = "session-1"
	serverURL = srv.URL

	if err := runAgent(nil, []string{"hello skill"}); err != nil {
		t.Fatalf("runAgent: %v", err)
	}

	if gotStart["framework"] != "skill" {
		t.Fatalf("framework = %v, want skill; body=%v", gotStart["framework"], gotStart)
	}
	if gotStart["agentConfig"] != nil {
		t.Fatalf("agentConfig should not be sent for stored skill rawConfig: %v", gotStart)
	}
	if gotStart["rawConfig"] == nil {
		t.Fatalf("missing rawConfig in start body: %v", gotStart)
	}
	if gotStart["prompt"] != "hello skill" {
		t.Fatalf("prompt = %v, want hello skill", gotStart["prompt"])
	}
	if gotStart["sessionId"] != "session-1" {
		t.Fatalf("sessionId = %v, want session-1", gotStart["sessionId"])
	}
}

func TestDetectStoredFramework(t *testing.T) {
	tests := []struct {
		name string
		def  map[string]interface{}
		want string
	}{
		{
			name: "explicit framework",
			def:  map[string]interface{}{"_framework": "skill"},
			want: "skill",
		},
		{
			name: "skill raw config",
			def:  map[string]interface{}{"skillMd": "---\nname: s\n---\n"},
			want: "skill",
		},
		{
			name: "native config",
			def:  map[string]interface{}{"name": "native", "instructions": "hi"},
			want: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := detectStoredFramework(tt.def); got != tt.want {
				t.Fatalf("%s: got %q, want %q for %s", tt.name, got, tt.want, fmt.Sprint(tt.def))
			}
		})
	}
}

func TestRunAgent_ByNameNativeStillUsesAgentConfig(t *testing.T) {
	var gotStart map[string]interface{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/native-agent":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"name":         "native-agent",
				"model":        "openai/gpt-4o-mini",
				"instructions": "You are helpful.",
			})
		case r.Method == http.MethodPost && r.URL.Path == "/api/agent/start":
			json.NewDecoder(r.Body).Decode(&gotStart)
			json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-native",
				"agentName":   "native-agent",
			})
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	oldName := runAgentName
	oldConfig := runConfigFile
	oldNoStream := runNoStream
	oldServerURL := serverURL
	defer func() {
		runAgentName = oldName
		runConfigFile = oldConfig
		runNoStream = oldNoStream
		serverURL = oldServerURL
	}()

	runAgentName = "native-agent"
	runConfigFile = ""
	runNoStream = true
	serverURL = srv.URL

	if err := runAgent(nil, []string{"hello native"}); err != nil {
		t.Fatalf("runAgent: %v", err)
	}

	if gotStart["framework"] != nil || gotStart["rawConfig"] != nil {
		t.Fatalf("native agent should not use framework payload: %v", gotStart)
	}
	if gotStart["agentConfig"] == nil {
		t.Fatalf("native agent missing agentConfig: %v", gotStart)
	}
	if !strings.Contains(fmt.Sprint(gotStart["agentConfig"]), "native-agent") {
		t.Fatalf("agentConfig does not contain native-agent: %v", gotStart)
	}
}
