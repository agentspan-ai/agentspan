package cmd

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// makeFakePip writes a small shell script that records its args to a file and exits 0.
func makeFakePip(t *testing.T, recordFile string) string {
	t.Helper()
	tmp := t.TempDir()
	script := filepath.Join(tmp, "pip3")
	content := "#!/bin/sh\necho \"$@\" >> " + recordFile + "\n"
	if err := os.WriteFile(script, []byte(content), 0o755); err != nil {
		t.Fatal(err)
	}
	return script
}

func pipArgs(t *testing.T, recordFile string) []string {
	t.Helper()
	data, err := os.ReadFile(recordFile)
	if err != nil {
		return nil
	}
	return strings.Fields(strings.TrimSpace(string(data)))
}

func TestBuild_Pyproject(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	os.WriteFile(filepath.Join(src, "pyproject.toml"), []byte("[project]\nname=\"a\""), 0o644)

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	args := pipArgs(t, record)
	if len(args) == 0 {
		t.Fatal("pip was not called")
	}
	if !contains(args, src) {
		t.Errorf("expected pip args to include source dir %q, got %v", src, args)
	}
	if containsStr(args, "-r") {
		t.Errorf("pyproject path must not use -r flag, got %v", args)
	}
}

func TestBuild_SetupPy(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	os.WriteFile(filepath.Join(src, "setup.py"), []byte("from setuptools import setup\nsetup()"), 0o644)

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	args := pipArgs(t, record)
	if len(args) == 0 {
		t.Fatal("pip was not called")
	}
	if !contains(args, src) {
		t.Errorf("expected pip args to include source dir %q, got %v", src, args)
	}
}

func TestBuild_RequirementsTxt(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	reqFile := filepath.Join(src, "requirements.txt")
	os.WriteFile(reqFile, []byte("requests==2.32.3\n"), 0o644)

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	args := pipArgs(t, record)
	if !containsStr(args, "-r") {
		t.Errorf("requirements.txt path must use -r flag, got %v", args)
	}
	if !contains(args, reqFile) {
		t.Errorf("expected pip args to include %q, got %v", reqFile, args)
	}
}

func TestBuild_NoDeps(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	// No dep file at all.

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	if args := pipArgs(t, record); len(args) > 0 {
		t.Errorf("pip must not be called for no-deps project, got %v", args)
	}
}

func TestBuild_EmptyRequirementsIsNoDeps(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	// requirements.txt with only blank lines and comments.
	os.WriteFile(filepath.Join(src, "requirements.txt"), []byte("# no deps\n\n# yet\n"), 0o644)

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	if args := pipArgs(t, record); len(args) > 0 {
		t.Errorf("empty requirements.txt must not invoke pip, got %v", args)
	}
}

func TestBuild_WhlCachePreferred(t *testing.T) {
	tmp := t.TempDir()
	record := filepath.Join(tmp, "pip.log")
	pip := makeFakePip(t, record)
	t.Setenv("PIP", pip)

	src := filepath.Join(tmp, "src")
	os.MkdirAll(src, 0o755)
	// Both pyproject.toml and a deps/ wheel exist — wheel wins.
	os.WriteFile(filepath.Join(src, "pyproject.toml"), []byte("[project]\nname=\"a\""), 0o644)
	depsDir := filepath.Join(src, "deps")
	os.MkdirAll(depsDir, 0o755)
	whl := filepath.Join(depsDir, "mypkg-1.0-py3-none-any.whl")
	os.WriteFile(whl, []byte("fake"), 0o644)

	lib := filepath.Join(tmp, "lib")
	os.MkdirAll(lib, 0o755)

	if err := installPythonDeps(context.Background(), src, lib); err != nil {
		t.Fatalf("installPythonDeps: %v", err)
	}

	args := pipArgs(t, record)
	if !contains(args, whl) {
		t.Errorf("whl cache must be preferred; expected %q in args %v", whl, args)
	}
	if contains(args, "pyproject.toml") {
		t.Errorf("pyproject.toml must not be used when whl cache exists, got %v", args)
	}
}

func TestFindPipBinary_RespectsPIPEnvVar(t *testing.T) {
	t.Setenv("PIP", "/custom/pip")
	pip, err := findPipBinary()
	if err != nil {
		t.Fatalf("findPipBinary: %v", err)
	}
	if len(pip) != 1 || pip[0] != "/custom/pip" {
		t.Errorf("expected [\"/custom/pip\"], got %v", pip)
	}
}

func contains(slice []string, s string) bool {
	for _, v := range slice {
		if v == s {
			return true
		}
	}
	return false
}

func containsStr(slice []string, s string) bool { return contains(slice, s) }
