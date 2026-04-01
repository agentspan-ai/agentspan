// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package client

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/config"
)

type Client struct {
	baseURL    string
	httpClient *http.Client
	authKey    string
	authSecret string
	apiKey     string
}

func New(cfg *config.Config) *Client {
	return &Client{
		baseURL:    strings.TrimRight(cfg.ServerURL, "/"),
		httpClient: &http.Client{Timeout: 30 * time.Second},
		authKey:    cfg.AuthKey,
		authSecret: cfg.AuthSecret,
		apiKey:     cfg.APIKey,
	}
}

func (c *Client) doRequest(method, path string, body interface{}) (*http.Response, error) {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("marshal request: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequest(method, c.baseURL+path, bodyReader)
	if err != nil {
		return nil, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	} else {
		if c.authKey != "" {
			req.Header.Set("X-Auth-Key", c.authKey)
		}
		if c.authSecret != "" {
			req.Header.Set("X-Auth-Secret", c.authSecret)
		}
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	if resp.StatusCode >= 400 {
		defer resp.Body.Close()
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(bodyBytes))
	}
	return resp, nil
}

// HealthCheck pings the server
func (c *Client) HealthCheck() error {
	resp, err := c.doRequest("GET", "/health", nil)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// StartRequest is the payload for starting an agent
type StartRequest struct {
	AgentConfig map[string]interface{} `json:"agentConfig,omitempty"`
	Prompt      string                 `json:"prompt"`
	SessionID   string                 `json:"sessionId,omitempty"`
}

// StartResponse from the runtime
type StartResponse struct {
	ExecutionID string `json:"executionId"`
	AgentName   string `json:"agentName"`
}

// Start compiles, registers, and starts an agent execution
func (c *Client) Start(req *StartRequest) (*StartResponse, error) {
	resp, err := c.doRequest("POST", "/api/agent/start", req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result StartResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &result, nil
}

// StartFramework starts a framework agent (skill, openai, etc.) with a raw payload.
// Framework agents use top-level "framework" + "rawConfig" instead of "agentConfig".
func (c *Client) StartFramework(payload map[string]interface{}) (*StartResponse, error) {
	resp, err := c.doRequest("POST", "/api/agent/start", payload)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result StartResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &result, nil
}

// PollTask polls for a task of the given type. Returns nil if no task available.
func (c *Client) PollTask(taskType string) (map[string]interface{}, error) {
	resp, err := c.doRequest("GET", "/api/tasks/poll/"+url.PathEscape(taskType), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNoContent || resp.StatusCode == http.StatusNotFound {
		return nil, nil // no task available
	}
	var task map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&task); err != nil {
		return nil, nil // empty body
	}
	return task, nil
}

// UpdateTask reports the result of a completed task.
func (c *Client) UpdateTask(result map[string]interface{}) error {
	resp, err := c.doRequest("POST", "/api/tasks", result)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

// Compile compiles an agent config to an execution plan
func (c *Client) Compile(agentConfig map[string]interface{}) (map[string]interface{}, error) {
	body := map[string]interface{}{"agentConfig": agentConfig}
	resp, err := c.doRequest("POST", "/api/agent/compile", body)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}

// AgentSummary represents a registered agent
type AgentSummary struct {
	Name        string   `json:"name"`
	Version     int      `json:"version"`
	Type        string   `json:"type"`
	Tags        []string `json:"tags"`
	CreateTime  *int64   `json:"createTime"`
	UpdateTime  *int64   `json:"updateTime"`
	Description string   `json:"description"`
	Checksum    string   `json:"checksum"`
}

// ListAgents returns all registered agents
func (c *Client) ListAgents() ([]AgentSummary, error) {
	resp, err := c.doRequest("GET", "/api/agent/list", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result []AgentSummary
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}

// GetAgent returns the definition for a named agent
func (c *Client) GetAgent(name string, version *int) (map[string]interface{}, error) {
	path := "/api/agent/" + url.PathEscape(name)
	if version != nil {
		path += fmt.Sprintf("?version=%d", *version)
	}
	resp, err := c.doRequest("GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}

// DeleteAgent removes an agent definition
func (c *Client) DeleteAgent(name string, version *int) error {
	path := "/api/agent/" + url.PathEscape(name)
	if version != nil {
		path += fmt.Sprintf("?version=%d", *version)
	}
	resp, err := c.doRequest("DELETE", path, nil)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// ExecutionSearchResult from the search endpoint
type ExecutionSearchResult struct {
	TotalHits int64                   `json:"totalHits"`
	Results   []AgentExecutionSummary `json:"results"`
}

// AgentExecutionSummary represents one execution in search results
type AgentExecutionSummary struct {
	ExecutionID   string `json:"executionId"`
	AgentName     string `json:"agentName"`
	Version       int    `json:"version"`
	Status        string `json:"status"`
	StartTime     string `json:"startTime"`
	EndTime       string `json:"endTime"`
	UpdateTime    string `json:"updateTime"`
	ExecutionTime int64  `json:"executionTime"`
	Input         string `json:"input"`
	Output        string `json:"output"`
	CreatedBy     string `json:"createdBy"`
}

// SearchExecutions searches agent executions with optional filters
func (c *Client) SearchExecutions(start, size int, agentName, status, freeText string) (*ExecutionSearchResult, error) {
	params := url.Values{}
	params.Set("start", fmt.Sprintf("%d", start))
	params.Set("size", fmt.Sprintf("%d", size))
	params.Set("sort", "startTime:DESC")
	if agentName != "" {
		params.Set("agentName", agentName)
	}
	if status != "" {
		params.Set("status", status)
	}
	if freeText != "" {
		params.Set("freeText", freeText)
	}
	resp, err := c.doRequest("GET", "/api/agent/executions?"+params.Encode(), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result ExecutionSearchResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &result, nil
}

// ExecutionDetail represents detailed execution status
type ExecutionDetail struct {
	ExecutionID string                 `json:"executionId"`
	AgentName   string                 `json:"agentName"`
	Version     int                    `json:"version"`
	Status      string                 `json:"status"`
	Input       map[string]interface{} `json:"input"`
	Output      map[string]interface{} `json:"output"`
	CurrentTask *CurrentTask           `json:"currentTask"`
}

type CurrentTask struct {
	TaskRefName string                 `json:"taskRefName"`
	TaskType    string                 `json:"taskType"`
	Status      string                 `json:"status"`
	InputData   map[string]interface{} `json:"inputData"`
	OutputData  map[string]interface{} `json:"outputData"`
}

// GetExecutionDetail returns detailed status for an execution
func (c *Client) GetExecutionDetail(executionId string) (*ExecutionDetail, error) {
	resp, err := c.doRequest("GET", "/api/agent/executions/"+url.PathEscape(executionId), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result ExecutionDetail
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &result, nil
}

// Status gets the execution status
func (c *Client) Status(executionID string) (map[string]interface{}, error) {
	resp, err := c.doRequest("GET", "/api/agent/"+url.PathEscape(executionID)+"/status", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}

// Respond sends a HITL response
func (c *Client) Respond(executionID string, approved bool, reason, message string) error {
	body := map[string]interface{}{
		"approved": approved,
		"reason":   reason,
		"message":  message,
	}
	resp, err := c.doRequest("POST", "/api/agent/"+url.PathEscape(executionID)+"/respond", body)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// SSEEvent represents a server-sent event
type SSEEvent struct {
	ID    string
	Event string
	Data  string
}

// Stream opens an SSE connection and sends events to the channel
func (c *Client) Stream(executionID string, lastEventID string, events chan<- SSEEvent, done chan<- error) {
	go func() {
		defer close(events)
		defer close(done)

		streamClient := &http.Client{Timeout: 0} // no timeout for SSE

		req, err := http.NewRequest("GET", c.baseURL+"/api/agent/stream/"+url.PathEscape(executionID), nil)
		if err != nil {
			done <- err
			return
		}
		req.Header.Set("Accept", "text/event-stream")
		if lastEventID != "" {
			req.Header.Set("Last-Event-ID", lastEventID)
		}
		if c.authKey != "" {
			req.Header.Set("X-Auth-Key", c.authKey)
		}

		resp, err := streamClient.Do(req)
		if err != nil {
			done <- err
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode >= 400 {
			body, _ := io.ReadAll(resp.Body)
			done <- fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
			return
		}

		scanner := bufio.NewScanner(resp.Body)
		scanner.Buffer(make([]byte, 0, 1024*1024), 1024*1024)

		var current SSEEvent
		var dataLines []string
		for scanner.Scan() {
			line := scanner.Text()

			if line == "" {
				// Empty line = end of event; join accumulated data lines per SSE spec
				if len(dataLines) > 0 {
					current.Data = strings.Join(dataLines, "\n")
				}
				if current.Data != "" || current.Event != "" {
					events <- current
					current = SSEEvent{}
					dataLines = dataLines[:0]
				}
				continue
			}

			if strings.HasPrefix(line, ":") {
				// Comment (heartbeat), skip
				continue
			}

			if strings.HasPrefix(line, "id:") {
				current.ID = sseFieldValue(line, "id:")
			} else if strings.HasPrefix(line, "event:") {
				current.Event = sseFieldValue(line, "event:")
			} else if strings.HasPrefix(line, "data:") {
				dataLines = append(dataLines, sseFieldValue(line, "data:"))
			}
		}

		done <- scanner.Err()
	}()
}

// sseFieldValue extracts the value from an SSE field line by stripping the
// prefix and, per the WHATWG SSE spec, removing exactly one leading U+0020
// space character (not all whitespace).
func sseFieldValue(line, prefix string) string {
	v := strings.TrimPrefix(line, prefix)
	v = strings.TrimPrefix(v, " ") // strip at most one leading space per spec
	return v
}

// ─── Auth API ─────────────────────────────────────────────────────────────────

// LoginRequest is the payload for POST /api/auth/login
type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// LoginResponse carries the JWT returned by the server
type LoginResponse struct {
	Token string `json:"token"`
}

// Login authenticates with the server and returns a JWT.
func (c *Client) Login(username, password string) (*LoginResponse, error) {
	resp, err := c.doRequest("POST", "/api/auth/login", &LoginRequest{
		Username: username,
		Password: password,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result LoginResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode login response: %w", err)
	}
	return &result, nil
}

// ─── Credential management API ────────────────────────────────────────────────

// CredentialMeta is the list-view for a stored credential.
type CredentialMeta struct {
	Name      string `json:"name"`
	Partial   string `json:"partial"`
	UpdatedAt string `json:"updated_at"`
}

// CredentialSetRequest is the body for POST /api/credentials.
type CredentialSetRequest struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

// BindingMeta represents one logical key → store name binding.
type BindingMeta struct {
	LogicalKey string `json:"logical_key"`
	StoreName  string `json:"store_name"`
}

// BindingSetRequest is the body for PUT /api/credentials/bindings/{key}.
type BindingSetRequest struct {
	StoreName string `json:"store_name"`
}

// ListCredentials returns all stored credential metadata.
func (c *Client) ListCredentials() ([]CredentialMeta, error) {
	resp, err := c.doRequest("GET", "/api/credentials", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result []CredentialMeta
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode credentials: %w", err)
	}
	return result, nil
}

// SetCredential stores a credential value on the server.
func (c *Client) SetCredential(name, value string) error {
	resp, err := c.doRequest("POST", "/api/credentials", &CredentialSetRequest{
		Name:  name,
		Value: value,
	})
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// DeleteCredential removes a stored credential by name.
func (c *Client) DeleteCredential(name string) error {
	resp, err := c.doRequest("DELETE", "/api/credentials/"+url.PathEscape(name), nil)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// ListBindings returns all logical key → store name bindings.
func (c *Client) ListBindings() ([]BindingMeta, error) {
	resp, err := c.doRequest("GET", "/api/credentials/bindings", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result []BindingMeta
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode bindings: %w", err)
	}
	return result, nil
}

// SetBinding sets (or updates) a logical key → store name binding.
func (c *Client) SetBinding(logicalKey, storeName string) error {
	resp, err := c.doRequest("PUT", "/api/credentials/bindings/"+url.PathEscape(logicalKey),
		&BindingSetRequest{StoreName: storeName})
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}
