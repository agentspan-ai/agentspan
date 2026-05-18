// Package examples provides fetching and installing of AgentSpan SDK examples
// from the GitHub repository at github.com/agentspan-ai/agentspan.
package examples

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const (
	repoOwner  = "agentspan-ai"
	repoName   = "agentspan"
	repoBranch = "main"

	pythonExamplesPath = "sdk/python/examples"
	tsExamplesPath     = "sdk/typescript/examples"

	githubAPIBase = "https://api.github.com"
	githubRawBase = "https://raw.githubusercontent.com"
)

// Language identifies the SDK language of an example.
type Language string

const (
	Python     Language = "python"
	TypeScript Language = "typescript"
)

// Example holds metadata for a single example file.
type Example struct {
	Filename    string // e.g. "01_basic_agent.py"
	Name        string // e.g. "Basic Agent"
	Description string // first sentence of the docstring
	Language    Language
	Path        string // full repo path e.g. "sdk/python/examples/01_basic_agent.py"
	DownloadURL string // raw GitHub URL
	Number      string // e.g. "01"
	Tags        []string
}

// DisplayName returns a formatted label for the multi-select.
func (e Example) DisplayName() string {
	lang := "🐍"
	if e.Language == TypeScript {
		lang = "📘"
	}
	return fmt.Sprintf("%s  %-4s  %s", lang, e.Number, e.Name)
}

// ghTreeEntry is one item from the GitHub Trees API.
type ghTreeEntry struct {
	Path string `json:"path"`
	Type string `json:"type"` // "blob" or "tree"
	SHA  string `json:"sha"`
	URL  string `json:"url"`
	Size int    `json:"size"`
}

type ghTree struct {
	Tree []ghTreeEntry `json:"tree"`
}

// ghFileContent is the response from the GitHub Contents API.
type ghFileContent struct {
	Content  string `json:"content"`  // base64 encoded
	Encoding string `json:"encoding"` // "base64"
}

// client is a simple rate-limit-aware HTTP client for GitHub.
var httpClient = &http.Client{Timeout: 30 * time.Second}

func githubGet(url string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github.v3+json")
	req.Header.Set("User-Agent", "agentspan-cli/1.0")
	// Use GITHUB_TOKEN if available to avoid rate limiting
	if tok := os.Getenv("GITHUB_TOKEN"); tok != "" {
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	return httpClient.Do(req)
}

// FetchExampleList retrieves the list of examples for both SDKs from GitHub.
func FetchExampleList() ([]Example, error) {
	var all []Example

	pyExamples, err := fetchDirListing(pythonExamplesPath, Python)
	if err != nil {
		return nil, fmt.Errorf("fetch python examples: %w", err)
	}
	all = append(all, pyExamples...)

	tsExamples, err := fetchDirListing(tsExamplesPath, TypeScript)
	if err != nil {
		return nil, fmt.Errorf("fetch typescript examples: %w", err)
	}
	all = append(all, tsExamples...)

	return all, nil
}

// fetchDirListing uses the GitHub Trees API to list files in a directory.
func fetchDirListing(dir string, lang Language) ([]Example, error) {
	// Use the Git Trees API for reliable recursive listing
	url := fmt.Sprintf("%s/repos/%s/%s/git/trees/%s?recursive=0",
		githubAPIBase, repoOwner, repoName, repoBranch)

	resp, err := githubGet(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("GitHub API returned %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	// The tree API at root level won't recurse deep enough — use contents API instead
	contentsURL := fmt.Sprintf("%s/repos/%s/%s/contents/%s?ref=%s",
		githubAPIBase, repoOwner, repoName, dir, repoBranch)

	resp2, err := githubGet(contentsURL)
	if err != nil {
		return nil, err
	}
	defer resp2.Body.Close()
	_ = body // unused from first call

	if resp2.StatusCode != 200 {
		return nil, fmt.Errorf("GitHub contents API returned %d for %s", resp2.StatusCode, dir)
	}

	var entries []struct {
		Name        string `json:"name"`
		Path        string `json:"path"`
		Type        string `json:"type"`
		DownloadURL string `json:"download_url"`
	}
	if err := json.NewDecoder(resp2.Body).Decode(&entries); err != nil {
		return nil, fmt.Errorf("decode contents: %w", err)
	}

	var examples []Example
	for _, e := range entries {
		if e.Type != "file" {
			continue
		}
		if lang == Python && !strings.HasSuffix(e.Name, ".py") {
			continue
		}
		if lang == TypeScript && !strings.HasSuffix(e.Name, ".ts") {
			continue
		}
		// Skip __init__.py, settings.py, etc.
		if strings.HasPrefix(e.Name, "__") || e.Name == "settings.py" || e.Name == "requirements.txt" {
			continue
		}

		ex := Example{
			Filename:    e.Name,
			Language:    lang,
			Path:        e.Path,
			DownloadURL: e.DownloadURL,
		}
		ex.Number, ex.Name, ex.Tags = parseExampleName(e.Name, lang)
		examples = append(examples, ex)
	}

	return examples, nil
}

// parseExampleName extracts the number and human-readable name from filename.
// e.g. "01_basic_agent.py" → "01", "Basic Agent"
// e.g. "01-basic-agent.ts" → "01", "Basic Agent"
func parseExampleName(filename string, lang Language) (number, name string, tags []string) {
	// Strip extension
	base := filename
	if idx := strings.LastIndex(base, "."); idx >= 0 {
		base = base[:idx]
	}

	// Normalise separators
	base = strings.ReplaceAll(base, "-", "_")

	// Extract leading number
	numRe := regexp.MustCompile(`^(\d+[a-z]?)_(.+)$`)
	m := numRe.FindStringSubmatch(base)
	if m != nil {
		number = m[1]
		name = humanise(m[2])
	} else {
		name = humanise(base)
		number = "??"
	}

	// Infer tags from name
	lower := strings.ToLower(name)
	tagMap := map[string]string{
		"tool": "tools", "http": "http", "mcp": "mcp",
		"human": "hitl", "loop": "hitl", "guardrail": "guardrails",
		"stream": "streaming", "memory": "memory", "credential": "credentials",
		"parallel": "parallel", "sequential": "sequential", "router": "router",
		"handoff": "handoff", "hierarchical": "multi-agent", "swarm": "multi-agent",
		"code": "code-execution", "opentelemetry": "observability",
		"skill": "skills",
	}
	seen := map[string]bool{}
	for kw, tag := range tagMap {
		if strings.Contains(lower, kw) && !seen[tag] {
			tags = append(tags, tag)
			seen[tag] = true
		}
	}

	return
}

// humanise converts snake_case to Title Case.
func humanise(s string) string {
	parts := strings.Split(s, "_")
	for i, p := range parts {
		if len(p) > 0 {
			parts[i] = strings.ToUpper(p[:1]) + p[1:]
		}
	}
	return strings.Join(parts, " ")
}

// FetchFileContent downloads the raw content of a single example file.
func FetchFileContent(ex Example) (string, error) {
	if ex.DownloadURL != "" {
		resp, err := httpClient.Get(ex.DownloadURL)
		if err != nil {
			return "", err
		}
		defer resp.Body.Close()
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return "", err
		}
		return string(body), nil
	}

	// Fallback: use contents API with base64 decoding
	url := fmt.Sprintf("%s/repos/%s/%s/contents/%s?ref=%s",
		githubAPIBase, repoOwner, repoName, ex.Path, repoBranch)
	resp, err := githubGet(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	var fc ghFileContent
	if err := json.NewDecoder(resp.Body).Decode(&fc); err != nil {
		return "", err
	}
	content := strings.ReplaceAll(fc.Content, "\n", "")
	decoded, err := base64.StdEncoding.DecodeString(content)
	if err != nil {
		return "", fmt.Errorf("base64 decode: %w", err)
	}
	return string(decoded), nil
}

// InstallExamples downloads selected examples into destDir.
// Also downloads required support files (settings.py for Python, shared.ts
// for TypeScript) so the examples can be deployed without missing imports.
// Returns a map of filename → error (nil = success).
func InstallExamples(examples []Example, destDir string) map[string]error {
	results := make(map[string]error, len(examples))

	// Track which support files we still need to fetch
	needPySupport := false
	needTSSupport := false

	for _, ex := range examples {
		content, err := FetchFileContent(ex)
		if err != nil {
			results[ex.Filename] = err
			continue
		}
		dest := filepath.Join(destDir, ex.Filename)
		if _, err := os.Stat(dest); err == nil {
			dest = filepath.Join(destDir, addSuffix(ex.Filename))
		}
		if err := os.WriteFile(dest, []byte(content), 0644); err != nil {
			results[ex.Filename] = err
			continue
		}
		results[ex.Filename] = nil

		if ex.Language == Python {
			needPySupport = true
		} else if ex.Language == TypeScript {
			needTSSupport = true
		}
	}

	// Download Python support file (settings.py) if not already present
	if needPySupport {
		ensureSupportFile(destDir, pythonExamplesPath+"/settings.py", "settings.py")
	}

	// Download TypeScript support files if not already present
	if needTSSupport {
		ensureSupportFile(destDir, tsExamplesPath+"/settings.ts", "settings.ts")
		ensureSupportFile(destDir, tsExamplesPath+"/tsconfig.json", "tsconfig.json")
	}

	return results
}

// ensureSupportFile downloads a support file from GitHub if it doesn't already
// exist in destDir. Silently ignores errors — examples may still work.
func ensureSupportFile(destDir, repoPath, filename string) {
	dest := filepath.Join(destDir, filename)
	if _, err := os.Stat(dest); err == nil {
		return // already exists
	}
	// raw.githubusercontent.com format: /owner/repo/branch/path
	rawURL := fmt.Sprintf("%s/%s/%s/%s/%s",
		githubRawBase, repoOwner, repoName, repoBranch, repoPath)
	resp, err := httpClient.Get(rawURL)
	if err != nil {
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return
	}
	_ = os.WriteFile(dest, body, 0644)
}

// addSuffix appends _new before the extension to avoid overwriting.
func addSuffix(filename string) string {
	ext := filepath.Ext(filename)
	base := strings.TrimSuffix(filename, ext)
	return base + "_new" + ext
}
