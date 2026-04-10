package views

import (
	"encoding/json"
	"fmt"
	"strings"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type ExecutionDetailMsg struct {
	Detail *client.ExecutionDetail
	Err    error
}

type RespondSentMsg struct {
	Approved bool
	Err      error
}

// ─── Model ───────────────────────────────────────────────────────────────────

type StatusModel struct {
	client      *client.Client
	width       int
	height      int
	executionID string
	detail      *client.ExecutionDetail
	loading     bool
	err         string

	inputVP  viewport.Model
	outputVP viewport.Model
	focus    int // 0=input, 1=output
	loaded   bool

	spinTick int

	// HITL respond
	hitlConfirm bool
	hitlApprove bool
	hitlReason  string
	hitlInput   bool // typing reason
}

func NewStatus(c *client.Client, executionID string) StatusModel {
	return StatusModel{
		client:      c,
		executionID: executionID,
		loading:     true,
	}
}

func (m StatusModel) Init() tea.Cmd {
	return tea.Batch(m.loadDetail(), ui.SpinnerTickCmd())
}

func (m StatusModel) Update(msg tea.Msg) (StatusModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		vpH := ui.ContentHeight(m.height) - 14
		if vpH < 4 {
			vpH = 4
		}
		vpW := (ui.ContentWidth(m.width) - 8) / 2
		m.inputVP.SetWidth(vpW)
		m.inputVP.SetHeight(vpH)
		m.outputVP.SetWidth(vpW)
		m.outputVP.SetHeight(vpH)

	case ExecutionDetailMsg:
		m.loading = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.detail = msg.Detail
			m.loaded = true
			m.initViewports()
		}

	case RespondSentMsg:
		m.hitlConfirm = false
		m.hitlInput = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			return m, m.loadDetail()
		}

	case ui.SpinnerTickMsg:
		m.spinTick++
		if m.loading {
			return m, ui.SpinnerTickCmd()
		}

	case tea.KeyPressMsg:
		if m.hitlInput {
			switch msg.String() {
			case "enter":
				m.hitlInput = false
			case "esc":
				m.hitlInput = false
				m.hitlConfirm = false
			case "backspace":
				if len(m.hitlReason) > 0 {
					m.hitlReason = m.hitlReason[:len(m.hitlReason)-1]
				}
			default:
				if len(msg.String()) == 1 {
					m.hitlReason += msg.String()
				}
			}
			return m, nil
		}

		if m.hitlConfirm {
			switch msg.String() {
			case "y", "Y", "enter":
				return m, m.respond(m.hitlApprove, m.hitlReason)
			case "n", "N", "esc":
				m.hitlConfirm = false
			case "r":
				m.hitlInput = true
			}
			return m, nil
		}

		switch msg.String() {
		case "tab":
			m.focus = (m.focus + 1) % 2
		case "R":
			m.loading = true
			return m, m.loadDetail()
		case "up", "k":
			if m.focus == 0 {
				m.inputVP.ScrollUp(1)
			} else {
				m.outputVP.ScrollUp(1)
			}
		case "down", "j":
			if m.focus == 0 {
				m.inputVP.ScrollDown(1)
			} else {
				m.outputVP.ScrollDown(1)
			}
		case "a":
			// Approve HITL
			if m.detail != nil && m.detail.Status == "WAITING" {
				m.hitlConfirm = true
				m.hitlApprove = true
				m.hitlReason = ""
			}
		case "x":
			// Deny HITL
			if m.detail != nil && m.detail.Status == "WAITING" {
				m.hitlConfirm = true
				m.hitlApprove = false
				m.hitlReason = ""
			}
		}
	}
	return m, nil
}

func (m StatusModel) View() string {
	cw := ui.ContentWidth(m.width)

	if m.loading {
		return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Execution Status",
			ui.DimStyle.Render(fmt.Sprintf("  %s  Loading...", ui.SpinnerFrame(m.spinTick))))
	}
	if m.err != "" {
		return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Execution Status",
			ui.ErrorBanner(cw-4, m.err))
	}
	if m.detail == nil {
		return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Execution Status",
			ui.EmptyState("No execution selected."))
	}

	d := m.detail

	// Metadata header
	statusBadge := ui.StatusBadge(d.Status)
	idLine := lipgloss.NewStyle().Foreground(ui.ColorWhite).Bold(true).
		Render("Execution: "+components.TruncateID(d.ExecutionID)) + "  " + statusBadge

	metaRows := []string{
		lipgloss.JoinHorizontal(lipgloss.Top,
			ui.CardRow("Agent:", fmt.Sprintf("%s v%d", d.AgentName, d.Version)),
			"    ",
			ui.CardRow("Execution ID:", d.ExecutionID),
		),
	}
	if d.CurrentTask != nil {
		metaRows = append(metaRows,
			ui.CardRow("Current Task:", d.CurrentTask.TaskRefName+" ("+d.CurrentTask.Status+")"))
	}

	// HITL confirm overlay
	var hitlPanel string
	if d.Status == "WAITING" {
		hitlPanel = m.renderHITL(cw)
	}

	// Input / output panels side by side
	ioPanel := m.renderIOPanels(cw)

	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", cw-6))

	hint := ui.HintBar(
		ui.ButtonDef{Key: "tab", Label: "focus"},
		ui.ButtonDef{Key: "↑↓", Label: "scroll"},
		ui.ButtonDef{Key: "R", Label: "refresh"},
		ui.ButtonDef{Key: "esc", Label: "back"},
	)
	if d.Status == "WAITING" {
		hint = ui.KeyHint("a", "approve") + "  " + ui.KeyHint("x", "deny") + "  " + ui.DimStyle.Render("r add reason")
	}

	body := idLine + "\n" + strings.Join(metaRows, "\n") + "\n" + sep + "\n" +
		hitlPanel + ioPanel + "\n" + hint

	return ui.ContentPanel(cw, ui.ContentHeight(m.height), "", body)
}

func (m StatusModel) renderHITL(width int) string {
	if m.hitlConfirm {
		action := "Approve"
		if !m.hitlApprove {
			action = "Deny"
		}
		reasonLine := ui.DimStyle.Render("Reason: ") +
			lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(m.hitlReason)
		if m.hitlInput {
			reasonLine += lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("▌")
		}
		confirm := lipgloss.NewStyle().
			Foreground(ui.ColorYellow).Bold(true).
			Render(fmt.Sprintf("  %s this execution? [y/N]", action))
		return confirm + "\n  " + reasonLine + "\n"
	}

	banner := lipgloss.NewStyle().
		Foreground(ui.ColorYellow).Bold(true).
		Border(lipgloss.NormalBorder()).BorderForeground(ui.ColorYellow).
		Padding(0, 1).Width(width - 6).
		Render("⏸  Human input required — press a to approve, x to deny")
	return banner + "\n\n"
}

func (m StatusModel) renderIOPanels(width int) string {
	half := (width - 8) / 2

	focusedStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.ColorLimeGreen).
		Padding(0, 1).Width(half)

	unfocusedStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Padding(0, 1).Width(half)

	inputStyle := unfocusedStyle
	outputStyle := unfocusedStyle
	if m.focus == 0 {
		inputStyle = focusedStyle
	} else {
		outputStyle = focusedStyle
	}

	inputContent := ui.DimStyle.Render("Input") + "\n" + m.inputVP.View()
	outputContent := ui.DimStyle.Render("Output") + "\n" + m.outputVP.View()

	left := inputStyle.Render(inputContent)
	right := outputStyle.Render(outputContent)
	return lipgloss.JoinHorizontal(lipgloss.Top, left, "  ", right)
}

func (m *StatusModel) initViewports() {
	if m.detail == nil {
		return
	}
	vpW := (ui.ContentWidth(m.width) - 8) / 2
	vpH := ui.ContentHeight(m.height) - 14
	if vpH < 4 {
		vpH = 4
	}

	m.inputVP = viewport.New(viewport.WithWidth(vpW), viewport.WithHeight(vpH))
	m.outputVP = viewport.New(viewport.WithWidth(vpW), viewport.WithHeight(vpH))

	// Pretty-print JSON for input/output
	if m.detail.Input != nil {
		b, _ := json.MarshalIndent(m.detail.Input, "", "  ")
		m.inputVP.SetContent(string(b))
	}
	if m.detail.Output != nil {
		b, _ := json.MarshalIndent(m.detail.Output, "", "  ")
		m.outputVP.SetContent(string(b))
	}
}

// ─── Commands ────────────────────────────────────────────────────────────────

func (m StatusModel) loadDetail() tea.Cmd {
	id := m.executionID
	return func() tea.Msg {
		detail, err := m.client.GetExecutionDetail(id)
		return ExecutionDetailMsg{Detail: detail, Err: err}
	}
}

func (m StatusModel) respond(approved bool, reason string) tea.Cmd {
	id := m.executionID
	return func() tea.Msg {
		err := m.client.Respond(id, approved, reason, "")
		return RespondSentMsg{Approved: approved, Err: err}
	}
}

// IsLoaded returns true if an execution ID has been set on this model.
func (m StatusModel) IsLoaded() bool {
	return m.executionID != ""
}

// FooterHints returns context-sensitive key hints.
func (m StatusModel) FooterHints() string {
	base := strings.Join([]string{
		ui.KeyHint("tab", "toggle focus"),
		ui.KeyHint("↑↓", "scroll"),
		ui.KeyHint("R", "refresh"),
		ui.KeyHint("esc", "back"),
	}, "  ")
	if m.detail != nil && m.detail.Status == "WAITING" {
		return ui.KeyHint("a", "approve") + "  " + ui.KeyHint("x", "deny") + "  " + base
	}
	return base
}
