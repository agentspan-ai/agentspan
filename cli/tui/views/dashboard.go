package views

import (
	"fmt"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type ServerHealthMsg struct {
	Healthy bool
	Err     error
}

type DashboardDataMsg struct {
	Agents     []client.AgentSummary
	Executions []client.AgentExecutionSummary
	Err        error
}

type TickMsg struct{ Time time.Time }

// ─── Model ───────────────────────────────────────────────────────────────────

type DashboardModel struct {
	client     *client.Client
	width      int
	height     int
	healthy    bool
	checking   bool
	agents     []client.AgentSummary
	executions []client.AgentExecutionSummary
	cursor     int // selected execution row
	err        string
	loaded     bool
	tick       int
}

func NewDashboard(c *client.Client) DashboardModel {
	return DashboardModel{
		client:   c,
		checking: true,
	}
}

func (m DashboardModel) Init() tea.Cmd {
	return tea.Batch(
		m.checkHealth(),
		m.loadData(),
		tickCmd(),
	)
}

func (m DashboardModel) Update(msg tea.Msg) (DashboardModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case TickMsg:
		m.tick++
		return m, tea.Batch(tickCmd(), m.checkHealth())

	case ServerHealthMsg:
		m.checking = false
		m.healthy = msg.Healthy
		if msg.Err != nil {
			m.healthy = false
		}

	case DashboardDataMsg:
		m.loaded = true
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.agents = msg.Agents
			m.executions = msg.Executions
		}

	case ui.SpinnerTickMsg:
		m.tick++
		return m, ui.SpinnerTickCmd()

	case tea.KeyPressMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.executions)-1 {
				m.cursor++
			}
		case "R":
			m.loaded = false
			m.checking = true
			return m, tea.Batch(m.checkHealth(), m.loadData())
		}
	}
	return m, nil
}

func (m DashboardModel) View() string {
	cw := ui.ContentWidth(m.width)
	ch := ui.ContentHeight(m.height)
	innerW := cw - 4

	// ── Status bar (inline, not card) ─────────────────────────────────────
	statusBar := m.renderStatusBar(innerW)

	// ── Recent executions table ──────────────────────────────────────────
	execTable := m.renderExecutionsTable(innerW)

	// ── Footer hint ──────────────────────────────────────────────────────
	hint := ui.HintBar(
		ui.ButtonDef{Key: "↑↓", Label: "navigate"},
		ui.ButtonDef{Key: "enter", Label: "detail"},
		ui.ButtonDef{Key: "s", Label: "stream"},
		ui.ButtonDef{Key: "r", Label: "run"},
		ui.ButtonDef{Key: "R", Label: "refresh"},
	)

	var body strings.Builder
	body.WriteString(statusBar + "\n\n")
	body.WriteString(execTable + "\n")
	body.WriteString(hint)

	return ui.ContentPanel(cw, ch, "Dashboard", body.String())
}

// renderStatusBar renders server status + activity stats in a single compact bar.
func (m DashboardModel) renderStatusBar(width int) string {
	var statusStr string
	if m.checking {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorYellow).Render("⟳ checking")
	} else if m.healthy {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorGreen).Bold(true).Render("● Running")
	} else {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorRed).Bold(true).Render("◌ Offline")
	}

	dim := ui.DimStyle
	val := lipgloss.NewStyle().Foreground(ui.ColorWhite).Bold(true)

	agentCount := fmt.Sprintf("%d", len(m.agents))
	var running int
	for _, e := range m.executions {
		if e.Status == "RUNNING" {
			running++
		}
	}

	left := dim.Render("Server ") + statusStr +
		"   " + dim.Render("URL ") + val.Render("localhost:6767")

	right := dim.Render("Agents ") + val.Render(agentCount) +
		"   " + dim.Render("Running ") + val.Render(fmt.Sprintf("%d", running)) +
		"   " + dim.Render("Executions ") + val.Render(fmt.Sprintf("%d", len(m.executions)))

	leftW := lipgloss.Width(left)
	rightW := lipgloss.Width(right)
	gap := width - leftW - rightW - 4
	if gap < 1 {
		gap = 1
	}

	content := left + strings.Repeat(" ", gap) + right
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Padding(0, 1).
		Width(width).
		Render(content)
}

func (m DashboardModel) renderExecutionsTable(width int) string {
	if !m.loaded {
		return ui.DimStyle.Render("  " + ui.SpinnerFrame(m.tick) + " Loading executions...")
	}
	if m.err != "" {
		return ui.ErrorBanner(width, m.err)
	}
	if len(m.executions) == 0 {
		return ui.EmptyState("No executions yet. Run an agent to get started.")
	}

	heading := ui.SectionHeadingStyle.Render("Recent Executions")

	// Build a simple styled table without the table package (for flexibility)
	colWidths := []int{14, 18, 14, 12, 10}
	headers := []string{"EXECUTION ID", "AGENT", "STATUS", "STARTED", "DURATION"}

	headerLine := renderTableRow(headers, colWidths, true)
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width-4))

	var rows strings.Builder
	for i, e := range m.executions {
		isSelected := i == m.cursor
		cells := []string{
			components.TruncateID(e.ExecutionID),
			ui.Truncate(e.AgentName, 16),
			ui.StatusBadge(e.Status),
			components.RelativeTime(e.StartTime),
			components.FormatDuration(e.ExecutionTime),
		}
		line := renderTableRow(cells, colWidths, false)
		if isSelected {
			line = lipgloss.NewStyle().
				Background(ui.ColorDarkGreen).
				Foreground(ui.ColorLimeGreen).
				Render(line)
		}
		rows.WriteString(line + "\n")
	}

	return heading + "\n" + sep + "\n" + headerLine + "\n" + sep + "\n" + rows.String()
}

// renderTableRow builds a fixed-width table row.
func renderTableRow(cells []string, widths []int, isHeader bool) string {
	var sb strings.Builder
	for i, cell := range cells {
		w := 14
		if i < len(widths) {
			w = widths[i]
		}
		if isHeader {
			sb.WriteString(lipgloss.NewStyle().
				Foreground(ui.ColorLimeGreen).
				Bold(true).
				Width(w).
				Render(ui.Truncate(cell, w-1)))
		} else {
			sb.WriteString(lipgloss.NewStyle().
				Foreground(ui.ColorWhite).
				Width(w).
				Render(ui.Truncate(cell, w-1)))
		}
	}
	return sb.String()
}

// ─── Commands ────────────────────────────────────────────────────────────────

func tickCmd() tea.Cmd {
	return tea.Tick(10*time.Second, func(t time.Time) tea.Msg {
		return TickMsg{Time: t}
	})
}

func (m DashboardModel) checkHealth() tea.Cmd {
	return func() tea.Msg {
		err := m.client.HealthCheck()
		return ServerHealthMsg{Healthy: err == nil, Err: err}
	}
}

func (m DashboardModel) loadData() tea.Cmd {
	return func() tea.Msg {
		agents, err := m.client.ListAgents()
		if err != nil {
			return DashboardDataMsg{Err: err}
		}
		result, err := m.client.SearchExecutions(0, 10, "", "", "")
		if err != nil {
			return DashboardDataMsg{Agents: agents, Err: err}
		}
		return DashboardDataMsg{Agents: agents, Executions: result.Results}
	}
}

// SelectedExecutionID returns the execution ID of the highlighted row.
func (m DashboardModel) SelectedExecutionID() string {
	if m.cursor < len(m.executions) {
		return m.executions[m.cursor].ExecutionID
	}
	return ""
}

// SelectedIsRunning returns true if the selected execution is RUNNING.
func (m DashboardModel) SelectedIsRunning() bool {
	if m.cursor < len(m.executions) {
		return m.executions[m.cursor].Status == "RUNNING"
	}
	return false
}

// FooterHints returns context-sensitive key hints for this view.
func (m DashboardModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("↑↓", "navigate"),
		ui.KeyHint("enter", "detail"),
		ui.KeyHint("s", "stream"),
		ui.KeyHint("r", "run"),
		ui.KeyHint("R", "refresh"),
		ui.KeyHint("q", "quit"),
	}, "  ")
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m DashboardModel) Loaded() bool { return m.loaded }
