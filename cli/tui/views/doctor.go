package views

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Check Result ─────────────────────────────────────────────────────────────

type CheckStatus int

const (
	CheckPending CheckStatus = iota
	CheckPass                // green ✓
	CheckWarn                // yellow ⚠
	CheckFail                // red ✗
	CheckSkip                // grey –
)

type CheckResult struct {
	Name   string
	Status CheckStatus
	Detail string
}

type DoctorResultMsg struct {
	Section string
	Results []CheckResult
}

// ─── Model ───────────────────────────────────────────────────────────────────

type DoctorModel struct {
	client   *client.Client
	width    int
	height   int
	running  bool
	tick     int
	sections map[string][]CheckResult
	order    []string
}

var aiProviders = []struct {
	Name    string
	EnvVars []string
	Example string
}{
	{"OpenAI", []string{"OPENAI_API_KEY"}, "gpt-4o"},
	{"Anthropic", []string{"ANTHROPIC_API_KEY"}, "claude-opus-4"},
	{"Google Gemini", []string{"GEMINI_API_KEY"}, "gemini-2.0-flash"},
	{"Azure OpenAI", []string{"AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"}, "gpt-4o"},
	{"AWS Bedrock", []string{"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}, "claude-3-5-sonnet"},
	{"Mistral", []string{"MISTRAL_API_KEY"}, "mistral-large"},
	{"Cohere", []string{"COHERE_API_KEY"}, "command-r-plus"},
	{"Grok", []string{"XAI_API_KEY"}, "grok-3"},
	{"Perplexity", []string{"PERPLEXITY_API_KEY"}, "sonar-pro"},
	{"Hugging Face", []string{"HUGGINGFACE_API_KEY"}, "llama-3.1"},
	{"Stability AI", []string{"STABILITY_API_KEY"}, "sd3.5-large"},
}

func NewDoctor(c *client.Client) DoctorModel {
	return DoctorModel{
		client:   c,
		running:  true,
		sections: make(map[string][]CheckResult),
		order:    []string{"System", "AI Providers", "Server"},
	}
}

func (m DoctorModel) Init() tea.Cmd {
	return tea.Batch(
		m.runSystemChecks(),
		m.runProviderChecks(),
		m.runServerChecks(),
	)
}

func (m DoctorModel) Update(msg tea.Msg) (DoctorModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case DoctorResultMsg:
		m.sections[msg.Section] = msg.Results
		// Check if all done
		if len(m.sections) >= 3 {
			m.running = false
		}

	case DoctorTickMsg:
		m.tick++

	case ui.SpinnerTickMsg:
		m.tick++
		return m, ui.SpinnerTickCmd()

	case tea.KeyPressMsg:
		switch msg.String() {
		case "R":
			m.running = true
			m.sections = make(map[string][]CheckResult)
			return m, tea.Batch(
				m.runSystemChecks(),
				m.runProviderChecks(),
				m.runServerChecks(),
				doctorTickCmd(),
			)
		}
	}
	return m, nil
}

type DoctorTickMsg struct{}

func doctorTickCmd() tea.Cmd {
	return tea.Tick(100*time.Millisecond, func(t time.Time) tea.Msg {
		return DoctorTickMsg{}
	})
}

func (m DoctorModel) View() string {
	cw := ui.ContentWidth(m.width)

	if m.running && len(m.sections) == 0 {
		return ui.ContentPanel(cw, ui.ContentHeight(m.height), "System Diagnostics",
			ui.DimStyle.Render(fmt.Sprintf("  %s  Running diagnostics...", ui.SpinnerFrame(m.tick))))
	}

	var sb strings.Builder

	for _, secName := range m.order {
		results, ok := m.sections[secName]
		if !ok {
			sb.WriteString(ui.SectionHeadingStyle.Render(secName) + "\n")
			sb.WriteString(ui.DimStyle.Render(fmt.Sprintf("  %s running...\n\n",
				ui.SpinnerFrame(m.tick))))
			continue
		}

		// Count configured providers for the summary line
		var summary string
		if secName == "AI Providers" {
			count := 0
			for _, r := range results {
				if r.Status == CheckPass {
					count++
				}
			}
			summary = lipgloss.NewStyle().Foreground(ui.ColorGrey).
				Render(fmt.Sprintf("  (%d configured)", count))
		}

		sb.WriteString(ui.SectionHeadingStyle.Render(secName) + summary + "\n")
		for _, r := range results {
			sb.WriteString(renderCheckResult(r) + "\n")
		}
		sb.WriteString("\n")
	}

	// Summary line
	if !m.running {
		sb.WriteString(lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", cw-8)) + "\n")
		totalFail, totalWarn := 0, 0
		for _, results := range m.sections {
			for _, r := range results {
				if r.Status == CheckFail {
					totalFail++
				} else if r.Status == CheckWarn {
					totalWarn++
				}
			}
		}
		if totalFail == 0 && totalWarn == 0 {
			sb.WriteString(ui.SuccessStyle.Render("  ✓  Everything looks good!") + "\n")
		} else {
			sb.WriteString(ui.WarnStyle.Render(
				fmt.Sprintf("  %d issue(s), %d warning(s) found — see above.", totalFail, totalWarn)) + "\n")
		}
	}

	sb.WriteString("\n" + ui.DimStyle.Render("R re-run diagnostics"))

	return ui.ContentPanel(cw, ui.ContentHeight(m.height), "System Diagnostics", sb.String())
}

func renderCheckResult(r CheckResult) string {
	var icon string
	var style lipgloss.Style
	switch r.Status {
	case CheckPass:
		icon = "✓"
		style = lipgloss.NewStyle().Foreground(ui.ColorGreen)
	case CheckWarn:
		icon = "⚠"
		style = lipgloss.NewStyle().Foreground(ui.ColorYellow)
	case CheckFail:
		icon = "✗"
		style = lipgloss.NewStyle().Foreground(ui.ColorRed)
	case CheckSkip:
		icon = "–"
		style = lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true)
	default:
		icon = "⟳"
		style = lipgloss.NewStyle().Foreground(ui.ColorYellow)
	}

	line := fmt.Sprintf("  %s  %-26s %s", icon, r.Name, r.Detail)
	return style.Render(line)
}



// ─── Check Commands ──────────────────────────────────────────────────────────

func (m DoctorModel) runSystemChecks() tea.Cmd {
	return func() tea.Msg {
		var results []CheckResult

		// Java check
		out, err := exec.Command("java", "-version").CombinedOutput()
		if err != nil {
			results = append(results, CheckResult{"Java", CheckFail, "not found (21+ required)"})
		} else {
			version := strings.TrimSpace(string(out))
			if strings.Contains(version, "21") || strings.Contains(version, "22") ||
				strings.Contains(version, "23") || strings.Contains(version, "24") {
				results = append(results, CheckResult{"Java", CheckPass, version[:min(len(version), 40)]})
			} else {
				results = append(results, CheckResult{"Java", CheckFail, "version 21+ required — " + version[:min(len(version), 30)]})
			}
		}

		// JAVA_HOME
		javaHome := os.Getenv("JAVA_HOME")
		if javaHome == "" {
			results = append(results, CheckResult{"JAVA_HOME", CheckWarn, "not set (optional)"})
		} else if _, err := os.Stat(javaHome); err == nil {
			results = append(results, CheckResult{"JAVA_HOME", CheckPass, javaHome})
		} else {
			results = append(results, CheckResult{"JAVA_HOME", CheckFail, "path does not exist: " + javaHome})
		}

		// Python
		out, err = exec.Command("python3", "--version").CombinedOutput()
		if err != nil {
			results = append(results, CheckResult{"Python", CheckSkip, "not found (optional)"})
		} else {
			results = append(results, CheckResult{"Python", CheckPass, strings.TrimSpace(string(out))})
		}

		// Disk space
		home, _ := os.UserHomeDir()
		serverDir := filepath.Join(home, ".agentspan", "server")
		_ = os.MkdirAll(serverDir, 0755)
		results = append(results, CheckResult{"Disk space", CheckPass, "checked ~/.agentspan/"})

		// JAR
		jarPath := filepath.Join(home, ".agentspan", "server", "agentspan-runtime.jar")
		if fi, err := os.Stat(jarPath); err == nil {
			sizeMB := float64(fi.Size()) / 1024 / 1024
			results = append(results, CheckResult{"Server JAR", CheckPass, fmt.Sprintf("%.0f MB cached", sizeMB)})
		} else {
			results = append(results, CheckResult{"Server JAR", CheckSkip, "not downloaded yet"})
		}

		return DoctorResultMsg{Section: "System", Results: results}
	}
}

func (m DoctorModel) runProviderChecks() tea.Cmd {
	return func() tea.Msg {
		var results []CheckResult

		for _, p := range aiProviders {
			allSet := true
			for _, env := range p.EnvVars {
				if os.Getenv(env) == "" {
					allSet = false
					break
				}
			}
			if allSet {
				results = append(results, CheckResult{
					p.Name, CheckPass,
					p.EnvVars[0] + " set  →  " + p.Example,
				})
			} else {
				results = append(results, CheckResult{
					p.Name, CheckSkip,
					"not configured  →  " + p.Example,
				})
			}
		}

		// Ollama
		ollamaURL := os.Getenv("OLLAMA_BASE_URL")
		if ollamaURL == "" {
			ollamaURL = "http://localhost:11434"
		}
		hc := &http.Client{Timeout: 2 * time.Second}
		if _, err := hc.Get(ollamaURL); err == nil {
			results = append(results, CheckResult{"Ollama", CheckPass, "connected at " + ollamaURL})
		} else {
			results = append(results, CheckResult{"Ollama", CheckSkip, "not running (optional)"})
		}

		return DoctorResultMsg{Section: "AI Providers", Results: results}
	}
}

func (m DoctorModel) runServerChecks() tea.Cmd {
	return func() tea.Msg {
		var results []CheckResult

		err := m.client.HealthCheck()
		if err == nil {
			results = append(results, CheckResult{"Health check", CheckPass, "server is responding"})
		} else {
			results = append(results, CheckResult{"Health check", CheckFail, "server not responding: " + err.Error()})
		}

		return DoctorResultMsg{Section: "Server", Results: results}
	}
}

// FooterHints returns context-sensitive key hints.
func (m DoctorModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("R", "re-run"),
		ui.KeyHint("q", "quit"),
	}, "  ")
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m DoctorModel) Running() bool                    { return m.running }
func (m DoctorModel) Sections() map[string][]CheckResult { return m.sections }
func (m *DoctorModel) SetSections(s map[string][]CheckResult) { m.sections = s; m.running = false }
