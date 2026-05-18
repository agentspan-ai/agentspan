// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
)

// ── Fixtures ────────────────────────────────────────────────────────────────

// createSimpleSkill creates a minimal instruction-only skill directory.
func createSimpleSkill(t *testing.T, dir string) {
	t.Helper()
	skillMd := `---
name: simple-skill
description: A simple skill for testing.
---

# Simple Skill

You are a helpful assistant. Follow these instructions carefully.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)
}

// createDGSkill creates a skill directory with sub-agents and an asset.
func createDGSkill(t *testing.T, dir string) {
	t.Helper()
	skillMd := `---
name: dg-skill
description: Adversarial code review with two sub-agents.
metadata:
  author: test
---

# DG Review

Dispatch the gilfoyle agent to review code, then dispatch the dinesh agent to respond.
Repeat until convergence. Read comic-template.html to generate output.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)
	os.WriteFile(filepath.Join(dir, "gilfoyle-agent.md"), []byte("# You Are Gilfoyle\nReview code with withering precision."), 0o644)
	os.WriteFile(filepath.Join(dir, "dinesh-agent.md"), []byte("# You Are Dinesh\nDefend the code."), 0o644)
	os.WriteFile(filepath.Join(dir, "comic-template.html"), []byte("<html><body>{{PANELS}}</body></html>"), 0o644)
}

// createScriptSkill creates a skill directory with scripts.
func createScriptSkill(t *testing.T, dir string) {
	t.Helper()
	skillMd := `---
name: script-skill
description: A skill with scripts.
---

# Script Skill

Run the hello script to greet the user.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)

	scriptsDir := filepath.Join(dir, "scripts")
	os.MkdirAll(scriptsDir, 0o755)
	os.WriteFile(filepath.Join(scriptsDir, "hello.py"), []byte("#!/usr/bin/env python3\nprint('hello')"), 0o755)
	os.WriteFile(filepath.Join(scriptsDir, "build.sh"), []byte("#!/bin/bash\necho build"), 0o755)
	os.WriteFile(filepath.Join(scriptsDir, "lint.js"), []byte("console.log('lint')"), 0o644)
	os.WriteFile(filepath.Join(scriptsDir, "check"), []byte("#!/bin/bash\necho check"), 0o755)
}

// createResourceSkill creates a skill with references, examples, and assets.
func createResourceSkill(t *testing.T, dir string) {
	t.Helper()
	skillMd := `---
name: resource-skill
description: A skill with resource files.
---

# Resource Skill

Read reference files as needed.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)

	os.MkdirAll(filepath.Join(dir, "references"), 0o755)
	os.WriteFile(filepath.Join(dir, "references", "api.md"), []byte("# API Reference"), 0o644)
	os.WriteFile(filepath.Join(dir, "references", "guide.md"), []byte("# Guide"), 0o644)

	os.MkdirAll(filepath.Join(dir, "examples"), 0o755)
	os.WriteFile(filepath.Join(dir, "examples", "usage.md"), []byte("# Usage"), 0o644)

	os.MkdirAll(filepath.Join(dir, "assets"), 0o755)
	os.WriteFile(filepath.Join(dir, "assets", "template.html"), []byte("<html></html>"), 0o644)

	os.WriteFile(filepath.Join(dir, "extra.txt"), []byte("extra"), 0o644)
}

// ── Frontmatter Parsing ─────────────────────────────────────────────────────

func TestParseFrontmatter_ExtractsFields(t *testing.T) {
	content := "---\nname: my-skill\ndescription: A test skill.\n---\n# Body"
	fm, err := parseFrontmatter(content)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if fm["name"] != "my-skill" {
		t.Errorf("name = %q, want my-skill", fm["name"])
	}
	if fm["description"] != "A test skill." {
		t.Errorf("description = %q, want 'A test skill.'", fm["description"])
	}
}

func TestParseFrontmatter_ExtractsMetadata(t *testing.T) {
	content := "---\nname: x\ndescription: y\nmetadata:\n  author: test\n---\n"
	fm, err := parseFrontmatter(content)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	meta, ok := fm["metadata"].(map[string]interface{})
	if !ok {
		t.Fatalf("metadata is not a map: %T", fm["metadata"])
	}
	if meta["author"] != "test" {
		t.Errorf("metadata.author = %q, want test", meta["author"])
	}
}

func TestParseFrontmatter_MissingOpeningDelimiter(t *testing.T) {
	content := "name: x\n---\n# Body"
	_, err := parseFrontmatter(content)
	if err == nil {
		t.Fatal("expected error for missing opening ---")
	}
}

func TestParseFrontmatter_MissingClosingDelimiter(t *testing.T) {
	content := "---\nname: x\n# Body without closing"
	_, err := parseFrontmatter(content)
	if err == nil {
		t.Fatal("expected error for missing closing ---")
	}
}

func TestExtractBody(t *testing.T) {
	content := "---\nname: x\ndescription: y\n---\n# Body\nHello"
	body := extractBody(content)
	if body != "# Body\nHello" {
		t.Errorf("body = %q, want '# Body\\nHello'", body)
	}
}

func TestExtractBody_NoFrontmatter(t *testing.T) {
	content := "# Just a body"
	body := extractBody(content)
	if body != "# Just a body" {
		t.Errorf("body = %q, want '# Just a body'", body)
	}
}

// ── Agent File Discovery ────────────────────────────────────────────────────

func TestDiscoverAgentFiles_FindsSubAgents(t *testing.T) {
	dir := t.TempDir()
	createDGSkill(t, dir)

	agents, err := discoverAgentFiles(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 2 {
		t.Fatalf("got %d agent files, want 2", len(agents))
	}
	if _, ok := agents["gilfoyle"]; !ok {
		t.Error("missing gilfoyle agent")
	}
	if _, ok := agents["dinesh"]; !ok {
		t.Error("missing dinesh agent")
	}
	if agents["gilfoyle"] == "" {
		t.Error("gilfoyle content is empty")
	}
}

func TestDiscoverAgentFiles_EmptyForSimpleSkill(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	agents, err := discoverAgentFiles(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 0 {
		t.Errorf("got %d agent files, want 0", len(agents))
	}
}

// ── Script Discovery ────────────────────────────────────────────────────────

func TestDiscoverScripts_FindsScripts(t *testing.T) {
	dir := t.TempDir()
	createScriptSkill(t, dir)

	scripts, err := discoverScripts(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(scripts) != 4 {
		t.Fatalf("got %d scripts, want 4: %v", len(scripts), scripts)
	}

	// Check hello.py
	hello, ok := scripts["hello"]
	if !ok {
		t.Fatal("missing hello script")
	}
	if hello.Filename != "hello.py" {
		t.Errorf("hello.Filename = %q, want hello.py", hello.Filename)
	}
	if hello.Language != "python" {
		t.Errorf("hello.Language = %q, want python", hello.Language)
	}

	// Check build.sh
	build, ok := scripts["build"]
	if !ok {
		t.Fatal("missing build script")
	}
	if build.Language != "bash" {
		t.Errorf("build.Language = %q, want bash", build.Language)
	}

	// Check lint.js
	lint, ok := scripts["lint"]
	if !ok {
		t.Fatal("missing lint script")
	}
	if lint.Language != "node" {
		t.Errorf("lint.Language = %q, want node", lint.Language)
	}

	// Check extensionless script
	check, ok := scripts["check"]
	if !ok {
		t.Fatal("missing check script")
	}
	if check.Language != "bash" {
		t.Errorf("check.Language = %q, want bash (default)", check.Language)
	}
}

func TestDiscoverScripts_EmptyWhenNoDir(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	scripts, err := discoverScripts(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(scripts) != 0 {
		t.Errorf("got %d scripts, want 0", len(scripts))
	}
}

// ── Language Detection ──────────────────────────────────────────────────────

func TestDetectScriptLanguage(t *testing.T) {
	tests := []struct {
		filename string
		want     string
	}{
		{"hello.py", "python"},
		{"build.sh", "bash"},
		{"lint.js", "node"},
		{"index.mjs", "node"},
		{"compile.ts", "node"},
		{"process.rb", "ruby"},
		{"main.go", "go"},
		{"run", "bash"},
		{"Makefile", "bash"},
	}

	for _, tt := range tests {
		t.Run(tt.filename, func(t *testing.T) {
			got := detectScriptLanguage(tt.filename)
			if got != tt.want {
				t.Errorf("detectScriptLanguage(%q) = %q, want %q", tt.filename, got, tt.want)
			}
		})
	}
}

// ── Resource File Collection ────────────────────────────────────────────────

func TestCollectResourceFiles(t *testing.T) {
	dir := t.TempDir()
	createResourceSkill(t, dir)

	files, err := collectResourceFiles(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	sort.Strings(files)
	expected := []string{
		filepath.Join("assets", "template.html"),
		filepath.Join("examples", "usage.md"),
		"extra.txt",
		filepath.Join("references", "api.md"),
		filepath.Join("references", "guide.md"),
	}
	sort.Strings(expected)

	if len(files) != len(expected) {
		t.Fatalf("got %d files, want %d: %v", len(files), len(expected), files)
	}

	for i, f := range files {
		if f != expected[i] {
			t.Errorf("files[%d] = %q, want %q", i, f, expected[i])
		}
	}
}

func TestCollectResourceFiles_ExcludesSkillAndAgentMd(t *testing.T) {
	dir := t.TempDir()
	createDGSkill(t, dir)

	files, err := collectResourceFiles(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	for _, f := range files {
		if f == "SKILL.md" {
			t.Error("resource files should not include SKILL.md")
		}
		if f == "gilfoyle-agent.md" || f == "dinesh-agent.md" {
			t.Errorf("resource files should not include agent file: %s", f)
		}
	}

	// Should include comic-template.html
	found := false
	for _, f := range files {
		if f == "comic-template.html" {
			found = true
		}
	}
	if !found {
		t.Error("resource files should include comic-template.html")
	}
}

// ── Agent Model Flag Parsing ────────────────────────────────────────────────

func TestParseAgentModelFlags(t *testing.T) {
	flags := []string{"gilfoyle=openai/gpt-4o", "dinesh=anthropic/claude-sonnet-4-6"}
	result, err := parseAgentModelFlags(flags)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["gilfoyle"] != "openai/gpt-4o" {
		t.Errorf("gilfoyle = %q, want openai/gpt-4o", result["gilfoyle"])
	}
	if result["dinesh"] != "anthropic/claude-sonnet-4-6" {
		t.Errorf("dinesh = %q, want anthropic/claude-sonnet-4-6", result["dinesh"])
	}
}

func TestParseAgentModelFlags_Empty(t *testing.T) {
	result, err := parseAgentModelFlags(nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result) != 0 {
		t.Errorf("got %d entries, want 0", len(result))
	}
}

func TestParseAgentModelFlags_InvalidFormat(t *testing.T) {
	_, err := parseAgentModelFlags([]string{"no-equals-sign"})
	if err == nil {
		t.Fatal("expected error for invalid format")
	}
}

func TestParseAgentModelFlags_EmptyName(t *testing.T) {
	_, err := parseAgentModelFlags([]string{"=model"})
	if err == nil {
		t.Fatal("expected error for empty name")
	}
}

func TestParseAgentModelFlags_EmptyModel(t *testing.T) {
	_, err := parseAgentModelFlags([]string{"name="})
	if err == nil {
		t.Fatal("expected error for empty model")
	}
}

// ── buildSkillPayload Integration ───────────────────────────────────────────

func TestBuildSkillPayload_SimpleSkill(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	// Set the package-level flags for the test
	oldModel := skillModel
	oldAgentModels := skillAgentModels
	defer func() {
		skillModel = oldModel
		skillAgentModels = oldAgentModels
	}()
	skillModel = "openai/gpt-4o"
	skillAgentModels = nil

	payload, name, err := buildSkillPayload(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if name != "simple-skill" {
		t.Errorf("name = %q, want simple-skill", name)
	}

	config, ok := payload["config"].(map[string]interface{})
	if !ok {
		t.Fatal("payload missing config")
	}

	if config["model"] != "openai/gpt-4o" {
		t.Errorf("model = %q, want openai/gpt-4o", config["model"])
	}

	agentFiles, ok := config["agentFiles"].(map[string]string)
	if !ok {
		t.Fatalf("agentFiles is not map[string]string: %T", config["agentFiles"])
	}
	if len(agentFiles) != 0 {
		t.Errorf("agentFiles has %d entries, want 0", len(agentFiles))
	}

	scripts, ok := config["scripts"].(map[string]scriptInfo)
	if !ok {
		t.Fatalf("scripts is not map[string]scriptInfo: %T", config["scripts"])
	}
	if len(scripts) != 0 {
		t.Errorf("scripts has %d entries, want 0", len(scripts))
	}
}

func TestBuildSkillPayload_DGSkill(t *testing.T) {
	dir := t.TempDir()
	createDGSkill(t, dir)

	oldModel := skillModel
	oldAgentModels := skillAgentModels
	defer func() {
		skillModel = oldModel
		skillAgentModels = oldAgentModels
	}()
	skillModel = "anthropic/claude-sonnet-4-6"
	skillAgentModels = []string{"gilfoyle=openai/gpt-4o"}

	payload, name, err := buildSkillPayload(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if name != "dg-skill" {
		t.Errorf("name = %q, want dg-skill", name)
	}

	config := payload["config"].(map[string]interface{})

	agentFiles := config["agentFiles"].(map[string]string)
	if len(agentFiles) != 2 {
		t.Fatalf("agentFiles has %d entries, want 2", len(agentFiles))
	}
	if _, ok := agentFiles["gilfoyle"]; !ok {
		t.Error("missing gilfoyle in agentFiles")
	}
	if _, ok := agentFiles["dinesh"]; !ok {
		t.Error("missing dinesh in agentFiles")
	}

	agentModelsMap := config["agentModels"].(map[string]string)
	if agentModelsMap["gilfoyle"] != "openai/gpt-4o" {
		t.Errorf("agentModels[gilfoyle] = %q, want openai/gpt-4o", agentModelsMap["gilfoyle"])
	}

	resourceFiles := config["resourceFiles"].([]string)
	found := false
	for _, f := range resourceFiles {
		if f == "comic-template.html" {
			found = true
		}
	}
	if !found {
		t.Error("resourceFiles should include comic-template.html")
	}
}

func TestBuildSkillPayload_MissingSkillMd(t *testing.T) {
	dir := t.TempDir()
	// Empty directory — no SKILL.md

	oldModel := skillModel
	defer func() { skillModel = oldModel }()
	skillModel = "openai/gpt-4o"

	_, _, err := buildSkillPayload(dir)
	if err == nil {
		t.Fatal("expected error for missing SKILL.md")
	}
}

func TestBuildSkillPayload_MissingName(t *testing.T) {
	dir := t.TempDir()
	skillMd := "---\ndescription: no name\n---\n# Body"
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)

	oldModel := skillModel
	defer func() { skillModel = oldModel }()
	skillModel = "openai/gpt-4o"

	_, _, err := buildSkillPayload(dir)
	if err == nil {
		t.Fatal("expected error for missing name")
	}
}

// ── Skill Run Integration ───────────────────────────────────────────────────

func TestSkillRun_Integration(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	// Mock server: accept POST /api/agent/start, return execution ID
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "POST" && r.URL.Path == "/api/agent/start":
			var req map[string]interface{}
			json.NewDecoder(r.Body).Decode(&req)

			// Framework agents use top-level "framework" + "rawConfig"
			if req["framework"] != "skill" {
				http.Error(w, fmt.Sprintf("expected framework=skill, got %v", req["framework"]), http.StatusBadRequest)
				return
			}
			if req["rawConfig"] == nil {
				http.Error(w, "missing rawConfig", http.StatusBadRequest)
				return
			}

			json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-123",
				"agentName":   "simple-skill",
			})

		case r.Method == "GET" && r.URL.Path == "/api/agent/exec-123/status":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"status": "COMPLETED",
				"output": map[string]string{"result": "done"},
			})

		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	// Set up globals for the test
	oldModel := skillModel
	oldStream := skillStream
	oldTimeout := skillTimeout
	oldServerURL := serverURL
	defer func() {
		skillModel = oldModel
		skillStream = oldStream
		skillTimeout = oldTimeout
		serverURL = oldServerURL
	}()

	skillModel = "openai/gpt-4o"
	skillStream = false
	skillTimeout = 10
	serverURL = srv.URL

	err := runSkillRun(nil, []string{dir, "test prompt"})
	if err != nil {
		t.Fatalf("runSkillRun error: %v", err)
	}
}

// ── Skill Load Integration ──────────────────────────────────────────────────

func TestSkillLoad_Integration(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/api/agent/compile" {
			var req map[string]interface{}
			json.NewDecoder(r.Body).Decode(&req)

			// Compile also uses "agentConfig" wrapper (client.Compile wraps it)
			agentConfig, ok := req["agentConfig"].(map[string]interface{})
			if !ok {
				http.Error(w, "missing agentConfig", http.StatusBadRequest)
				return
			}
			if agentConfig["rawConfig"] == nil {
				http.Error(w, "missing rawConfig in agentConfig", http.StatusBadRequest)
				return
			}

			json.NewEncoder(w).Encode(map[string]string{
				"status": "compiled",
				"name":   "simple-skill",
			})
			return
		}
		http.Error(w, "unexpected request", http.StatusNotFound)
	}))
	defer srv.Close()

	oldModel := skillModel
	oldServerURL := serverURL
	defer func() {
		skillModel = oldModel
		serverURL = oldServerURL
	}()

	skillModel = "openai/gpt-4o"
	serverURL = srv.URL

	err := runSkillLoad(nil, []string{dir})
	if err != nil {
		t.Fatalf("runSkillLoad error: %v", err)
	}
}

// ── Skill Serve ─────────────────────────────────────────────────────────────

func TestSkillServe_ValidSkill(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	err := runSkillServe(nil, []string{dir})
	if err != nil {
		t.Fatalf("runSkillServe error: %v", err)
	}
}

func TestSkillServe_InvalidDir(t *testing.T) {
	dir := t.TempDir()
	// No SKILL.md

	err := runSkillServe(nil, []string{dir})
	if err == nil {
		t.Fatal("expected error for directory without SKILL.md")
	}
}

// ── Param Flag Parsing ──────────────────────────────────────────────────────

func TestParseParamFlags(t *testing.T) {
	flags := []string{"rounds=5", "style=verbose"}
	result, err := parseParamFlags(flags)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result) != 2 {
		t.Fatalf("got %d params, want 2", len(result))
	}
	if result[0][0] != "rounds" || result[0][1] != "5" {
		t.Errorf("param[0] = %v, want [rounds, 5]", result[0])
	}
	if result[1][0] != "style" || result[1][1] != "verbose" {
		t.Errorf("param[1] = %v, want [style, verbose]", result[1])
	}
}

func TestParseParamFlags_Empty(t *testing.T) {
	result, err := parseParamFlags(nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result) != 0 {
		t.Errorf("got %d params, want 0", len(result))
	}
}

func TestParseParamFlags_InvalidFormat(t *testing.T) {
	_, err := parseParamFlags([]string{"no-equals-sign"})
	if err == nil {
		t.Fatal("expected error for invalid format")
	}
}

func TestParseParamFlags_EmptyKey(t *testing.T) {
	_, err := parseParamFlags([]string{"=value"})
	if err == nil {
		t.Fatal("expected error for empty key")
	}
}

func TestParseParamFlags_EmptyValueAllowed(t *testing.T) {
	result, err := parseParamFlags([]string{"key="})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result[0][0] != "key" || result[0][1] != "" {
		t.Errorf("param = %v, want [key, ]", result[0])
	}
}

func TestParseParamFlags_ValueWithEquals(t *testing.T) {
	result, err := parseParamFlags([]string{"expr=a=b"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result[0][0] != "expr" || result[0][1] != "a=b" {
		t.Errorf("param = %v, want [expr, a=b]", result[0])
	}
}

// ── Prompt Formatting ───────────────────────────────────────────────────────

func TestFormatPromptWithParams_Empty(t *testing.T) {
	result := formatPromptWithParams("hello", nil)
	if result != "hello" {
		t.Errorf("got %q, want 'hello'", result)
	}
}

func TestFormatPromptWithParams_WithParams(t *testing.T) {
	params := [][2]string{{"rounds", "5"}, {"style", "verbose"}}
	result := formatPromptWithParams("Review this code", params)

	if !strings.Contains(result, "[Skill Parameters]") {
		t.Error("missing [Skill Parameters] header")
	}
	if !strings.Contains(result, "rounds: 5") {
		t.Error("missing rounds param")
	}
	if !strings.Contains(result, "style: verbose") {
		t.Error("missing style param")
	}
	if !strings.Contains(result, "[User Request]") {
		t.Error("missing [User Request] header")
	}
	if !strings.HasSuffix(result, "Review this code") {
		t.Error("prompt not at end")
	}
}

// ── Poll Execution ──────────────────────────────────────────────────────────

func TestPollExecution_Completed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "COMPLETED",
			"output": map[string]string{"result": "all done"},
		})
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))

	err := pollExecution(c, "exec-1", 10*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestPollExecution_Failed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "FAILED",
		})
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))

	err := pollExecution(c, "exec-1", 10*time.Second)
	if err == nil {
		t.Fatal("expected error for failed execution")
	}
}
