// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------- detectLanguage ----------

func TestDetectLanguage_Python(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte("[project]\nname = \"foo\"\n"), 0o644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Errorf("got %q, want python", lang)
	}
}

func TestDetectLanguage_SetupPy(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "setup.py"), []byte(""), 0o644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Errorf("got %q, want python", lang)
	}
}

func TestDetectLanguage_Typescript(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "tsconfig.json"), []byte("{}"), 0o644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "typescript" {
		t.Errorf("got %q, want typescript", lang)
	}
}

func TestDetectLanguage_PackageJsonWithTypescript(t *testing.T) {
	dir := t.TempDir()
	pkgJSON := `{"devDependencies": {"typescript": "^5.0.0"}}`
	os.WriteFile(filepath.Join(dir, "package.json"), []byte(pkgJSON), 0o644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "typescript" {
		t.Errorf("got %q, want typescript", lang)
	}
}

func TestDetectLanguage_BothError(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte("[project]\nname = \"x\"\n"), 0o644)
	os.WriteFile(filepath.Join(dir, "tsconfig.json"), []byte("{}"), 0o644)

	_, err := detectLanguage(dir, "")
	if err == nil {
		t.Fatal("expected error when both markers present")
	}
	if !strings.Contains(err.Error(), "both") {
		t.Errorf("error should mention 'both': %v", err)
	}
}

func TestDetectLanguage_NeitherError(t *testing.T) {
	dir := t.TempDir()

	_, err := detectLanguage(dir, "")
	if err == nil {
		t.Fatal("expected error when no markers present")
	}
	if !strings.Contains(err.Error(), "no Python or TypeScript") {
		t.Errorf("error should mention missing markers: %v", err)
	}
}

func TestDetectLanguage_Override(t *testing.T) {
	dir := t.TempDir()
	// No marker files needed when override is set

	lang, err := detectLanguage(dir, "python")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Errorf("got %q, want python", lang)
	}

	lang, err = detectLanguage(dir, "typescript")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "typescript" {
		t.Errorf("got %q, want typescript", lang)
	}
}

// ---------- inferPackage ----------

func TestInferPackage_Pyproject(t *testing.T) {
	dir := t.TempDir()
	toml := "[project]\nname = \"my_agent\"\n"
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(toml), 0o644)

	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg.Value != "my_agent" || pkg.IsPath {
		t.Errorf("got %+v, want Value=my_agent IsPath=false", pkg)
	}
}

func TestInferPackage_HyphensToUnderscores(t *testing.T) {
	dir := t.TempDir()
	toml := "[project]\nname = \"my-cool-agent\"\n"
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(toml), 0o644)

	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg.Value != "my_cool_agent" {
		t.Errorf("got %q, want my_cool_agent", pkg.Value)
	}
}

func TestInferPackage_TypescriptDefault(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "src"), 0o755)

	pkg, err := inferPackage(dir, "typescript", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg.Value != "./src" {
		t.Errorf("got %q, want ./src", pkg.Value)
	}

	// Without src directory, should default to "."
	dir2 := t.TempDir()
	pkg2, err := inferPackage(dir2, "typescript", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg2.Value != "." {
		t.Errorf("got %q, want .", pkg2.Value)
	}
}

func TestInferPackage_Override(t *testing.T) {
	dir := t.TempDir()

	pkg, err := inferPackage(dir, "python", "custom_pkg")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg.Value != "custom_pkg" {
		t.Errorf("got %q, want custom_pkg", pkg.Value)
	}
}

func TestInferPackage_PythonFallsBackToPath(t *testing.T) {
	dir := t.TempDir()
	// No pyproject.toml — should fall back to directory path

	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !pkg.IsPath {
		t.Errorf("expected IsPath=true for directory fallback, got %+v", pkg)
	}
	if pkg.Value != dir {
		t.Errorf("got %q, want %q", pkg.Value, dir)
	}
}

// ---------- findPythonBinary ----------

func TestFindPythonBinary_Venv(t *testing.T) {
	dir := t.TempDir()
	venvBin := filepath.Join(dir, ".venv", "bin")
	os.MkdirAll(venvBin, 0o755)
	pythonPath := filepath.Join(venvBin, "python")
	os.WriteFile(pythonPath, []byte("#!/bin/sh\n"), 0o755)

	// Clear PYTHON env var for this test
	t.Setenv("PYTHON", "")

	got := findPythonBinary(dir)
	if got != pythonPath {
		t.Errorf("got %q, want %q", got, pythonPath)
	}
}

func TestFindPythonBinary_FallsToPath(t *testing.T) {
	dir := t.TempDir()
	// No venv present
	t.Setenv("PYTHON", "")

	got := findPythonBinary(dir)
	// Should find python3 or python on PATH, or empty string
	// We can't guarantee PATH has python, so just check it doesn't panic
	// and returns something (on CI python3 is typically available)
	if got == "" {
		t.Log("no python found on PATH (ok in minimal environments)")
	} else if !strings.Contains(got, "python") {
		t.Errorf("expected path containing 'python', got %q", got)
	}
}

// ---------- parseDiscoveryResult ----------

func TestParseDiscoveryResult_Valid(t *testing.T) {
	data := []byte(`[{"name":"agent1","framework":"crewai"},{"name":"agent2","framework":"langgraph"}]`)

	agents, err := parseDiscoveryResult(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 2 {
		t.Fatalf("got %d agents, want 2", len(agents))
	}
	if agents[0].Name != "agent1" || agents[0].Framework != "crewai" {
		t.Errorf("agent[0] = %+v, want name=agent1 framework=crewai", agents[0])
	}
	if agents[1].Name != "agent2" || agents[1].Framework != "langgraph" {
		t.Errorf("agent[1] = %+v, want name=agent2 framework=langgraph", agents[1])
	}
}

func TestParseDiscoveryResult_Empty(t *testing.T) {
	data := []byte(`[]`)

	agents, err := parseDiscoveryResult(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 0 {
		t.Errorf("got %d agents, want 0", len(agents))
	}
}

func TestParseDiscoveryResult_InvalidJSON(t *testing.T) {
	data := []byte(`not json at all`)

	_, err := parseDiscoveryResult(data)
	if err == nil {
		t.Fatal("expected error for invalid JSON")
	}
}

// ---------- parseDeployResult ----------

func TestParseDeployResult(t *testing.T) {
	regName := "agent1_registered"
	data := []byte(`[
		{"agent_name":"agent1","registered_name":"agent1_registered","success":true,"error":null},
		{"agent_name":"agent2","registered_name":null,"success":false,"error":"connection refused"}
	]`)

	results, err := parseDeployResult(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("got %d results, want 2", len(results))
	}
	if !results[0].Success || results[0].AgentName != "agent1" {
		t.Errorf("result[0] = %+v, want success=true agent_name=agent1", results[0])
	}
	if results[0].RegisteredName == nil || *results[0].RegisteredName != regName {
		t.Errorf("result[0].RegisteredName = %v, want %q", results[0].RegisteredName, regName)
	}
	if results[1].Success || results[1].Error == nil || *results[1].Error != "connection refused" {
		t.Errorf("result[1] = %+v, want success=false error='connection refused'", results[1])
	}
}

// ---------- filterDiscoveredAgents ----------

func TestFilterDiscoveredAgents_FilterWorks(t *testing.T) {
	agents := []discoveredAgent{
		{Name: "alpha", Framework: "crewai"},
		{Name: "beta", Framework: "langgraph"},
		{Name: "gamma", Framework: "autogen"},
	}

	filtered, err := filterDiscoveredAgents(agents, []string{"alpha", "gamma"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(filtered) != 2 {
		t.Fatalf("got %d, want 2", len(filtered))
	}
	if filtered[0].Name != "alpha" || filtered[1].Name != "gamma" {
		t.Errorf("got %v, want alpha and gamma", filtered)
	}

	// Empty names returns all
	all, err := filterDiscoveredAgents(agents, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(all) != 3 {
		t.Errorf("got %d, want 3", len(all))
	}
}

func TestFilterDiscoveredAgents_NotFoundError(t *testing.T) {
	agents := []discoveredAgent{
		{Name: "alpha", Framework: "crewai"},
	}

	_, err := filterDiscoveredAgents(agents, []string{"alpha", "missing"})
	if err == nil {
		t.Fatal("expected error for missing agent")
	}
	if !strings.Contains(err.Error(), "missing") {
		t.Errorf("error should mention 'missing': %v", err)
	}
}

// ---------- formatDeployOutput ----------

func TestFormatDeployOutput_AllSuccess(t *testing.T) {
	wf := "wf1"
	results := []deployResult{
		{AgentName: "a1", RegisteredName: &wf, Success: true},
		{AgentName: "a2", RegisteredName: &wf, Success: true},
	}

	out := formatDeployOutput(results)
	if !strings.Contains(out, "a1") || !strings.Contains(out, "a2") {
		t.Errorf("output should contain agent names: %s", out)
	}
	if !strings.Contains(out, "All 2 agent(s) deployed successfully") {
		t.Errorf("output should show all-success summary: %s", out)
	}
}

func TestFormatDeployOutput_Partial(t *testing.T) {
	wf := "wf1"
	results := []deployResult{
		{AgentName: "a1", RegisteredName: &wf, Success: true},
		{AgentName: "a2", Success: false, Error: strPtr("timeout")},
	}

	out := formatDeployOutput(results)
	if !strings.Contains(out, "1 deployed") || !strings.Contains(out, "1 failed") {
		t.Errorf("output should show partial summary: %s", out)
	}
}

func TestFormatDeployOutput_AllFailed(t *testing.T) {
	results := []deployResult{
		{AgentName: "a1", Success: false, Error: strPtr("err1")},
		{AgentName: "a2", Success: false, Error: strPtr("err2")},
	}

	out := formatDeployOutput(results)
	if !strings.Contains(out, "All 2 agent(s) failed to deploy") {
		t.Errorf("output should show all-failed summary: %s", out)
	}
}

func strPtr(s string) *string { return &s }
