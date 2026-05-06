// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"

	"github.com/agentspan-ai/agentspan/cli/client"
)

// Artifact is a locally built agent bundle. Path is a developer-machine path; it stays
// inside the CLI process and is never sent to Conductor or any server-side component.
type Artifact struct {
	Path        string
	FileName    string
	ContentType string
	SizeBytes   int64
}

// BundleBuilder packages an agent source directory into a deployable Artifact written
// under outputDir. Implementations perform no network I/O — build is a local-only step.
type BundleBuilder interface {
	Build(ctx context.Context, sourceDir, outputDir string) (Artifact, error)
}

// WorkflowClient starts a Conductor workflow and waits for it to reach a terminal state.
type WorkflowClient interface {
	StartWorkflow(ctx context.Context, name string, version int, input map[string]any) (string, error)
	WaitForWorkflow(ctx context.Context, workflowID string, progress func(string)) (*client.WorkflowStatus, error)
}

// TaskClient polls for and reports on the tasks an ephemeral CLI worker handles.
type TaskClient interface {
	PollTask(ctx context.Context, taskType, workerID string) (*client.Task, error)
	UpdateTask(ctx context.Context, result client.TaskResult) error
}

// FileClient uploads a local artifact's bytes to Conductor file storage.
type FileClient interface {
	CreateFile(ctx context.Context, workflowID, taskID, fileName, contentType string) (*client.FileHandle, error)
	PutFile(ctx context.Context, uploadURL string, content []byte) error
	ConfirmUpload(ctx context.Context, fileHandleID string) error
}

// DeployClient is exactly what the deploy command depends on. *client.ConductorClient
// satisfies it; the command depends on this interface, not the concrete type.
type DeployClient interface {
	WorkflowClient
	TaskClient
	FileClient
}
