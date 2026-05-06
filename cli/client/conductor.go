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
