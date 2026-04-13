package tui

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"
)

var (
	ansiCSI         = regexp.MustCompile(`\x1b\[[0-9;?]*[ -/]*[@-~]`)
	ansiOSC         = regexp.MustCompile(`\x1b\][^\a\x1b]*(?:\a|\x1b\\)`)
	trueColorEscape = regexp.MustCompile(`\x1b\[[0-9;]*[34]8;2;`)
	lightAccentFG   = regexp.MustCompile(`\x1b\[[0-9;]*32m`)
	darkAccentFG    = regexp.MustCompile(`\x1b\[[0-9;]*92m`)
)

type lockedBuffer struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (b *lockedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.Write(p)
}

func (b *lockedBuffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.Len()
}

func (b *lockedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.String()
}

func (b *lockedBuffer) SliceFrom(offset int) string {
	b.mu.Lock()
	defer b.mu.Unlock()
	data := b.b.Bytes()
	if offset < 0 {
		offset = 0
	}
	if offset > len(data) {
		offset = len(data)
	}
	return string(append([]byte(nil), data[offset:]...))
}

type ptySession struct {
	t      *testing.T
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	output *lockedBuffer

	waitCh  chan error
	mu      sync.Mutex
	exited  bool
	exitErr error
}

type runStubState struct {
	mu           sync.Mutex
	gotPrompt    string
	gotAgentName string
	startCalls   int
}

func (s *runStubState) recordStart(req startRequest) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.gotPrompt = req.Prompt
	if name, ok := req.AgentConfig["name"].(string); ok {
		s.gotAgentName = name
	}
	s.startCalls++
}

func (s *runStubState) snapshot() (startCalls int, agentName, prompt string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.startCalls, s.gotAgentName, s.gotPrompt
}

type startRequest struct {
	AgentConfig map[string]interface{} `json:"agentConfig"`
	Prompt      string                 `json:"prompt"`
	SessionID   string                 `json:"sessionId"`
}

func TestPTYThemeOverrideAndToggle(t *testing.T) {
	bin := buildCLIBinary(t)
	s := startPTYSession(t, bin, tuiRuntimeEnv(t, map[string]string{
		"AGENTSPAN_THEME": "light",
	}))
	defer s.close()

	s.waitForPlain("ctrl+t dark", 8*time.Second)

	initialRaw := s.output.String()
	if trueColorEscape.MatchString(initialRaw) {
		t.Fatalf("expected terminal-native ANSI colors, found hard-coded truecolor escapes\n%s", initialRaw)
	}
	if !lightAccentFG.MatchString(initialRaw) {
		t.Fatalf("expected light theme to render standard ANSI green accents\n%s", initialRaw)
	}

	offset := s.output.Len()
	s.send("\x14") // ctrl+t
	s.waitForPlain("ctrl+t light", 8*time.Second)

	toggledRaw := s.output.SliceFrom(offset)
	if trueColorEscape.MatchString(toggledRaw) {
		t.Fatalf("expected terminal-native ANSI colors after ctrl+t, found hard-coded truecolor escapes\n%s", toggledRaw)
	}
	if !darkAccentFG.MatchString(toggledRaw) {
		t.Fatalf("expected dark theme to render bright ANSI green accents after ctrl+t\n%s", toggledRaw)
	}
	if lightAccentFG.MatchString(toggledRaw) {
		t.Fatalf("stale light-theme ANSI green accent remained after ctrl+t\n%s", toggledRaw)
	}
}

func TestPTYAppleTerminalBasicProfileStartsLight(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("Apple Terminal fallback only applies on macOS")
	}

	bin := buildCLIBinary(t)
	fakeBinDir := t.TempDir()
	fakeDefaults := filepath.Join(fakeBinDir, "defaults")
	script := "#!/bin/sh\n" +
		"if [ \"$1\" = \"read\" ] && [ \"$2\" = \"com.apple.Terminal\" ]; then\n" +
		"  if [ \"$3\" = \"Default Window Settings\" ] || [ \"$3\" = \"Startup Window Settings\" ]; then\n" +
		"    printf 'Basic\\n'\n" +
		"    exit 0\n" +
		"  fi\n" +
		"fi\n" +
		"exit 1\n"
	if err := os.WriteFile(fakeDefaults, []byte(script), 0o755); err != nil {
		t.Fatalf("write fake defaults: %v", err)
	}

	env := map[string]string{
		"TERM_PROGRAM":                     "Apple_Terminal",
		"PATH":                             fakeBinDir + string(os.PathListSeparator) + os.Getenv("PATH"),
		"AGENTSPAN_TEST_DISABLE_OSC_QUERY": "1",
	}
	s := startPTYSession(t, bin, tuiRuntimeEnv(t, env))
	defer s.close()

	s.waitForPlain("ctrl+t dark", 8*time.Second)

	raw := s.output.String()
	if trueColorEscape.MatchString(raw) {
		t.Fatalf("expected Apple Terminal fallback to keep terminal-native ANSI colors\n%s", raw)
	}
	if !lightAccentFG.MatchString(raw) {
		t.Fatalf("expected Apple Terminal Basic fallback to start with light-theme ANSI accents\n%s", raw)
	}
}

func TestPTYDashboardRunStartsAgentExecution(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("PTY harness is only supported on Unix-like platforms")
	}

	bin := buildCLIBinary(t)

	srv, state := startRunStubServer()
	defer srv.Close()

	s := startPTYSession(t, bin, tuiRuntimeEnv(t, map[string]string{
		"AGENTSPAN_SERVER_URL": srv.URL,
		"AGENTSPAN_THEME":      "light",
	}))
	defer s.close()

	s.waitForPlain("Dashboard", 8*time.Second)
	s.send("r")
	s.waitForPlain("Run Agent", 8*time.Second)
	s.waitForPlain("Select the registered agent to run", 8*time.Second)

	s.send("\r")
	time.Sleep(150 * time.Millisecond)
	s.sendSlow("hello from tui", 15*time.Millisecond)
	s.waitForPlain("hello from tui", 5*time.Second)
	s.send("\r")
	time.Sleep(150 * time.Millisecond)
	s.send("\r")

	s.waitForPlain("Execution: exec-1234", 10*time.Second)
	s.waitForPlain("Execution completed.", 10*time.Second)

	startCalls, gotAgentName, gotPrompt := state.snapshot()
	if startCalls != 1 {
		t.Fatalf("expected exactly one start request, got %d", startCalls)
	}
	if gotAgentName != "demo" {
		t.Fatalf("start request agent name = %q, want demo", gotAgentName)
	}
	if gotPrompt != "hello from tui" {
		t.Fatalf("start request prompt = %q, want %q", gotPrompt, "hello from tui")
	}
}

func TestPTYAgentsRunPromptsForInputImmediately(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("PTY harness is only supported on Unix-like platforms")
	}

	bin := buildCLIBinary(t)
	srv, state := startRunStubServer()
	defer srv.Close()

	s := startPTYSession(t, bin, tuiRuntimeEnv(t, map[string]string{
		"AGENTSPAN_SERVER_URL": srv.URL,
		"AGENTSPAN_THEME":      "light",
	}))
	defer s.close()

	s.waitForPlain("Dashboard", 8*time.Second)
	s.send("2")
	s.waitForPlain("Registered Agents", 8*time.Second)
	s.waitForPlain("demo", 8*time.Second)

	s.send("r")
	s.waitForPlain("Run Agent: demo", 8*time.Second)
	s.waitForPlain("Prompt", 8*time.Second)

	plain := normalizeTTY(s.output.String())
	if strings.Contains(plain, "Select the registered agent to run") {
		t.Fatalf("selected-agent run should open directly on prompt entry, not a second agent selector\n%s", plain)
	}

	s.sendSlow("hello from agents view", 15*time.Millisecond)
	time.Sleep(250 * time.Millisecond)
	s.send("\r")
	time.Sleep(150 * time.Millisecond)
	s.send("\r")

	s.waitForPlain("Execution: exec-1234", 10*time.Second)
	s.waitForPlain("Execution completed.", 10*time.Second)

	startCalls, gotAgentName, gotPrompt := state.snapshot()
	if startCalls != 1 {
		t.Fatalf("expected exactly one start request, got %d", startCalls)
	}
	if gotAgentName != "demo" {
		t.Fatalf("start request agent name = %q, want demo", gotAgentName)
	}
	if gotPrompt != "hello from agents view" {
		t.Fatalf("start request prompt = %q, want %q", gotPrompt, "hello from agents view")
	}
}

func startRunStubServer() (*httptest.Server, *runStubState) {
	state := &runStubState{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/health":
			w.WriteHeader(http.StatusOK)

		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/list":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"name":        "demo",
					"version":     1,
					"type":        "agent",
					"description": "Demo agent",
				},
			})

		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/executions":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"totalHits": 0,
				"results":   []interface{}{},
			})

		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/demo":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"name":         "demo",
				"model":        "openai/gpt-4o",
				"instructions": "You are a demo agent.",
				"tools":        []interface{}{},
			})

		case r.Method == http.MethodPost && r.URL.Path == "/api/agent/start":
			var req startRequest
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			state.recordStart(req)

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{
				"executionId": "exec-1234",
				"agentName":   "demo",
			})

		case r.Method == http.MethodGet && r.URL.Path == "/api/agent/stream/exec-1234":
			w.Header().Set("Content-Type", "text/event-stream")
			w.WriteHeader(http.StatusOK)
			if flusher, ok := w.(http.Flusher); ok {
				flusher.Flush()
			}
			_, _ = fmt.Fprint(w, "event: message\ndata: started\n\n")
			if flusher, ok := w.(http.Flusher); ok {
				flusher.Flush()
			}
			_, _ = fmt.Fprint(w, "event: done\ndata: {\"output\":\"ok\"}\n\n")

		default:
			http.NotFound(w, r)
		}
	}))
	return srv, state
}

func buildCLIBinary(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("get working directory: %v", err)
	}
	cliDir := filepath.Dir(wd)
	tmp := t.TempDir()
	bin := filepath.Join(tmp, "agentspan")
	cacheDir := filepath.Join(tmp, "go-build-cache")

	cmd := exec.Command("go", "build", "-o", bin, ".")
	cmd.Dir = cliDir
	cmd.Env = append(tuiRuntimeEnv(t, nil), "GOCACHE="+cacheDir)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("build CLI binary: %v\n%s", err, string(out))
	}
	return bin
}

func startPTYSession(t *testing.T, bin string, env []string) *ptySession {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("PTY harness is only supported on Unix-like platforms")
	}
	if _, err := exec.LookPath("script"); err != nil {
		t.Skipf("script command not available: %v", err)
	}

	args := ptyCommandArgs(bin)
	cmd := exec.Command("script", args...)
	cmd.Env = env

	var out lockedBuffer
	cmd.Stdout = &out
	cmd.Stderr = &out

	stdin, err := cmd.StdinPipe()
	if err != nil {
		t.Fatalf("stdin pipe: %v", err)
	}
	if err := cmd.Start(); err != nil {
		t.Fatalf("start PTY session: %v", err)
	}

	s := &ptySession{
		t:      t,
		cmd:    cmd,
		stdin:  stdin,
		output: &out,
		waitCh: make(chan error, 1),
	}
	go func() {
		err := cmd.Wait()
		s.mu.Lock()
		s.exited = true
		s.exitErr = err
		s.mu.Unlock()
		s.waitCh <- err
		close(s.waitCh)
	}()
	return s
}

func ptyCommandArgs(bin string) []string {
	command := "stty rows 40 cols 120; exec " + shellQuote(bin) + " tui"
	switch runtime.GOOS {
	case "darwin":
		return []string{"-qe", "/dev/null", "/bin/sh", "-lc", command}
	default:
		return []string{"-qe", "-c", command, "/dev/null"}
	}
}

func tuiRuntimeEnv(t *testing.T, overrides map[string]string) []string {
	t.Helper()
	remove := map[string]bool{
		"NO_COLOR":                         true,
		"AGENTSPAN_THEME":                  true,
		"AGENTSPAN_TEST_DISABLE_OSC_QUERY": true,
		"COLORFGBG":                        true,
		"TERM":                             true,
		"COLORTERM":                        true,
		"CI":                               true,
		"CODEX_CI":                         true,
	}
	for key := range overrides {
		remove[key] = true
	}

	var env []string
	for _, item := range os.Environ() {
		parts := strings.SplitN(item, "=", 2)
		if remove[parts[0]] {
			continue
		}
		env = append(env, item)
	}

	env = append(env,
		"TERM=xterm-256color",
		"COLORTERM=truecolor",
		"AGENTSPAN_SERVER_URL=http://127.0.0.1:1/api",
	)
	for key, value := range overrides {
		env = append(env, key+"="+value)
	}
	return env
}

func (s *ptySession) waitForPlain(substr string, timeout time.Duration) {
	s.t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		plain := normalizeTTY(s.output.String())
		if strings.Contains(plain, substr) {
			return
		}
		if exited, err := s.exitState(); exited {
			s.t.Fatalf("PTY session exited before %q (err=%v)\n%s", substr, err, plain)
		}
		time.Sleep(50 * time.Millisecond)
	}
	s.t.Fatalf("timed out waiting for %q\n%s", substr, normalizeTTY(s.output.String()))
}

func (s *ptySession) send(chars string) {
	s.t.Helper()
	if _, err := io.WriteString(s.stdin, chars); err != nil {
		s.t.Fatalf("write PTY input %q: %v", chars, err)
	}
}

func (s *ptySession) sendSlow(chars string, delay time.Duration) {
	s.t.Helper()
	for _, r := range chars {
		s.send(string(r))
		time.Sleep(delay)
	}
}

func (s *ptySession) close() {
	s.t.Helper()
	if exited, _ := s.exitState(); exited {
		return
	}
	_, _ = io.WriteString(s.stdin, "q")
	_ = s.stdin.Close()
	select {
	case <-s.waitCh:
	case <-time.After(2 * time.Second):
		_ = s.cmd.Process.Kill()
		<-s.waitCh
	}
}

func (s *ptySession) exitState() (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.exited, s.exitErr
}

func normalizeTTY(raw string) string {
	noOSC := ansiOSC.ReplaceAllString(raw, "")
	noANSI := ansiCSI.ReplaceAllString(noOSC, "")

	var b strings.Builder
	for _, r := range noANSI {
		switch {
		case r == '\b':
			plain := b.String()
			if plain == "" {
				continue
			}
			runes := []rune(plain)
			b.Reset()
			b.WriteString(string(runes[:len(runes)-1]))
		case r == '\r':
			continue
		case r == '\n' || r == '\t':
			b.WriteRune(r)
		case r < 32:
			continue
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'"
}
