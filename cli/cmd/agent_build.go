// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"crypto/rand"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const (
	buildBundleTaskType = "BUILD_BUNDLE"
	buildWorkerID       = "agentspan-cli-local-1"
)

var agentBuildCmd = &cobra.Command{
	Use:   "build",
	Short: "Package and upload agent bundle",
	Long: `Package the current directory into a deployable bundle and upload it to
Conductor. The CLI handles bundling and upload locally; the cloud metadata-worker
stores the build reference in Valkey.

Run from the project directory containing agentspan.yaml.`,
	Args: cobra.NoArgs,
	RunE: runAgentBuildCmd,
}

func init() {
	agentCmd.AddCommand(agentBuildCmd)
}

// bundleInfo holds metadata about a locally built bundle.
type bundleInfo struct {
	path        string
	fileName    string
	contentType string
	sizeBytes   int64
}

// buildBundleResult is sent from the ephemeral worker goroutine when done.
type buildBundleResult struct {
	fileHandleID string
	buildID      string
	err          error
}

func runAgentBuildCmd(cmd *cobra.Command, args []string) error {
	cfg := getConfig()

	ref := readAgentRef(".")
	if ref == nil {
		return fmt.Errorf("agentspan.yaml not found — run this command from your project directory")
	}

	abs, _ := filepath.Abs(".")
	bold := color.New(color.Bold)
	bold.Printf("Building agent: %s/%s/%s/%s\n", ref.Customer, ref.Cluster, ref.Namespace, ref.Name)
	fmt.Printf("  Conductor: %s\n\n", cfg.ConductorURL)

	// 1. Bundle locally.
	fmt.Print("  Packaging")
	bundle, cleanup, err := buildBundle(cmd.Context(), abs)
	fmt.Println()
	if err != nil {
		return fmt.Errorf("bundle agent: %w", err)
	}
	defer cleanup()
	fmt.Printf("  Bundle   : %s (%.1f MB)\n\n", bundle.fileName, float64(bundle.sizeBytes)/1e6)

	cc := client.NewConductorClient(cfg.ConductorURL)

	// 2. Start ephemeral worker goroutine.
	taskDone := make(chan buildBundleResult, 1)
	workerCtx, stopWorker := context.WithCancel(cmd.Context())
	defer stopWorker()

	go runBuildBundleWorker(workerCtx, cc, bundle, taskDone)

	// 3. Start agentspan_build v3 workflow.
	agentRefMap := map[string]string{
		"customer":  ref.Customer,
		"cluster":   ref.Cluster,
		"namespace": ref.Namespace,
		"name":      ref.Name,
	}
	workflowID, err := cc.StartWorkflow(cmd.Context(), "agentspan_build", 3, map[string]any{
		"bundle_path": bundle.path,
		"agent_ref":   agentRefMap,
	})
	if err != nil {
		return fmt.Errorf("start build workflow: %w", err)
	}
	fmt.Printf("  Workflow : %s\n", workflowID)
	fmt.Print("  Uploading")

	// 4. Wait for the ephemeral worker to complete BUILD_BUNDLE.
	result := <-taskDone
	fmt.Println()
	if result.err != nil {
		return fmt.Errorf("build bundle failed: %w", result.err)
	}
	stopWorker()

	fmt.Println()
	color.New(color.FgGreen, color.Bold).Println("  Build complete.")
	fmt.Printf("  Artifact : %s\n", result.fileHandleID)
	fmt.Printf("  Build ID : %s\n", result.buildID)
	fmt.Println()
	fmt.Println("Next: agentspan agent deploy")
	return nil
}

// runBuildBundleWorker polls for BUILD_BUNDLE tasks and handles the file upload.
// It sends the result on done and exits when ctx is cancelled.
func runBuildBundleWorker(ctx context.Context, cc *client.ConductorClient, bundle *bundleInfo, done chan<- buildBundleResult) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		task, err := cc.PollTask(ctx, buildBundleTaskType, buildWorkerID)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
				continue
			}
		}
		if task == nil {
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
				continue
			}
		}

		result, err := handleBuildBundleTask(ctx, cc, task, bundle)
		if err != nil {
			_ = cc.UpdateTask(ctx, client.TaskResult{
				TaskID:                task.TaskID,
				WorkflowInstanceID:    task.WorkflowInstanceID,
				Status:                "FAILED",
				ReasonForIncompletion: err.Error(),
			})
			done <- buildBundleResult{err: err}
			return
		}

		_ = cc.UpdateTask(ctx, client.TaskResult{
			TaskID:             task.TaskID,
			WorkflowInstanceID: task.WorkflowInstanceID,
			Status:             "COMPLETED",
			OutputData: map[string]any{
				"file_handle_id": result.fileHandleID,
				"build_id":       result.buildID,
			},
		})
		done <- *result
		return
	}
}

func handleBuildBundleTask(ctx context.Context, cc *client.ConductorClient, task *client.Task, bundle *bundleInfo) (*buildBundleResult, error) {
	content, err := os.ReadFile(bundle.path)
	if err != nil {
		return nil, fmt.Errorf("read bundle: %w", err)
	}

	buildID := newUUID()

	handle, err := cc.CreateFile(ctx, task.WorkflowInstanceID, task.TaskID, bundle.fileName, bundle.contentType)
	if err != nil {
		return nil, fmt.Errorf("create file record: %w", err)
	}

	if err := cc.PutFile(ctx, handle.UploadURL, content); err != nil {
		return nil, fmt.Errorf("upload bundle: %w", err)
	}

	if err := cc.ConfirmUpload(ctx, handle.FileHandleID); err != nil {
		return nil, fmt.Errorf("confirm upload: %w", err)
	}

	fmt.Print(".")
	return &buildBundleResult{fileHandleID: handle.FileHandleID, buildID: buildID}, nil
}

// buildBundle packages the agent source into a tar.gz and returns a bundleInfo.
// The caller is responsible for calling the returned cleanup function.
func buildBundle(ctx context.Context, sourceDir string) (*bundleInfo, func(), error) {
	tmpDir, err := os.MkdirTemp("", "agentspan-build-*")
	if err != nil {
		return nil, nil, fmt.Errorf("create temp dir: %w", err)
	}
	cleanup := func() { os.RemoveAll(tmpDir) }

	libDir := filepath.Join(tmpDir, "lib")
	if err := os.MkdirAll(libDir, 0o755); err != nil {
		cleanup()
		return nil, nil, fmt.Errorf("create lib dir: %w", err)
	}

	// Install dependencies using uv.
	uv, err := findUVBinary()
	if err != nil {
		cleanup()
		return nil, nil, err
	}

	depsDir := filepath.Join(sourceDir, "deps")
	if info, err := os.Stat(depsDir); err == nil && info.IsDir() {
		matches, _ := filepath.Glob(filepath.Join(depsDir, "*.whl"))
		if len(matches) > 0 {
			args := append([]string{"pip", "install", "--target", libDir, "--quiet"}, matches...)
			if err := runBuildCommand(ctx, uv, args...); err != nil {
				cleanup()
				return nil, nil, fmt.Errorf("uv pip install local deps: %w", err)
			}
		}
	} else {
		if err := runBuildCommand(ctx, uv, "pip", "install", sourceDir, "--target", libDir, "--quiet"); err != nil {
			cleanup()
			return nil, nil, fmt.Errorf("uv pip install: %w", err)
		}
	}

	// Create tar.gz.
	bundlePath := filepath.Join(tmpDir, "agent-bundle.tar.gz")
	size, err := createBundle(sourceDir, libDir, bundlePath)
	if err != nil {
		cleanup()
		return nil, nil, fmt.Errorf("create bundle: %w", err)
	}

	return &bundleInfo{
		path:        bundlePath,
		fileName:    "agent-bundle.tar.gz",
		contentType: "application/gzip",
		sizeBytes:   size,
	}, cleanup, nil
}

// createBundle builds a tar.gz from lib/ (dependencies) and the source files.
// Returns the compressed size in bytes.
func createBundle(sourceDir, libDir, outputPath string) (int64, error) {
	f, err := os.Create(outputPath)
	if err != nil {
		return 0, fmt.Errorf("create bundle file: %w", err)
	}
	defer f.Close()

	gw := gzip.NewWriter(f)
	tw := tar.NewWriter(gw)

	// Add lib/ — installed dependencies.
	if err := filepath.WalkDir(libDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		rel, _ := filepath.Rel(libDir, path)
		return addTarFile(tw, path, filepath.Join("lib", rel))
	}); err != nil {
		return 0, fmt.Errorf("walk lib dir: %w", err)
	}

	// Add source files.
	skipDirs := map[string]bool{".git": true, "__pycache__": true, ".venv": true, "node_modules": true, "lib": true}
	skipExts := map[string]bool{".pyc": true, ".pyo": true}
	if err := filepath.WalkDir(sourceDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() && skipDirs[d.Name()] {
			return filepath.SkipDir
		}
		if d.IsDir() {
			return nil
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

func runBuildCommand(ctx context.Context, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func findUVBinary() (string, error) {
	if p, err := exec.LookPath("uv"); err == nil {
		return p, nil
	}
	home, _ := os.UserHomeDir()
	for _, c := range []string{
		filepath.Join(home, ".local", "bin", "uv"),
		"/usr/local/bin/uv",
	} {
		if _, err := os.Stat(c); err == nil {
			return c, nil
		}
	}
	return "", fmt.Errorf("uv not found — install it from https://github.com/astral-sh/uv")
}

func newUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
