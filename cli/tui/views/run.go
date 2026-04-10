package views

import (
	"fmt"
	"os"
	"strings"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type RunStartedMsg struct {
	ExecutionID string
	AgentName   string
	Err         error
}

type SSELineMsg struct {
	EventType string
	Data      string
}

type SSEDoneMsg struct {
	Err error
}

type AgentNamesLoadedMsg struct {
	Names []string
}

// ─── Stage ───────────────────────────────────────────────────────────────────

type RunStage int

const (
	RunStageForm   RunStage = iota // showing the huh form
	RunStageStream                 // streaming live SSE events
	RunStageDone                   // execution completed
)

// sseChans holds the persistent channels for SSE streaming.
type sseChans struct {
	events chan client.SSEEvent
	done   chan error
}

// ─── Model ───────────────────────────────────────────────────────────────────

type RunModel struct {
	client *client.Client
	width  int
	height int
	stage  RunStage

	// Form fields
	agentNames []string
	agentName  string
	prompt     string
	sessionID  string
	noStream   bool
	form       *huh.Form
	formErr    string

	// Stream state
	executionID string
	agentResult string
	status      string
	lines       []string
	vp          viewport.Model
	following   bool
	tick        int
	streamErr   string
	sseCh       *sseChans // persistent SSE channels

	// Pre-selected agent (from Agents view)
	preselected string
}

func NewRun(c *client.Client, preselectedAgent string) RunModel {
	m := RunModel{
		client:      c,
		stage:       RunStageForm,
		following:   true,
		preselected: preselectedAgent,
		agentName:   preselectedAgent,
	}
	return m
}

func (m RunModel) Init() tea.Cmd {
	return tea.Batch(
		m.loadAgentNames(),
	)
}

func (m RunModel) Update(msg tea.Msg) (RunModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		if m.vp.Width() > 0 {
			vpH := ui.ContentHeight(m.height) - 10
			if vpH < 5 {
				vpH = 5
			}
			m.vp.SetWidth(ui.ContentWidth(m.width) - 6)
			m.vp.SetHeight(vpH)
		}

	case AgentNamesLoadedMsg:
		m.agentNames = msg.Names
		m.form = m.buildForm()
		return m, m.form.Init()

	case tea.KeyPressMsg:
		switch m.stage {
		case RunStageForm:
			return m.updateForm(msg)
		case RunStageStream:
			return m.updateStream(msg)
		case RunStageDone:
			return m.updateDone(msg)
		}

	case RunStartedMsg:
		if msg.Err != nil {
			m.formErr = msg.Err.Error()
			m.stage = RunStageForm
		} else {
			m.executionID = msg.ExecutionID
			m.status = "RUNNING"
			m.stage = RunStageStream
			// Init viewport — fill all available content height minus header rows
			vpH := ui.ContentHeight(m.height) - 10
			if vpH < 5 {
				vpH = 5
			}
			m.vp = viewport.New(
				viewport.WithWidth(ui.ContentWidth(m.width)-6),
				viewport.WithHeight(vpH),
			)
			m.vp.Style = lipgloss.NewStyle().
				Background(ui.ColorDeepBg)
			var streamCmd tea.Cmd
			m, streamCmd = m.startSSE()
			return m, streamCmd
		}

	case SSELineMsg:
		line := components.EventLine(msg.EventType, msg.Data)
		if line != "" {
			m.lines = append(m.lines, line)
			m.vp.SetContent(strings.Join(m.lines, "\n"))
			if m.following {
				m.vp.GotoBottom()
			}
		}
		// Schedule reading the next event
		return m, m.streamSSE()

	case SSEDoneMsg:
		if msg.Err != nil {
			m.streamErr = msg.Err.Error()
		}
		m.stage = RunStageDone
		m.status = "COMPLETED"

	default:
		// Delegate form updates for non-key messages
		if m.stage == RunStageForm && m.form != nil {
			form, cmd := m.form.Update(msg)
			if f, ok := form.(*huh.Form); ok {
				m.form = f
			}
			return m, cmd
		}
		// Delegate viewport updates
		if m.stage == RunStageStream || m.stage == RunStageDone {
			var cmd tea.Cmd
			m.vp, cmd = m.vp.Update(msg)
			return m, cmd
		}
	}
	return m, nil
}

func (m RunModel) updateForm(msg tea.KeyPressMsg) (RunModel, tea.Cmd) {
	if m.form == nil {
		return m, nil
	}
	switch msg.String() {
	case "esc":
		// Cancel — caller handles navigation back
		return m, nil
	}
	form, cmd := m.form.Update(msg)
	if f, ok := form.(*huh.Form); ok {
		m.form = f
		if m.form.State == huh.StateCompleted {
			return m, m.startAgent()
		}
		if m.form.State == huh.StateAborted {
			// form cancelled
		}
	}
	return m, cmd
}

func (m RunModel) updateStream(msg tea.KeyPressMsg) (RunModel, tea.Cmd) {
	switch msg.String() {
	case "f":
		m.following = !m.following
		if m.following {
			m.vp.GotoBottom()
		}
		return m, nil
	case "s":
		return m, m.saveOutput()
	case "ctrl+c":
		m.stage = RunStageDone
		m.status = "STOPPED"
		return m, nil
	default:
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	}
}

func (m RunModel) updateDone(msg tea.KeyPressMsg) (RunModel, tea.Cmd) {
	switch msg.String() {
	case "r":
		// Reset to form stage
		m.stage = RunStageForm
		m.lines = nil
		m.executionID = ""
		m.status = ""
		m.streamErr = ""
		m.form = m.buildForm()
		return m, m.form.Init()
	case "s":
		return m, m.saveOutput()
	}
	return m, nil
}

func (m RunModel) View() string {
	cw := ui.ContentWidth(m.width)

	switch m.stage {
	case RunStageForm:
		return m.renderForm(cw)
	case RunStageStream, RunStageDone:
		return m.renderStream(cw)
	}
	return ""
}

func (m RunModel) renderForm(width int) string {
	var content strings.Builder

	if len(m.agentNames) == 0 {
		content.WriteString(ui.DimStyle.Render("  Loading agents..."))
	} else if m.form != nil {
		content.WriteString(m.form.View())
	}

	if m.formErr != "" {
		content.WriteString("\n\n" + ui.ErrorBanner(width-4, m.formErr))
	}

	return ui.ContentPanel(width, ui.ContentHeight(m.height), "Run Agent", content.String())
}

func (m RunModel) renderStream(width int) string {
	ch := ui.ContentHeight(m.height)
	innerW := width - 6

	// Status header line
	statusBadge := ui.StatusBadge(m.status)
	idStr := components.TruncateID(m.executionID)
	followIndicator := ""
	if m.following && m.stage == RunStageStream {
		followIndicator = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("  [↓ following]")
	}
	execHeader := lipgloss.NewStyle().Foreground(ui.ColorWhite).Bold(true).
		Render("Execution: "+idStr) + "  " + statusBadge + followIndicator

	// Resize viewport to fill available space on every render
	vpH := ch - 10 // panel-border(2) + title-gap(3) + execHeader(1) + gap(1) + vp-border(2) + hint(1)
	if vpH < 5 {
		vpH = 5
	}
	m.vp.SetWidth(innerW)
	m.vp.SetHeight(vpH)

	vpFrame := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Background(ui.ColorDeepBg).
		Width(innerW + 2).
		Height(vpH + 2).
		Render(m.vp.View())

	// Error or done message
	var statusLine string
	if m.streamErr != "" {
		statusLine = "\n" + ui.ErrorBanner(innerW, m.streamErr)
	} else if m.stage == RunStageDone {
		statusLine = "\n" + ui.SuccessBanner(innerW, "Execution completed.")
		statusLine += "\n" + ui.DimStyle.Render("  r run again  s save output  esc back")
	}

	hint := ""
	if m.stage == RunStageStream {
		hint = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "↑↓", Label: "scroll"},
			ui.ButtonDef{Key: "f", Label: "follow"},
			ui.ButtonDef{Key: "ctrl+c", Label: "stop", Danger: true},
			ui.ButtonDef{Key: "s", Label: "save"},
		)
	}

	body := execHeader + "\n\n" + vpFrame + statusLine + hint
	return ui.ContentPanel(width, ch, "", body)
}

// ─── Form Builder ─────────────────────────────────────────────────────────────

func (m *RunModel) buildForm() *huh.Form {
	// Build agent options
	opts := make([]huh.Option[string], 0, len(m.agentNames))
	for _, name := range m.agentNames {
		opts = append(opts, huh.NewOption(name, name))
	}
	if len(opts) == 0 {
		opts = append(opts, huh.NewOption("(no agents registered)", ""))
	}

	agentSel := huh.NewSelect[string]().
		Title("Agent").
		Description("Select a registered agent to run").
		Options(opts...).
		Value(&m.agentName)
	if m.preselected != "" {
		agentSel = agentSel.Value(&m.agentName)
	}

	promptField := huh.NewText().
		Title("Prompt").
		Description("What should the agent do?").
		CharLimit(4000).
		Value(&m.prompt)

	sessionField := huh.NewInput().
		Title("Session ID").
		Description("Optional: for conversation continuity").
		Placeholder("leave blank for new session").
		Value(&m.sessionID)

	return huh.NewForm(
		huh.NewGroup(agentSel, promptField, sessionField),
	).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

// agentspanHuhTheme applies our color palette to huh forms.
func agentspanHuhTheme(isDark bool) *huh.Styles {
	s := huh.ThemeCharm(isDark)
	// Override key colors with our palette
	s.Focused.Base = s.Focused.Base.BorderForeground(ui.ColorDarkGreen)
	s.Focused.Title = s.Focused.Title.Foreground(ui.ColorLimeGreen)
	s.Focused.SelectedOption = s.Focused.SelectedOption.Foreground(ui.ColorLimeGreen)
	s.Focused.SelectSelector = s.Focused.SelectSelector.Foreground(ui.ColorLimeGreen)
	return s
}

// ─── Commands ─────────────────────────────────────────────────────────────────

func (m RunModel) loadAgentNames() tea.Cmd {
	return func() tea.Msg {
		agents, err := m.client.ListAgents()
		if err != nil {
			return AgentNamesLoadedMsg{Names: nil}
		}
		names := make([]string, len(agents))
		for i, a := range agents {
			names[i] = a.Name
		}
		return AgentNamesLoadedMsg{Names: names}
	}
}

func (m RunModel) startAgent() tea.Cmd {
	name := m.agentName
	prompt := m.prompt
	sessionID := m.sessionID
	return func() tea.Msg {
		// Fetch agent definition by name, then start with full config
		agentDef, err := m.client.GetAgent(name, nil)
		if err != nil {
			return RunStartedMsg{Err: fmt.Errorf("failed to get agent '%s': %w", name, err)}
		}
		req := &client.StartRequest{
			AgentConfig: agentDef,
			Prompt:      prompt,
			SessionID:   sessionID,
		}
		resp, err := m.client.Start(req)
		if err != nil {
			return RunStartedMsg{Err: err}
		}
		return RunStartedMsg{
			ExecutionID: resp.ExecutionID,
			AgentName:   resp.AgentName,
		}
	}
}

// startSSE initialises the SSE channels and kicks off the background goroutine.
// Returns the model with channels stored and a Cmd to read the first event.
func (m RunModel) startSSE() (RunModel, tea.Cmd) {
	ch := &sseChans{
		events: make(chan client.SSEEvent, 200),
		done:   make(chan error, 1),
	}
	m.sseCh = ch
	executionID := m.executionID
	// Start background reader
	go m.client.Stream(executionID, "", ch.events, ch.done)
	return m, nextSSEEvent(ch)
}

// nextSSEEvent returns a Cmd that blocks until the next SSE event arrives.
func nextSSEEvent(ch *sseChans) tea.Cmd {
	return func() tea.Msg {
		select {
		case evt, ok := <-ch.events:
			if !ok {
				select {
				case err := <-ch.done:
					return SSEDoneMsg{Err: err}
				default:
					return SSEDoneMsg{}
				}
			}
			return SSELineMsg{EventType: evt.Event, Data: evt.Data}
		case err := <-ch.done:
			return SSEDoneMsg{Err: err}
		}
	}
}

// streamSSE is called to get the SSE read command (uses stored channels).
func (m RunModel) streamSSE() tea.Cmd {
	if m.sseCh == nil {
		return nil
	}
	return nextSSEEvent(m.sseCh)
}

// saveOutput saves the stream output to a file.
func (m RunModel) saveOutput() tea.Cmd {
	lines := m.lines
	execID := m.executionID
	return func() tea.Msg {
		filename := fmt.Sprintf("output-%s.txt", execID[:8])
		content := strings.Join(lines, "\n")
		// Strip ANSI before saving
		_ = os.WriteFile(filename, []byte(content), 0644)
		return nil
	}
}

// FooterHints returns context-sensitive key hints.
func (m RunModel) FooterHints() string {
	switch m.stage {
	case RunStageForm:
		return strings.Join([]string{
			ui.KeyHint("tab", "next field"),
			ui.KeyHint("enter", "confirm"),
			ui.KeyHint("esc", "back"),
		}, "  ")
	case RunStageStream:
		return strings.Join([]string{
			ui.KeyHint("↑↓", "scroll"),
			ui.KeyHint("f", "follow"),
			ui.KeyHint("ctrl+c", "stop"),
			ui.KeyHint("s", "save output"),
		}, "  ")
	default:
		return strings.Join([]string{
			ui.KeyHint("r", "run again"),
			ui.KeyHint("s", "save output"),
			ui.KeyHint("esc", "back"),
		}, "  ")
	}
}
