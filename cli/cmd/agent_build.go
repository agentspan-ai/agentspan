// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"archive/tar"
	"bufio"
	"compress/gzip"
	"context"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const (
	artifactFileName    = "agent-bundle.tar.gz"
	artifactContentType = "application/gzip"
	defaultOutputSubdir = "dist"
	flagOutput          = "output"
)

var agentBuildCmd = &cobra.Command{
	Use:   "build",
	Short: "Package the agent into a local deployable bundle",
	Long: `Package the current directory into a deployable bundle written to ./dist
(override with --output). Build is fully local — it does not upload anything;
run "agentspan agent deploy" to upload and provision.

Run from the project directory containing agentspan.yaml.`,
	Args: cobra.NoArgs,
	RunE: runAgentBuildCmd,
}

func init() {
	agentBuildCmd.Flags().String(flagOutput, defaultOutputSubdir, "Directory to write the bundle into")
	agentCmd.AddCommand(agentBuildCmd)
}

// agentResourceSpec mirrors spec.resources in agentspan.yaml.
type agentResourceSpec struct {
	CPU     string `yaml:"cpu,omitempty"`
	CPUTime string `yaml:"cpu_time,omitempty"`
	Memory  string `yaml:"memory,omitempty"`
	Storage string `yaml:"storage,omitempty"`
}

// agentScalingSpec mirrors spec.scaling in agentspan.yaml.
type agentScalingSpec struct {
	Replicas int `yaml:"replicas,omitempty"`
}

// agentspanFullSpec is the complete agentspan.yaml shape needed for bundling.
type agentspanFullSpec struct {
	Metadata struct {
		Customer  string `yaml:"customer"`
		Cluster   string `yaml:"cluster"`
		Namespace string `yaml:"namespace"`
		Name      string `yaml:"name"`
	} `yaml:"metadata"`
	Spec struct {
		Runtime    string             `yaml:"runtime"`
		Entrypoint string             `yaml:"entrypoint"`
		Install    string             `yaml:"install,omitempty"`
		Env        []string           `yaml:"env,omitempty"`
		Egress     []string           `yaml:"egress,omitempty"`
		Resources  *agentResourceSpec `yaml:"resources,omitempty"`
		Scaling    *agentScalingSpec  `yaml:"scaling,omitempty"`
	} `yaml:"spec"`
}

// fcManifest is the manifest.yaml embedded in the bundle for the Firecracker runner.
type fcManifest struct {
	Runtime    string             `yaml:"runtime"`
	Entrypoint string             `yaml:"entrypoint"`
	Install    string             `yaml:"install,omitempty"`
	Env        []string           `yaml:"env,omitempty"`
	Egress     []string           `yaml:"egress,omitempty"`
	Resources  *agentResourceSpec `yaml:"resources,omitempty"`
	Scaling    *agentScalingSpec  `yaml:"scaling,omitempty"`
}

func runAgentBuildCmd(cmd *cobra.Command, _ []string) error {
	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found — run this command from your project directory")
	}

	outputDir, _ := cmd.Flags().GetString(flagOutput)
	if outputDir == "" {
		outputDir = defaultOutputSubdir
	}

	color.New(color.Bold).Printf("Building agent: %s/%s/%s/%s\n", ref.Customer, ref.Cluster, ref.Namespace, ref.Name)

	fmt.Print("  Packaging")
	var builder BundleBuilder = fcBundleBuilder{}
	artifact, err := builder.Build(cmd.Context(), ".", outputDir)
	fmt.Println()
	if err != nil {
		return fmt.Errorf("build agent: %w", err)
	}

	fmt.Printf("  Artifact : %s (%.1f MB)\n\n", artifact.Path, float64(artifact.SizeBytes)/1e6)
	fmt.Println("Next: agentspan agent deploy")
	return nil
}

// fcBundleBuilder packages a Python agent into a Firecracker-ready tar.gz bundle.
type fcBundleBuilder struct{}

// Build implements BundleBuilder. It writes <outputDir>/agent-bundle.tar.gz with no
// network I/O. Python deps are staged in a temp dir (cleaned up), so outputDir holds
// only the final artifact.
func (fcBundleBuilder) Build(ctx context.Context, sourceDir, outputDir string) (Artifact, error) {
	data, err := os.ReadFile(filepath.Join(sourceDir, "agentspan.yaml"))
	if err != nil {
		return Artifact{}, fmt.Errorf("read agentspan.yaml: %w", err)
	}
	var spec agentspanFullSpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return Artifact{}, fmt.Errorf("parse agentspan.yaml: %w", err)
	}
	if spec.Spec.Runtime == "" {
		return Artifact{}, fmt.Errorf("agentspan.yaml: spec.runtime is required")
	}
	if spec.Spec.Entrypoint == "" {
		return Artifact{}, fmt.Errorf("agentspan.yaml: spec.entrypoint is required")
	}

	manifest := &fcManifest{
		Runtime:    spec.Spec.Runtime,
		Entrypoint: spec.Spec.Entrypoint,
		Install:    spec.Spec.Install,
		Env:        spec.Spec.Env,
		Egress:     spec.Spec.Egress,
		Resources:  spec.Spec.Resources,
		Scaling:    spec.Spec.Scaling,
	}

	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return Artifact{}, fmt.Errorf("create output dir: %w", err)
	}

	// Stage pip deps in a temp dir so the output dir holds only the final artifact.
	stagingDir, err := os.MkdirTemp("", "agentspan-build-*")
	if err != nil {
		return Artifact{}, fmt.Errorf("create staging dir: %w", err)
	}
	defer os.RemoveAll(stagingDir)

	libDir := filepath.Join(stagingDir, "lib")
	if err := os.MkdirAll(libDir, 0o755); err != nil {
		return Artifact{}, fmt.Errorf("create lib dir: %w", err)
	}
	if err := installPythonDeps(ctx, sourceDir, libDir); err != nil {
		return Artifact{}, err
	}

	bundlePath := filepath.Join(outputDir, artifactFileName)
	size, err := createBundle(sourceDir, libDir, bundlePath, manifest)
	if err != nil {
		return Artifact{}, fmt.Errorf("create bundle: %w", err)
	}

	return Artifact{
		Path:        bundlePath,
		FileName:    artifactFileName,
		ContentType: artifactContentType,
		SizeBytes:   size,
	}, nil
}

// createBundle builds a tar.gz with manifest.yaml + lib/ + source files.
// Returns the compressed size in bytes.
func createBundle(sourceDir, libDir, outputPath string, manifest *fcManifest) (int64, error) {
	f, err := os.Create(outputPath)
	if err != nil {
		return 0, fmt.Errorf("create bundle file: %w", err)
	}
	defer f.Close()

	gw := gzip.NewWriter(f)
	tw := tar.NewWriter(gw)

	// manifest.yaml — required by the Firecracker runner.
	manifestBytes, err := yaml.Marshal(manifest)
	if err != nil {
		return 0, fmt.Errorf("marshal manifest.yaml: %w", err)
	}
	if err := tw.WriteHeader(&tar.Header{
		Name: "manifest.yaml",
		Mode: 0o644,
		Size: int64(len(manifestBytes)),
	}); err != nil {
		return 0, fmt.Errorf("tar header manifest.yaml: %w", err)
	}
	if _, err := tw.Write(manifestBytes); err != nil {
		return 0, fmt.Errorf("write manifest.yaml: %w", err)
	}

	// lib/ — installed dependencies (staged outside sourceDir).
	if err := filepath.WalkDir(libDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		rel, _ := filepath.Rel(libDir, path)
		return addTarFile(tw, path, filepath.Join("lib", rel))
	}); err != nil {
		return 0, fmt.Errorf("walk lib dir: %w", err)
	}

	// Source files. Skip the output dir / artifact so we never tar the bundle into itself.
	outputPathAbs, _ := filepath.Abs(outputPath)
	outputDirAbs, _ := filepath.Abs(filepath.Dir(outputPath))
	sourceDirAbs, _ := filepath.Abs(sourceDir)
	skipDirs := map[string]bool{".git": true, "__pycache__": true, ".venv": true, "node_modules": true, "lib": true}
	skipExts := map[string]bool{".pyc": true, ".pyo": true}
	if err := filepath.WalkDir(sourceDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		abs, _ := filepath.Abs(path)
		if d.IsDir() {
			if skipDirs[d.Name()] {
				return filepath.SkipDir
			}
			if abs == outputDirAbs && abs != sourceDirAbs {
				return filepath.SkipDir // don't descend into the output dir
			}
			return nil
		}
		if abs == outputPathAbs {
			return nil // never include the bundle currently being written
		}
		if skipExts[strings.ToLower(filepath.Ext(d.Name()))] {
			return nil
		}
		rel, _ := filepath.Rel(sourceDir, path)
		return addTarFile(tw, path, rel)
	}); err != nil {
		return 0, fmt.Errorf("walk source dir: %w", err)
	}

	if err := tw.Close(); err != nil {
		return 0, fmt.Errorf("close tar: %w", err)
	}
	if err := gw.Close(); err != nil {
		return 0, fmt.Errorf("close gzip: %w", err)
	}
	if err := f.Close(); err != nil {
		return 0, fmt.Errorf("close bundle file: %w", err)
	}

	fi, err := os.Stat(outputPath)
	if err != nil {
		return 0, err
	}
	return fi.Size(), nil
}

func addTarFile(tw *tar.Writer, diskPath, tarPath string) error {
	fi, err := os.Stat(diskPath)
	if err != nil {
		return fmt.Errorf("stat %s: %w", diskPath, err)
	}
	if err := tw.WriteHeader(&tar.Header{
		Name:    tarPath,
		Size:    fi.Size(),
		Mode:    int64(fi.Mode()),
		ModTime: fi.ModTime(),
	}); err != nil {
		return fmt.Errorf("tar header %s: %w", tarPath, err)
	}
	data, err := os.ReadFile(diskPath)
	if err != nil {
		return fmt.Errorf("read %s: %w", diskPath, err)
	}
	_, err = tw.Write(data)
	return err
}

// installPythonDeps installs Python dependencies into libDir.
// Priority: deps/*.whl → pyproject.toml → setup.py → requirements.txt → no-deps.
func installPythonDeps(ctx context.Context, sourceDir, libDir string) error {
	pip, err := findPipBinary()
	if err != nil {
		return err
	}

	// Pre-built wheels take precedence over everything else.
	depsDir := filepath.Join(sourceDir, "deps")
	if info, statErr := os.Stat(depsDir); statErr == nil && info.IsDir() {
		matches, _ := filepath.Glob(filepath.Join(depsDir, "*.whl"))
		if len(matches) > 0 {
			return runPipCommand(ctx, pip, append([]string{"install", "--target", libDir, "--quiet"}, matches...)...)
		}
	}

	if pathExists(filepath.Join(sourceDir, "pyproject.toml")) {
		return runPipCommand(ctx, pip, "install", "--target", libDir, "--quiet", sourceDir)
	}
	if pathExists(filepath.Join(sourceDir, "setup.py")) {
		return runPipCommand(ctx, pip, "install", "--target", libDir, "--quiet", sourceDir)
	}
	req := filepath.Join(sourceDir, "requirements.txt")
	if pathExists(req) && !requirementsEmpty(req) {
		return runPipCommand(ctx, pip, "install", "--target", libDir, "--quiet", "-r", req)
	}
	return nil // no-deps: lib/ stays empty
}

// findPipBinary locates a pip executable. Checks PIP env var first, then pip3,
// pip, and finally falls back to running pip as a Python module.
func findPipBinary() ([]string, error) {
	if p := os.Getenv("PIP"); p != "" {
		return []string{p}, nil
	}
	for _, name := range []string{"pip3", "pip"} {
		if p, err := exec.LookPath(name); err == nil {
			return []string{p}, nil
		}
	}
	for _, name := range []string{"python3", "python"} {
		if p, err := exec.LookPath(name); err == nil {
			return []string{p, "-m", "pip"}, nil
		}
	}
	return nil, fmt.Errorf("pip not found — install Python (pip ships with it) or set the PIP environment variable")
}

func runPipCommand(ctx context.Context, pip []string, args ...string) error {
	cmd := exec.CommandContext(ctx, pip[0], append(pip[1:], args...)...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// requirementsEmpty reports whether requirements.txt has no installable entries
// (only blank lines and # comments).
func requirementsEmpty(path string) bool {
	f, err := os.Open(path)
	if err != nil {
		return true
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" && !strings.HasPrefix(line, "#") {
			return false
		}
	}
	return true
}
