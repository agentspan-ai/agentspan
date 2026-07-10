// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"strings"
	"testing"

	"github.com/agentspan-ai/agentspan/cli/client"
)

// The server is the source of truth for provider configuration. Doctor renders
// the server's report; the client shell's env is only used to detect mismatches
// ("key set here but not on the server").
func TestBuildProviderReport(t *testing.T) {
	reachableFalse := false
	reachableTrue := true

	report := &client.ProviderStatusReport{
		Providers: []client.ProviderStatus{
			{Name: "openai", Configured: true},
			{Name: "anthropic", Configured: false},
			{Name: "mistral", Configured: false},
			{Name: "ollama", Configured: true, BaseURL: "http://gpu-box:11434", Reachable: &reachableFalse},
		},
	}
	env := map[string]string{"ANTHROPIC_API_KEY": "sk-ant-local-only"}
	getenv := func(k string) string { return env[k] }

	lines := buildProviderReport(report, getenv)

	byName := map[string]providerReportLine{}
	for _, l := range lines {
		for _, p := range []string{"OpenAI", "Anthropic", "Mistral", "Ollama"} {
			if strings.Contains(l.text, p) {
				byName[p] = l
			}
		}
	}

	// Configured on server → ok
	if byName["OpenAI"].level != "ok" {
		t.Fatalf("OpenAI should be ok (server-configured), got %+v", byName["OpenAI"])
	}
	// Not configured on server, but key in this shell → mismatch warning pointing at credentials set
	anthropic := byName["Anthropic"]
	if anthropic.level != "warn" || !strings.Contains(strings.Join(anthropic.extra, " "), "credentials set") {
		t.Fatalf("Anthropic should warn about shell/server mismatch with credentials-set hint, got %+v", anthropic)
	}
	// Not configured anywhere → informational skip
	if byName["Mistral"].level != "skip" {
		t.Fatalf("Mistral should be skip, got %+v", byName["Mistral"])
	}
	// Ollama unreachable FROM THE SERVER → fail, message names the URL and the server vantage
	ollama := byName["Ollama"]
	if ollama.level != "fail" || !strings.Contains(ollama.text+strings.Join(ollama.extra, " "), "gpu-box") {
		t.Fatalf("Ollama should fail with server-side unreachable detail, got %+v", ollama)
	}

	// Reachable ollama → ok
	report.Providers[3].Reachable = &reachableTrue
	lines = buildProviderReport(report, getenv)
	found := false
	for _, l := range lines {
		if strings.Contains(l.text, "Ollama") && l.level == "ok" {
			found = true
		}
	}
	if !found {
		t.Fatalf("reachable Ollama should be ok, got %+v", lines)
	}
}

func TestBuildProviderReport_ManagedByHost(t *testing.T) {
	report := &client.ProviderStatusReport{ManagedByHost: true}
	lines := buildProviderReport(report, func(string) string { return "" })
	if len(lines) != 1 || lines[0].level != "info" || !strings.Contains(lines[0].text, "host") {
		t.Fatalf("managed-by-host should produce a single info line, got %+v", lines)
	}
}
