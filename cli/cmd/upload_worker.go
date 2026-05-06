// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/agentspan-ai/agentspan/cli/client"
)

const (
	uploadBundleTaskType = "UPLOAD_BUNDLE"
	cliUploadWorkerID    = "agentspan-cli-deploy-1"
	uploadPollInterval   = 2 * time.Second
)

// uploadResult is sent once when the UPLOAD_BUNDLE task is done (or fails).
type uploadResult struct {
	fileHandleID string
	err          error
}

// bundleUploadWorker is an ephemeral, CLI-side worker that handles the single
// UPLOAD_BUNDLE task of a deploy workflow: it uploads the locally-built artifact's
// bytes to Conductor file storage. The artifact path lives only here, in the CLI
// process — it never enters Conductor (satisfies "production code never uses local
// file paths").
type bundleUploadWorker struct {
	client      DeployClient
	path        string
	fileName    string
	contentType string
	sizeBytes   int64
}

func newBundleUploadWorker(c DeployClient, path, fileName, contentType string, sizeBytes int64) *bundleUploadWorker {
	return &bundleUploadWorker{client: c, path: path, fileName: fileName, contentType: contentType, sizeBytes: sizeBytes}
}

// Run polls for the UPLOAD_BUNDLE task, uploads the artifact, completes the task, then
// exits. It sends the outcome on done exactly once. Returns early on context cancel.
func (w *bundleUploadWorker) Run(ctx context.Context, done chan<- uploadResult) {
	for {
		if ctx.Err() != nil {
			return
		}

		task, err := w.client.PollTask(ctx, uploadBundleTaskType, cliUploadWorkerID)
		if err != nil || task == nil {
			select {
			case <-ctx.Done():
				return
			case <-time.After(uploadPollInterval):
				continue
			}
		}

		fileHandleID, err := w.upload(ctx, task)
		if err != nil {
			_ = w.client.UpdateTask(ctx, client.TaskResult{
				TaskID:                task.TaskID,
				WorkflowInstanceID:    task.WorkflowInstanceID,
				Status:                "FAILED",
				ReasonForIncompletion: err.Error(),
			})
			done <- uploadResult{err: err}
			return
		}

		_ = w.client.UpdateTask(ctx, client.TaskResult{
			TaskID:             task.TaskID,
			WorkflowInstanceID: task.WorkflowInstanceID,
			Status:             "COMPLETED",
			OutputData: map[string]any{
				"file_handle_id":    fileHandleID,
				"bundle_name":       w.fileName,
				"bundle_size_bytes": w.sizeBytes,
			},
		})
		done <- uploadResult{fileHandleID: fileHandleID}
		return
	}
}

// upload reads the artifact bytes from the local path and pushes them to file storage,
// scoped to the polling task's workflow so the downstream DEPLOY_AGENT task (same
// workflow family) can download it.
func (w *bundleUploadWorker) upload(ctx context.Context, task *client.Task) (string, error) {
	content, err := os.ReadFile(w.path)
	if err != nil {
		return "", fmt.Errorf("read artifact: %w", err)
	}
	handle, err := w.client.CreateFile(ctx, task.WorkflowInstanceID, task.TaskID, w.fileName, w.contentType)
	if err != nil {
		return "", fmt.Errorf("create file record: %w", err)
	}
	if err := w.client.PutFile(ctx, handle.UploadURL, content); err != nil {
		return "", fmt.Errorf("upload bundle: %w", err)
	}
	if err := w.client.ConfirmUpload(ctx, handle.FileHandleID); err != nil {
		return "", fmt.Errorf("confirm upload: %w", err)
	}
	return handle.FileHandleID, nil
}
