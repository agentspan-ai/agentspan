// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	conductorPollInterval = 2 * time.Second
	conductorPollTimeout  = 300 * time.Second
)

// ConductorClient talks to the Conductor Control Plane API.
type ConductorClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewConductorClient creates a client targeting the given Conductor base URL.
func NewConductorClient(conductorURL string) *ConductorClient {
	return &ConductorClient{
		baseURL:    strings.TrimRight(conductorURL, "/"),
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// WorkflowStatus holds the relevant fields from a Conductor workflow response.
type WorkflowStatus struct {
	WorkflowID string         `json:"workflowId"`
	Status     string         `json:"status"`
	Output     map[string]any `json:"output"`
	FailedRef  []string       `json:"failedReferenceTaskNames"`
}

// StartWorkflow triggers a named Conductor workflow and returns the workflow ID.
func (c *ConductorClient) StartWorkflow(ctx context.Context, name string, version int, input map[string]any) (string, error) {
	body := map[string]any{
		"name":    name,
		"version": version,
		"input":   input,
	}

	data, err := json.Marshal(body)
	if err != nil {
		return "", fmt.Errorf("marshal workflow start request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/workflow", bytes.NewReader(data))
	if err != nil {
		return "", fmt.Errorf("build start workflow request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("start workflow %s: %w", name, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("start workflow %s: HTTP %d: %s", name, resp.StatusCode, b)
	}

	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read workflow ID: %w", err)
	}
	// Conductor returns the workflow ID as a bare quoted string.
	workflowID := strings.Trim(strings.TrimSpace(string(b)), `"`)
	return workflowID, nil
}

// GetWorkflow fetches the current state of a workflow.
func (c *ConductorClient) GetWorkflow(ctx context.Context, workflowID string) (*WorkflowStatus, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/workflow/"+workflowID, nil)
	if err != nil {
		return nil, fmt.Errorf("build get workflow request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("get workflow %s: %w", workflowID, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("get workflow %s: HTTP %d: %s", workflowID, resp.StatusCode, b)
	}

	var status WorkflowStatus
	if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
		return nil, fmt.Errorf("decode workflow status: %w", err)
	}
	return &status, nil
}

// WaitForWorkflow polls until the workflow reaches a terminal state or the
// context is cancelled. Calls progressFn with each polled status (may be nil).
func (c *ConductorClient) WaitForWorkflow(ctx context.Context, workflowID string, progressFn func(string)) (*WorkflowStatus, error) {
	deadline := time.Now().Add(conductorPollTimeout)
	for {
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("workflow %s did not complete within %s", workflowID, conductorPollTimeout)
		}

		status, err := c.GetWorkflow(ctx, workflowID)
		if err != nil {
			return nil, err
		}

		if progressFn != nil {
			progressFn(status.Status)
		}

		switch status.Status {
		case "COMPLETED":
			return status, nil
		case "FAILED", "TIMED_OUT", "TERMINATED":
			return nil, fmt.Errorf("workflow %s ended with status %s", workflowID, status.Status)
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(conductorPollInterval):
		}
	}
}

// Task represents a polled Conductor task.
type Task struct {
	TaskID             string         `json:"taskId"`
	TaskType           string         `json:"taskType"`
	WorkflowInstanceID string         `json:"workflowInstanceId"`
	InputData          map[string]any `json:"inputData"`
}

// TaskResult is sent to Conductor to report task completion or failure.
type TaskResult struct {
	TaskID                string         `json:"taskId"`
	WorkflowInstanceID    string         `json:"workflowInstanceId"`
	Status                string         `json:"status"`
	OutputData            map[string]any `json:"outputData,omitempty"`
	ReasonForIncompletion string         `json:"reasonForIncompletion,omitempty"`
}

// FileHandle is returned by POST /api/files when creating a file artifact.
type FileHandle struct {
	FileHandleID string `json:"fileHandleId"`
	UploadURL    string `json:"uploadUrl"`
}

// PollTask polls for a task of the given type. Returns (nil, nil) when no task is available.
func (c *ConductorClient) PollTask(ctx context.Context, taskType, workerID string) (*Task, error) {
	endpoint := c.baseURL + "/tasks/poll/" + taskType + "?workerid=" + workerID
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("build poll request: %w", err)
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("poll task %s: %w", taskType, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("poll task %s: status %d", taskType, resp.StatusCode)
	}
	var task Task
	if err := json.NewDecoder(resp.Body).Decode(&task); err != nil {
		return nil, fmt.Errorf("decode task: %w", err)
	}
	return &task, nil
}

// UpdateTask sends a task result to Conductor (COMPLETED or FAILED).
func (c *ConductorClient) UpdateTask(ctx context.Context, result TaskResult) error {
	data, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("marshal task result: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/tasks", bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("build update task request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("update task: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("update task: status %d: %s", resp.StatusCode, b)
	}
	return nil
}

// CreateFile registers a new file artifact with Conductor and returns the upload URL.
func (c *ConductorClient) CreateFile(ctx context.Context, workflowID, taskID, fileName, contentType string) (*FileHandle, error) {
	body := map[string]string{
		"workflowId":  workflowID,
		"taskId":      taskID,
		"fileName":    fileName,
		"contentType": contentType,
	}
	data, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal create file: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/files", bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("build create file request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("create file: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("create file: status %d: %s", resp.StatusCode, b)
	}
	var handle FileHandle
	if err := json.NewDecoder(resp.Body).Decode(&handle); err != nil {
		return nil, fmt.Errorf("decode file handle: %w", err)
	}
	return &handle, nil
}

// PutFile uploads raw bytes to the given URL. Handles file:// (local dev) and http(s):// (S3).
func (c *ConductorClient) PutFile(ctx context.Context, uploadURL string, content []byte) error {
	if strings.HasPrefix(uploadURL, "file://") {
		path := strings.TrimPrefix(uploadURL, "file://")
		dir := path[:lastSlash(path)]
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("create upload dir: %w", err)
		}
		return os.WriteFile(path, content, 0o644)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, uploadURL, bytes.NewReader(content))
	if err != nil {
		return fmt.Errorf("build PUT request: %w", err)
	}
	req.ContentLength = int64(len(content))
	upload := &http.Client{Timeout: 120 * time.Second}
	resp, err := upload.Do(req)
	if err != nil {
		return fmt.Errorf("upload file: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("upload file: status %d", resp.StatusCode)
	}
	return nil
}

func lastSlash(s string) int {
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == '/' {
			return i
		}
	}
	return 0
}

// ConfirmUpload notifies Conductor that the file upload is complete.
func (c *ConductorClient) ConfirmUpload(ctx context.Context, fileHandleID string) error {
	fileID := strings.TrimPrefix(fileHandleID, "conductor://file/")
	endpoint := c.baseURL + "/files/" + fileID + "/upload-complete"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, nil)
	if err != nil {
		return fmt.Errorf("build confirm upload request: %w", err)
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("confirm upload: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("confirm upload: status %d: %s", resp.StatusCode, b)
	}
	return nil
}
