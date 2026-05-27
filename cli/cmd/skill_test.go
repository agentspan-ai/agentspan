// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
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

func createParamSkill(t *testing.T, dir string) {
	t.Helper()
	skillMd := `---
name: param-skill
description: A skill with params.
params:
  rounds:
    default: 3
  style: concise
---

# Param Skill

Use the provided parameters.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)
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
		"assets/template.html",
		"examples/usage.md",
		"extra.txt",
		"references/api.md",
		"references/guide.md",
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

func TestNormalizeSkillResourcePath_AcceptsWindowsSeparators(t *testing.T) {
	got := normalizeSkillResourcePath(`references\api.md`)
	if got != "references/api.md" {
		t.Fatalf("normalizeSkillResourcePath() = %q, want references/api.md", got)
	}

	section := normalizeSkillResourcePath("skill_section:Workflow")
	if section != "skill_section:Workflow" {
		t.Fatalf("skill section path = %q, want unchanged section path", section)
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

func TestBuildSkillPayload_ParamsMergedIntoRawConfig(t *testing.T) {
	dir := t.TempDir()
	createParamSkill(t, dir)

	oldModel := skillModel
	oldParams := skillParams
	defer func() {
		skillModel = oldModel
		skillParams = oldParams
	}()
	skillModel = "openai/gpt-4o"
	skillParams = []string{"rounds=5", "verbose=true"}

	payload, _, err := buildSkillPayload(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	config := payload["config"].(map[string]interface{})

	params := config["params"].(map[string]interface{})
	if params["rounds"] != "5" {
		t.Errorf("rounds = %v, want 5", params["rounds"])
	}
	if params["style"] != "concise" {
		t.Errorf("style = %v, want concise", params["style"])
	}
	if params["verbose"] != true {
		t.Errorf("verbose = %v, want true", params["verbose"])
	}
	if !strings.Contains(config["skillMd"].(string), "[Skill Parameters]") {
		t.Error("skillMd missing Skill Parameters block")
	}
}

func TestBuildSkillPayload_ResolvesCrossSkillReferences(t *testing.T) {
	root := t.TempDir()
	parent := filepath.Join(root, "parent-skill")
	child := filepath.Join(root, "child-skill")
	os.MkdirAll(parent, 0o755)
	os.MkdirAll(child, 0o755)
	os.WriteFile(filepath.Join(parent, "SKILL.md"), []byte(`---
name: parent-skill
---
# Parent

Use the child-skill skill for details.
`), 0o644)
	os.WriteFile(filepath.Join(child, "SKILL.md"), []byte(`---
name: child-skill
---
# Child
`), 0o644)

	oldModel := skillModel
	oldSearch := skillSearchPaths
	defer func() {
		skillModel = oldModel
		skillSearchPaths = oldSearch
	}()
	skillModel = "openai/gpt-4o"
	skillSearchPaths = nil

	payload, _, err := buildSkillPayload(parent)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	config := payload["config"].(map[string]interface{})
	refs := config["crossSkillRefs"].(map[string]interface{})
	if _, ok := refs["child-skill"]; !ok {
		t.Fatalf("missing child-skill ref: %#v", refs)
	}

	clean := stripLocalSkillFields(config)
	cleanRefs := clean["crossSkillRefs"].(map[string]interface{})
	childConfig := cleanRefs["child-skill"].(map[string]interface{})
	if _, ok := childConfig["_skillPath"]; ok {
		t.Fatal("local skill path leaked into rawConfig")
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

func TestBuildSkillPackage_IncludesSkillFiles(t *testing.T) {
	dir := t.TempDir()
	createResourceSkill(t, dir)

	data, files, err := buildSkillPackage(dir)
	if err != nil {
		t.Fatalf("buildSkillPackage: %v", err)
	}
	if len(data) == 0 {
		t.Fatal("package is empty")
	}

	paths := make([]string, 0, len(files))
	for _, f := range files {
		paths = append(paths, f.Path)
		if f.SHA256 == "" {
			t.Fatalf("missing checksum for %s", f.Path)
		}
	}
	sort.Strings(paths)
	for _, want := range []string{"SKILL.md", "references/api.md", "examples/usage.md", "assets/template.html"} {
		found := false
		for _, got := range paths {
			if got == want {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("package missing %s; paths=%v", want, paths)
		}
	}

	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		t.Fatalf("open zip: %v", err)
	}
	if len(reader.File) != len(files) {
		t.Fatalf("zip entries=%d files=%d", len(reader.File), len(files))
	}
}

func TestBuildSkillPackage_ExcludesSecretsAndAgentspanIgnore(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)
	os.WriteFile(filepath.Join(dir, ".env"), []byte("TOKEN=secret"), 0o600)
	os.WriteFile(filepath.Join(dir, "private.pem"), []byte("secret-key"), 0o600)
	os.WriteFile(filepath.Join(dir, "notes.tmp"), []byte("generated"), 0o644)
	os.WriteFile(filepath.Join(dir, ".agentspanignore"), []byte("notes.tmp\nignored/\n"), 0o644)
	os.MkdirAll(filepath.Join(dir, "ignored"), 0o755)
	os.WriteFile(filepath.Join(dir, "ignored", "artifact.txt"), []byte("artifact"), 0o644)

	_, files, err := buildSkillPackage(dir)
	if err != nil {
		t.Fatalf("buildSkillPackage: %v", err)
	}
	paths := make([]string, 0, len(files))
	for _, file := range files {
		paths = append(paths, file.Path)
	}
	for _, excluded := range []string{".env", "private.pem", "notes.tmp", ".agentspanignore", "ignored/artifact.txt"} {
		for _, got := range paths {
			if got == excluded {
				t.Fatalf("package included excluded file %q; paths=%v", excluded, paths)
			}
		}
	}
}

func TestSkillRegister_Integration(t *testing.T) {
	dir := t.TempDir()
	createResourceSkill(t, dir)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/api/skills/register" {
			http.Error(w, "unexpected request", http.StatusNotFound)
			return
		}
		if err := r.ParseMultipartForm(10 << 20); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		manifest := r.FormValue("manifest")
		var body map[string]interface{}
		if err := json.Unmarshal([]byte(manifest), &body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if body["name"] != "resource-skill" {
			http.Error(w, fmt.Sprintf("name=%v", body["name"]), http.StatusBadRequest)
			return
		}
		if body["model"] != "openai/gpt-4o" {
			http.Error(w, fmt.Sprintf("model=%v", body["model"]), http.StatusBadRequest)
			return
		}
		if body["rawConfig"] != nil {
			http.Error(w, "rawConfig should not be sent during register", http.StatusBadRequest)
			return
		}
		file, _, err := r.FormFile("package")
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		data, _ := io.ReadAll(file)
		reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		hasSkillMd := false
		for _, entry := range reader.File {
			if entry.Name == "SKILL.md" {
				hasSkillMd = true
			}
		}
		if !hasSkillMd {
			http.Error(w, "missing SKILL.md", http.StatusBadRequest)
			return
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"name":      "resource-skill",
			"version":   "v1",
			"status":    "READY",
			"fileCount": len(reader.File),
		})
	}))
	defer srv.Close()

	oldModel := skillModel
	oldServerURL := serverURL
	oldVersion := skillVersion
	defer func() {
		skillModel = oldModel
		serverURL = oldServerURL
		skillVersion = oldVersion
	}()
	skillModel = "openai/gpt-4o"
	serverURL = srv.URL
	skillVersion = "v1"

	if err := runSkillRegister(nil, []string{dir}); err != nil {
		t.Fatalf("runSkillRegister: %v", err)
	}
}

func TestSkillDelete_Integration(t *testing.T) {
	sawDelete := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "DELETE" || r.URL.Path != "/api/skills/resource-skill/versions/v1" {
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
			return
		}
		sawDelete = true
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	oldServerURL := serverURL
	oldVersion := skillVersion
	oldYes := skillDeleteYes
	defer func() {
		serverURL = oldServerURL
		skillVersion = oldVersion
		skillDeleteYes = oldYes
	}()
	serverURL = srv.URL
	skillVersion = "v1"
	skillDeleteYes = true

	if err := runSkillDelete(nil, []string{"resource-skill"}); err != nil {
		t.Fatalf("runSkillDelete: %v", err)
	}
	if !sawDelete {
		t.Fatal("server did not receive DELETE")
	}
}

func TestSkillDelete_RequiresConfirmation(t *testing.T) {
	oldYes := skillDeleteYes
	defer func() { skillDeleteYes = oldYes }()
	skillDeleteYes = false

	err := runSkillDelete(nil, []string{"resource-skill", "v1"})
	if err == nil || !strings.Contains(err.Error(), "without --yes") {
		t.Fatalf("expected confirmation error, got %v", err)
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

func TestSkillRun_RegisteredSkillUsesSkillRef(t *testing.T) {
	newTempHome(t)
	dir := t.TempDir()
	skillMd := `---
name: registered-skill
description: Parent skill.
---

# Parent

Use the child-skill skill.
`
	os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(skillMd), 0o644)
	zipBytes, _, err := buildSkillPackage(dir)
	if err != nil {
		t.Fatalf("buildSkillPackage: %v", err)
	}
	checksum := testSHA256(zipBytes)
	childDir := t.TempDir()
	childMd := `---
name: child-skill
description: Child skill.
---

# Child
`
	os.WriteFile(filepath.Join(childDir, "SKILL.md"), []byte(childMd), 0o644)
	childZipBytes, _, err := buildSkillPackage(childDir)
	if err != nil {
		t.Fatalf("build child package: %v", err)
	}
	childChecksum := testSHA256(childZipBytes)
	var childFetched bool

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"name":     "registered-skill",
				"version":  "v1",
				"status":   "READY",
				"checksum": checksum,
			})
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill/versions/v1/package":
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Write(zipBytes)
		case r.Method == "GET" && r.URL.Path == "/api/skills/child-skill":
			childFetched = true
			json.NewEncoder(w).Encode(map[string]interface{}{
				"name":     "child-skill",
				"version":  "v1",
				"status":   "READY",
				"checksum": childChecksum,
			})
		case r.Method == "GET" && r.URL.Path == "/api/skills/child-skill/versions/v1/package":
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Write(childZipBytes)
		case r.Method == "POST" && r.URL.Path == "/api/agent/start":
			var req map[string]interface{}
			json.NewDecoder(r.Body).Decode(&req)
			if req["rawConfig"] != nil {
				http.Error(w, "registered run should use skillRef, not rawConfig", http.StatusBadRequest)
				return
			}
			ref := req["skillRef"].(map[string]interface{})
			if ref["name"] != "registered-skill" || ref["version"] != "v1" || ref["model"] != "openai/gpt-4o" {
				http.Error(w, fmt.Sprintf("bad skillRef: %#v", ref), http.StatusBadRequest)
				return
			}
			params, _ := ref["params"].(map[string]interface{})
			if params["mode"] != "review" {
				http.Error(w, fmt.Sprintf("missing params in skillRef: %#v", ref), http.StatusBadRequest)
				return
			}
			json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-registered",
				"agentName":   "registered-skill",
			})
		case r.Method == "GET" && r.URL.Path == "/api/agent/exec-registered/status":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"status": "COMPLETED",
				"output": map[string]string{"result": "done"},
			})
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	oldModel := skillModel
	oldStream := skillStream
	oldTimeout := skillTimeout
	oldServerURL := serverURL
	oldVersion := skillVersion
	oldParams := skillParams
	defer func() {
		skillModel = oldModel
		skillStream = oldStream
		skillTimeout = oldTimeout
		serverURL = oldServerURL
		skillVersion = oldVersion
		skillParams = oldParams
	}()

	skillModel = "openai/gpt-4o"
	skillStream = false
	skillTimeout = 10
	serverURL = srv.URL
	skillVersion = ""
	skillParams = []string{"mode=review"}

	if err := runSkillRun(nil, []string{"registered-skill", "test prompt"}); err != nil {
		t.Fatalf("runSkillRun error: %v", err)
	}
	if !childFetched {
		t.Fatal("registered cross-skill reference was not fetched")
	}
}

func TestSkillRun_IncludesWorkspaceContext(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)
	workspace := t.TempDir()
	docs := t.TempDir()
	os.WriteFile(filepath.Join(workspace, "main.go"), []byte("package main\n"), 0o644)
	os.WriteFile(filepath.Join(docs, "README.md"), []byte("# Docs\n"), 0o644)

	var startReq map[string]interface{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "GET" && strings.HasPrefix(r.URL.Path, "/api/tasks/poll/"):
			w.WriteHeader(http.StatusNoContent)
		case r.Method == "POST" && r.URL.Path == "/api/agent/start":
			json.NewDecoder(r.Body).Decode(&startReq)
			json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-workspace",
				"agentName":   "simple-skill",
			})
		case r.Method == "GET" && r.URL.Path == "/api/agent/exec-workspace/status":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"status": "COMPLETED",
				"output": map[string]string{"result": "done"},
			})
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	oldModel := skillModel
	oldStream := skillStream
	oldTimeout := skillTimeout
	oldServerURL := serverURL
	oldWorkspace := skillWorkspace
	oldNoWorkspace := skillNoWorkspace
	oldFileSystems := skillFileSystems
	defer func() {
		skillModel = oldModel
		skillStream = oldStream
		skillTimeout = oldTimeout
		serverURL = oldServerURL
		skillWorkspace = oldWorkspace
		skillNoWorkspace = oldNoWorkspace
		skillFileSystems = oldFileSystems
	}()

	skillModel = "openai/gpt-4o"
	skillStream = false
	skillTimeout = 10
	serverURL = srv.URL
	skillWorkspace = workspace
	skillNoWorkspace = false
	skillFileSystems = []string{"docs=" + docs}

	if err := runSkillRun(nil, []string{dir, "review this workspace"}); err != nil {
		t.Fatalf("runSkillRun error: %v", err)
	}

	rawConfig := startReq["rawConfig"].(map[string]interface{})
	workspaceConfig := rawConfig["workspace"].(map[string]interface{})
	roots := workspaceConfig["roots"].([]interface{})
	if len(roots) != 2 {
		t.Fatalf("workspace roots = %#v, want 2 roots", roots)
	}
	rootNames := []string{
		roots[0].(map[string]interface{})["name"].(string),
		roots[1].(map[string]interface{})["name"].(string),
	}
	sort.Strings(rootNames)
	if strings.Join(rootNames, ",") != "docs,workspace" {
		t.Fatalf("workspace root names = %v, want docs,workspace", rootNames)
	}

	context := startReq["context"].(map[string]interface{})
	contextWorkspace := context["workspace"].(map[string]interface{})
	contextRoots := contextWorkspace["roots"].([]interface{})
	if len(contextRoots) != 2 {
		t.Fatalf("context workspace roots = %#v, want 2 roots", contextRoots)
	}
}

func TestMaterializeSkillArg_RegisteredSkillCachesUnderAgentspan(t *testing.T) {
	home := newTempHome(t)
	dir := t.TempDir()
	createSimpleSkill(t, dir)
	zipBytes, _, err := buildSkillPackage(dir)
	if err != nil {
		t.Fatalf("buildSkillPackage: %v", err)
	}
	checksum := testSHA256(zipBytes)

	packageDownloads := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"name":        "registered-skill",
				"version":     "v1",
				"status":      "READY",
				"checksum":    checksum,
				"packageSize": len(zipBytes),
			})
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill/versions/v1/package":
			packageDownloads++
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Write(zipBytes)
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))
	gotDir, cleanup, detail, err := materializeSkillArg(c, "registered-skill")
	if err != nil {
		t.Fatalf("materializeSkillArg first run: %v", err)
	}
	cleanup()

	wantDir := filepath.Join(home, ".agentspan", "skills", "registered-skill", "v1", "files")
	if gotDir != wantDir {
		t.Fatalf("cached dir = %q, want %q", gotDir, wantDir)
	}
	if detail == nil || detail.Name != "registered-skill" || detail.Version != "v1" {
		t.Fatalf("detail = %#v, want registered-skill@v1", detail)
	}
	if _, err := os.Stat(filepath.Join(gotDir, "SKILL.md")); err != nil {
		t.Fatalf("cached SKILL.md missing: %v", err)
	}
	if packageDownloads != 1 {
		t.Fatalf("package downloads after first materialize = %d, want 1", packageDownloads)
	}

	gotDir, cleanup, _, err = materializeSkillArg(c, "registered-skill")
	if err != nil {
		t.Fatalf("materializeSkillArg second run: %v", err)
	}
	cleanup()
	if gotDir != wantDir {
		t.Fatalf("cached dir on second run = %q, want %q", gotDir, wantDir)
	}
	if packageDownloads != 1 {
		t.Fatalf("package downloads after second materialize = %d, want 1", packageDownloads)
	}
}

func TestMaterializeSkillArg_RejectsChecksumMismatch(t *testing.T) {
	newTempHome(t)
	dir := t.TempDir()
	createSimpleSkill(t, dir)
	zipBytes, _, err := buildSkillPackage(dir)
	if err != nil {
		t.Fatalf("buildSkillPackage: %v", err)
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"name":     "registered-skill",
				"version":  "v1",
				"status":   "READY",
				"checksum": strings.Repeat("0", 64),
			})
		case r.Method == "GET" && r.URL.Path == "/api/skills/registered-skill/versions/v1/package":
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Write(zipBytes)
		default:
			http.Error(w, "unexpected request: "+r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	defer srv.Close()

	c := client.New(newTestConfig(t, srv.URL))
	_, _, _, err = materializeSkillArg(c, "registered-skill")
	if err == nil || !strings.Contains(err.Error(), "checksum mismatch") {
		t.Fatalf("expected checksum mismatch error, got %v", err)
	}
}

func testSHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func TestWorkspaceFileTools_RespectConfiguredRoot(t *testing.T) {
	rootDir := t.TempDir()
	os.MkdirAll(filepath.Join(rootDir, "src"), 0o755)
	os.WriteFile(filepath.Join(rootDir, "src", "app.go"), []byte("package app\nfunc ReviewTarget() {}\n"), 0o644)
	os.WriteFile(filepath.Join(rootDir, "README.md"), []byte("Review Target\n"), 0o644)

	root := skillWorkspaceRoot{Name: "workspace", Path: rootDir, Kind: "workspace"}

	listed, err := listWorkspaceFiles(root, ".", "**/*.go", 10)
	if err != nil {
		t.Fatalf("listWorkspaceFiles: %v", err)
	}
	files := listed["files"].([]string)
	if len(files) != 1 || files[0] != "src/app.go" {
		t.Fatalf("files = %#v, want [src/app.go]", files)
	}

	read, err := readWorkspaceFile(root, "src/app.go", 1024)
	if err != nil {
		t.Fatalf("readWorkspaceFile: %v", err)
	}
	if !strings.Contains(read["content"].(string), "ReviewTarget") {
		t.Fatalf("read content = %#v", read["content"])
	}

	search, err := searchWorkspace(root, ".", "**/*.go", "reviewtarget", true, 10)
	if err != nil {
		t.Fatalf("searchWorkspace: %v", err)
	}
	matches := search["matches"].([]map[string]interface{})
	if len(matches) != 1 || matches[0]["path"] != "src/app.go" {
		t.Fatalf("matches = %#v, want src/app.go", matches)
	}

	if _, err := readWorkspaceFile(root, "../outside.txt", 1024); err == nil {
		t.Fatal("expected outside-root path to be rejected")
	}
}

// ── Skill Load Integration ──────────────────────────────────────────────────

func TestSkillLoad_Integration(t *testing.T) {
	dir := t.TempDir()
	createSimpleSkill(t, dir)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/api/agent/deploy" {
			var req map[string]interface{}
			json.NewDecoder(r.Body).Decode(&req)

			if req["framework"] != "skill" {
				http.Error(w, "missing framework=skill", http.StatusBadRequest)
				return
			}
			if req["rawConfig"] == nil {
				http.Error(w, "missing rawConfig", http.StatusBadRequest)
				return
			}

			json.NewEncoder(w).Encode(map[string]string{
				"agentName": "simple-skill",
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

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	cmd := skillServeCmd
	oldCtx := cmd.Context()
	defer cmd.SetContext(oldCtx)
	cmd.SetContext(ctx)

	err := runSkillServe(cmd, []string{dir})
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

func TestStartSkillWorkers_PollsTypedScriptAndResourceWorkers(t *testing.T) {
	dir := t.TempDir()
	createScriptSkill(t, dir)
	os.MkdirAll(filepath.Join(dir, "references"), 0o755)
	os.WriteFile(filepath.Join(dir, "references", "api.md"), []byte("# API Reference"), 0o644)

	oldModel := skillModel
	defer func() { skillModel = oldModel }()
	skillModel = "openai/gpt-4o"

	payload, _, err := buildSkillPayload(dir)
	if err != nil {
		t.Fatalf("buildSkillPayload: %v", err)
	}
	config := payload["config"].(map[string]interface{})

	updates := make(chan map[string]interface{}, 4)
	var mu sync.Mutex
	polled := map[string]bool{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "GET" && strings.HasPrefix(r.URL.Path, "/api/tasks/poll/"):
			taskType := strings.TrimPrefix(r.URL.Path, "/api/tasks/poll/")
			mu.Lock()
			already := polled[taskType]
			polled[taskType] = true
			mu.Unlock()
			if already {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			switch taskType {
			case "script-skill__read_skill_file":
				json.NewEncoder(w).Encode(map[string]interface{}{
					"taskId":             "read-1",
					"workflowInstanceId": "wf-1",
					"inputData":          map[string]interface{}{"path": filepath.Join("references", "api.md")},
				})
			case "script-skill__hello":
				json.NewEncoder(w).Encode(map[string]interface{}{
					"taskId":             "script-1",
					"workflowInstanceId": "wf-1",
					"inputData":          map[string]interface{}{"command": ""},
				})
			default:
				w.WriteHeader(http.StatusNoContent)
			}
		case r.Method == "POST" && r.URL.Path == "/api/tasks":
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)
			updates <- body
			json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		default:
			http.Error(w, "unexpected request", http.StatusNotFound)
		}
	}))
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	startSkillWorkers(ctx, client.New(newTestConfig(t, srv.URL)), "script-skill", dir, config, skillWorkspaceConfig{})

	deadline := time.After(5 * time.Second)
	var sawRead, sawScript bool
	for !(sawRead && sawScript) {
		select {
		case update := <-updates:
			data := update["outputData"].(map[string]interface{})
			result := fmt.Sprint(data["result"])
			switch update["taskId"] {
			case "read-1":
				sawRead = strings.Contains(result, "# API Reference")
			case "script-1":
				sawScript = strings.Contains(result, "hello")
			}
		case <-deadline:
			t.Fatalf("timed out waiting for read/script worker updates; read=%v script=%v", sawRead, sawScript)
		}
	}
}

func TestExecuteScript_UsesSkillRootAndLimitsOutput(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		if _, err := exec.LookPath("python"); err != nil {
			t.Skip("python interpreter not available")
		}
	}

	dir := t.TempDir()
	scriptsDir := filepath.Join(dir, "scripts")
	if err := os.MkdirAll(scriptsDir, 0o755); err != nil {
		t.Fatalf("mkdir scripts: %v", err)
	}
	scriptPath := filepath.Join(scriptsDir, "probe.py")
	workspaceDir := t.TempDir()
	script := "import os\nprint(os.getcwd())\nprint(os.environ.get('AGENTSPAN_SKILL_DIR', ''))\nprint(os.path.basename(os.environ.get('AGENTSPAN_WORKSPACE_DIR', '')))\nprint('x' * 2048)\n"
	if err := os.WriteFile(scriptPath, []byte(script), 0o755); err != nil {
		t.Fatalf("write script: %v", err)
	}

	oldTimeout := skillScriptTimeout
	oldLimit := skillScriptOutputLimit
	defer func() {
		skillScriptTimeout = oldTimeout
		skillScriptOutputLimit = oldLimit
	}()
	skillScriptTimeout = 10
	skillScriptOutputLimit = 256

	workspaceCfg := skillWorkspaceConfig{
		Enabled: true,
		Roots: []skillWorkspaceRoot{{
			Name: "workspace",
			Path: workspaceDir,
			Kind: "workspace",
		}},
	}
	output, err := executeScript(scriptPath, "python", "", workspaceCfg)
	if err != nil {
		t.Fatalf("executeScript: %v", err)
	}
	text := fmt.Sprint(output)
	if !strings.Contains(text, dir) {
		t.Fatalf("script did not run from skill root or expose AGENTSPAN_SKILL_DIR: %q", text)
	}
	if !strings.Contains(text, filepath.Base(workspaceDir)) {
		t.Fatalf("script did not expose AGENTSPAN_WORKSPACE_DIR: %q", text)
	}
	if !strings.Contains(text, "output truncated after 256 bytes") {
		t.Fatalf("script output was not truncated: %q", text)
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
