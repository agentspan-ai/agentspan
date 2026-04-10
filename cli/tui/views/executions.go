package views

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type ExecutionsLoadedMsg struct {
	Result *client.ExecutionSearchResult
	Err    error
}

// ─── Model ───────────────────────────────────────────────────────────────────

type ExecutionsModel struct {
	client     *client.Client
	width      int
	height     int
	executions []client.AgentExecutionSummary
	total      int64
	cursor     int
	page       int
	pageSize   int
	loading    bool
	err        string
	tick       int

	// Filters
	statusFilter string
	agentFilter  string
	searchQuery  string
	searching    bool
}

func NewExecutions(c *client.Client) ExecutionsModel {
	return ExecutionsModel{
		client:   c,
		loading:  true,
		pageSize: 20,
	}
}

func (m ExecutionsModel) Init() tea.Cmd {
	return tea.Batch(m.loadExecutions(), ui.SpinnerTickCmd())
}

func (m ExecutionsModel) Update(msg tea.Msg) (ExecutionsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case ExecutionsLoadedMsg:
		m.loading = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.executions = msg.Result.Results
			m.total = msg.Result.TotalHits
			m.cursor = 0
		}

	case ui.SpinnerTickMsg:
		m.tick++
		return m, ui.SpinnerTickCmd()

	case tea.KeyPressMsg:
		if m.searching {
			switch msg.String() {
			case "esc", "enter":
				m.searching = false
				m.page = 0
				return m, m.loadExecutions()
			case "backspace":
				if len(m.searchQuery) > 0 {
					m.searchQuery = m.searchQuery[:len(m.searchQuery)-1]
				}
			default:
				if len(msg.String()) == 1 {
					m.searchQuery += msg.String()
				}
			}
			return m, nil
		}

		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.executions)-1 {
				m.cursor++
			}
		case "left", "h":
			if m.page > 0 {
				m.page--
				m.loading = true
				return m, m.loadExecutions()
			}
		case "right", "l":
			maxPage := int(m.total) / m.pageSize
			if m.page < maxPage {
				m.page++
				m.loading = true
				return m, m.loadExecutions()
			}
		case "/":
			m.searching = true
			m.searchQuery = ""
		case "esc":
			m.searchQuery = ""
			m.statusFilter = ""
			m.page = 0
			m.loading = true
			return m, m.loadExecutions()
		case "R":
			m.loading = true
			m.err = ""
			return m, m.loadExecutions()
		}
	}
	return m, nil
}

// StreamSelectedExecution returns true if the user pressed 's' on a RUNNING execution.
// The caller (app.go) checks this after delegating the key and navigates accordingly.
func (m ExecutionsModel) WantsStream(key string) bool {
	return key == "s" && m.SelectedIsRunning()
}

func (m ExecutionsModel) View() string {
	contentWidth := ui.ContentWidth(m.width)

	// Header
	totalStr := fmt.Sprintf("%d total", m.total)
	header := ui.SectionHeadingStyle.Render(fmt.Sprintf("Executions  (%s)", totalStr))

	// Filter bar
	var filterBar string
	if m.searching {
		filterBar = "\n" + ui.DimStyle.Render("search: ") +
			lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(m.searchQuery+"▌")
	} else if m.searchQuery != "" {
		filterBar = "\n" + ui.DimStyle.Render("filter: "+m.searchQuery) +
			"  " + ui.DimStyle.Render("esc to clear")
	}

	// Error
	var errBanner string
	if m.err != "" {
		errBanner = "\n" + ui.ErrorBanner(contentWidth-4, m.err)
	}

	// Table or loading
	var tableContent string
	if m.loading {
		tableContent = "\n" + ui.DimStyle.Render(fmt.Sprintf("  %s  Loading executions...",
			ui.SpinnerFrame(m.tick)))
	} else if len(m.executions) == 0 {
		tableContent = "\n" + ui.EmptyState("No executions found.")
	} else {
		tableContent = "\n" + m.renderTable(contentWidth-4)
	}

	// Pagination
	currentPage := m.page + 1
	totalPages := int(m.total)/m.pageSize + 1
	pagination := "\n" + ui.DimStyle.Render(fmt.Sprintf(
		"← prev  page %d/%d  next →  (%d total)",
		currentPage, totalPages, m.total))

	hint := "\n" + ui.DimStyle.Render("enter detail  s stream  / search  ← → pages  R refresh")

	body := header + filterBar + errBanner + tableContent + pagination + hint
	return ui.ContentPanel(contentWidth, ui.ContentHeight(m.height), "", body)
}

func (m ExecutionsModel) renderTable(width int) string {
	colWidths := []int{15, 18, 15, 14, 10}
	headers := []string{"EXECUTION ID", "AGENT", "STATUS", "STARTED", "DURATION"}

	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width))
	headerLine := renderTableRow(headers, colWidths, true)

	var rows strings.Builder
	for i, e := range m.executions {
		cells := []string{
			components.TruncateID(e.ExecutionID),
			ui.Truncate(e.AgentName, 16),
			ui.StatusBadge(e.Status),
			components.RelativeTime(e.StartTime),
			components.FormatDuration(e.ExecutionTime),
		}
		line := renderTableRow(cells, colWidths, false)
		cursor := "  "
		if i == m.cursor {
			cursor = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("▶ ")
			line = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render(line)
		}
		rows.WriteString(cursor + line + "\n")
	}
	return headerLine + "\n" + sep + "\n" + rows.String()
}

// ─── Commands ────────────────────────────────────────────────────────────────

func (m ExecutionsModel) loadExecutions() tea.Cmd {
	return func() tea.Msg {
		start := m.page * m.pageSize
		result, err := m.client.SearchExecutions(
			start, m.pageSize,
			m.agentFilter,
			m.statusFilter,
			m.searchQuery,
		)
		return ExecutionsLoadedMsg{Result: result, Err: err}
	}
}

// SelectedExecutionID returns the execution ID at the cursor.
func (m ExecutionsModel) SelectedExecutionID() string {
	if m.cursor < len(m.executions) {
		return m.executions[m.cursor].ExecutionID
	}
	return ""
}

// SelectedIsRunning returns true if selected execution is RUNNING.
func (m ExecutionsModel) SelectedIsRunning() bool {
	if m.cursor < len(m.executions) {
		return m.executions[m.cursor].Status == "RUNNING"
	}
	return false
}

// FooterHints returns context-sensitive key hints.
func (m ExecutionsModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("↑↓", "navigate"),
		ui.KeyHint("enter", "detail"),
		ui.KeyHint("s", "stream"),
		ui.KeyHint("/", "search"),
		ui.KeyHint("←→", "pages"),
		ui.KeyHint("R", "refresh"),
		ui.KeyHint("q", "quit"),
	}, "  ")
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m ExecutionsModel) Cursor() int         { return m.cursor }
func (m ExecutionsModel) Page() int           { return m.page }
func (m ExecutionsModel) PageSize() int       { return m.pageSize }
func (m ExecutionsModel) Searching() bool     { return m.searching }
func (m ExecutionsModel) SearchQuery() string { return m.searchQuery }
func (m ExecutionsModel) Loading() bool       { return m.loading }

func (m *ExecutionsModel) SetTotal(n int64)   { m.total = n }
func (m *ExecutionsModel) SetPageSize(n int)  { m.pageSize = n }

func (m *ExecutionsModel) InjectRunning(id string) {
	m.executions = []client.AgentExecutionSummary{{
		ExecutionID: id, AgentName: "test-agent", Status: "RUNNING",
	}}
	m.total = 1
}

// WantsEsc returns true when the view has internal state to clear.
func (m ExecutionsModel) WantsEsc() bool {
	return m.searching || m.searchQuery != ""
}
