package views

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/examples"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Sub-modes ────────────────────────────────────────────────────────────────

type AgentsPane int

const (
	PaneList     AgentsPane = iota // browsable agent list
	PaneDetail                     // inspect a single agent
	PaneRun                        // run agent: huh form
	PaneStream                     // live SSE stream
	PaneDone                       // stream finished
	PaneCreate                     // agent init form
	PaneDeploy                     // deploy from project info
	PaneExamples                   // browse + install GitHub examples
)

// ─── Messages ────────────────────────────────────────────────────────────────

type AgentsLoadedMsg struct {
	Agents []client.AgentSummary
	Err    error
}

type AgentDeletedMsg struct {
	Name string
	Err  error
}

type AgentCreatedMsg struct {
	Filename string
	Err      error
}

// ─── Examples types & messages ───────────────────────────────────────────────

// exampleEntry wraps examples.Example for display in the TUI.
type exampleEntry struct {
	Filename    string
	Name        string
	Number      string
	Language    string // "python" or "typescript"
	Path        string
	DownloadURL string
	Tags        []string
}

type exInstallResult struct {
	Filename      string
	WrittenPath   string // absolute path of the written file
	Err           error  // nil = file written OK
	DeployedName  string // registered agent name(s) (empty if deploy skipped/failed)
	DeployErr     error  // nil = deployed OK, non-nil = deploy failed/skipped
	DeploySkipped bool   // true when no agent was found in the file
}

// ExamplesLoadedMsg carries the fetched example list.
type ExamplesLoadedMsg struct {
	Examples []exampleEntry
	Err      error
}

// ExamplesInstalledMsg carries the install + deploy results.
type ExamplesInstalledMsg struct {
	Results []exInstallResult
}

// ─── Action buttons ───────────────────────────────────────────────────────────

// agentListButtons defines the action bar for the agents list pane.
// The order here matches btnCursor indices.
var agentListButtons = []ui.ButtonDef{
	{Key: "r", Label: "run"},
	{Key: "n", Label: "new"},
	{Key: "E", Label: "examples"},
	{Key: "D", Label: "deploy"},
	{Key: "d", Label: "delete", Danger: true},
	{Key: "/", Label: "search"},
	{Key: "R", Label: "refresh"},
}

// ─── Model ───────────────────────────────────────────────────────────────────

type AgentsModel struct {
	client    *client.Client
	serverURL string // for deploy subprocess env var
	width     int
	height    int
	pane      AgentsPane

	// List pane
	agents     []client.AgentSummary
	filtered   []client.AgentSummary
	cursor     int // row cursor in the agent table
	btnCursor  int // which action button is highlighted (-1 = table focused)
	search     string
	searching  bool
	loading    bool
	err        string
	tick       int
	detail     *client.AgentSummary
	delConfirm bool

	// Run pane (form → stream)
	runAgentName string
	runPrompt    string
	runSessionID string
	runForm      *huh.Form
	runFormErr   string

	// Stream pane
	executionID  string
	streamStatus string
	streamLines  []string
	streamErr    string
	vp           viewport.Model
	following    bool
	sseCh        *sseChans

	// Create pane
	createName  string
	createModel string
	createForm  *huh.Form

	// Spinner tick for animated loading indicators
	spinTick int

	// pendingStreamConnect: set by NewAgentsStream, consumed in Init()
	pendingStreamConnect bool

	// Examples pane
	exLoading    bool
	exErr        string
	exList       []exampleEntry // all fetched examples
	exFiltered   []exampleEntry // after lang/search filter
	exCursor     int            // browse cursor
	exSelected   map[int]bool   // indices into exFiltered that are selected
	exLang       string         // "python", "typescript", or "" (all)
	exSearch     string
	exSearching  bool
	exInstalling bool
	exResults    []exInstallResult // install outcome per file
	exDestDir    string            // destination directory
}

func NewAgents(c *client.Client) AgentsModel {
	return AgentsModel{
		client:    c,
		loading:   true,
		pane:      PaneList,
		following: true,
	}
}

// NewAgentsWithConfig creates an AgentsModel with server URL for deploy subprocesses.
func NewAgentsWithConfig(c *client.Client, serverURL string) AgentsModel {
	m := NewAgents(c)
	m.serverURL = serverURL
	return m
}

// NewAgentsRun creates the Agents model pre-navigated to the run form.
func NewAgentsRun(c *client.Client, preselected string) AgentsModel {
	m := NewAgents(c)
	m.runAgentName = preselected
	m.pane = PaneRun
	return m
}

// NewAgentsStream creates an AgentsModel that immediately connects to an
// existing running execution's SSE stream (reconnect from Executions view).
func NewAgentsStream(c *client.Client, executionID, agentName, serverURL string) AgentsModel {
	m := NewAgentsWithConfig(c, serverURL)
	m.executionID = executionID
	m.streamStatus = "RUNNING"
	m.following = true
	m.pane = PaneStream // will be initialised fully when WindowSizeMsg arrives
	// We'll kick off the SSE connection in Init()
	m.pendingStreamConnect = true
	return m
}

// connectStreamMsg triggers SSE connection for an existing execution.
type connectStreamMsg struct{ executionID string }

func (m AgentsModel) Init() tea.Cmd {
	cmds := []tea.Cmd{m.loadAgents(), ui.SpinnerTickCmd()}
	if m.pendingStreamConnect && m.executionID != "" {
		// Use a Cmd to deliver the connect trigger so Update() can handle it
		id := m.executionID
		cmds = append(cmds, func() tea.Msg { return connectStreamMsg{id} })
	}
	return tea.Batch(cmds...)
}

// ─── Update ──────────────────────────────────────────────────────────────────

func (m AgentsModel) Update(msg tea.Msg) (AgentsModel, tea.Cmd) {
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
		return m, nil

	case AgentsLoadedMsg:
		m.loading = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.agents = msg.Agents
			m.filtered = filterAgents(m.agents, m.search)
			if m.cursor >= len(m.filtered) {
				m.cursor = 0
			}
		}
		if m.pane == PaneRun && m.runForm == nil {
			m.runForm = m.buildRunForm()
			return m, m.runForm.Init()
		}
		return m, nil

	case AgentDeletedMsg:
		m.delConfirm = false
		m.detail = nil
		m.pane = PaneList
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.err = ""
			return m, m.loadAgents()
		}

	case AgentCreatedMsg:
		m.pane = PaneList
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.err = "Created " + msg.Filename + " — edit it and run 'agentspan deploy' to register."
			return m, m.loadAgents()
		}

	case connectStreamMsg:
		// Reconnect to an existing running execution's SSE stream.
		// Init the viewport (we have dimensions from WindowSizeMsg at this point).
		m.executionID = msg.executionID
		m.streamStatus = "RUNNING"
		m.pane = PaneStream
		vpH := ui.ContentHeight(m.height) - 10
		if vpH < 5 {
			vpH = 5
		}
		m.vp = viewport.New(
			viewport.WithWidth(ui.ContentWidth(m.width)-6),
			viewport.WithHeight(vpH),
		)
		m.vp.Style = lipgloss.NewStyle().Background(ui.ColorDeepBg)
		var streamCmd tea.Cmd
		m, streamCmd = m.startSSE()
		return m, streamCmd

	case RunStartedMsg:
		if msg.Err != nil {
			m.runFormErr = msg.Err.Error()
			m.pane = PaneRun
		} else {
			m.executionID = msg.ExecutionID
			m.streamStatus = "RUNNING"
			m.pane = PaneStream
			vpH := ui.ContentHeight(m.height) - 10
			if vpH < 5 {
				vpH = 5
			}
			m.vp = viewport.New(
				viewport.WithWidth(ui.ContentWidth(m.width)-6),
				viewport.WithHeight(vpH),
			)
			m.vp.Style = lipgloss.NewStyle().Background(ui.ColorDeepBg)
			var streamCmd tea.Cmd
			m, streamCmd = m.startSSE()
			return m, streamCmd
		}

	case SSELineMsg:
		line := components.EventLine(msg.EventType, msg.Data)
		if line != "" {
			m.streamLines = append(m.streamLines, line)
			m.vp.SetContent(strings.Join(m.streamLines, "\n"))
			if m.following {
				m.vp.GotoBottom()
			}
		}
		return m, m.streamSSE()

	case SSEDoneMsg:
		m.pane = PaneDone
		m.streamStatus = "COMPLETED"
		if msg.Err != nil {
			m.streamErr = msg.Err.Error()
		}

	case ui.SpinnerTickMsg:
		m.spinTick++
		// Keep ticking while loading or installing
		if m.loading || m.exLoading || m.exInstalling {
			return m, ui.SpinnerTickCmd()
		}

	case ExamplesLoadedMsg:
		m.exLoading = false
		if msg.Err != nil {
			m.exErr = msg.Err.Error()
		} else {
			m.exList = msg.Examples
			m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
			m.exCursor = 0
		}

	case ExamplesInstalledMsg:
		m.exInstalling = false
		m.exResults = msg.Results

	case tea.KeyPressMsg:
		// When a huh form is active, send keys DIRECTLY to the form so huh
		// can handle tab/enter/up/down/esc for field navigation internally.
		// Only after the form is done do we call handleKey.
		if m.pane == PaneRun && m.runForm != nil && m.runForm.State == huh.StateNormal {
			return m.updateRunForm(msg)
		}
		if m.pane == PaneCreate && m.createForm != nil && m.createForm.State == huh.StateNormal {
			return m.updateCreateForm(msg)
		}
		return m.handleKey(msg)
	}

	// Delegate huh form updates for non-key messages (e.g. window resize)
	if m.pane == PaneRun && m.runForm != nil {
		form, cmd := m.runForm.Update(msg)
		if f, ok := form.(*huh.Form); ok {
			m.runForm = f
			if m.runForm.State == huh.StateCompleted {
				return m, m.startAgent()
			}
			if m.runForm.State == huh.StateAborted {
				m.pane = PaneList
			}
		}
		return m, cmd
	}
	if m.pane == PaneCreate && m.createForm != nil {
		form, cmd := m.createForm.Update(msg)
		if f, ok := form.(*huh.Form); ok {
			m.createForm = f
			if m.createForm.State == huh.StateCompleted {
				return m, m.createAgent()
			}
			if m.createForm.State == huh.StateAborted {
				m.pane = PaneList
			}
		}
		return m, cmd
	}

	// Delegate viewport scroll in stream pane
	if m.pane == PaneStream {
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(msg)
		return m, cmd
	}

	return m, nil
}

func (m AgentsModel) handleKey(msg tea.KeyPressMsg) (AgentsModel, tea.Cmd) {
	key := msg.String()

	switch m.pane {
	case PaneList:
		return m.handleListKey(key)
	case PaneDetail:
		return m.handleDetailKey(key)
	case PaneRun:
		if key == "esc" {
			m.pane = PaneList
			m.runForm = nil
			m.runFormErr = ""
		}
	case PaneStream:
		return m.handleStreamKey(key)
	case PaneDone:
		switch key {
		case "r":
			m.pane = PaneRun
			m.streamLines = nil
			m.executionID = ""
			m.streamStatus = ""
			m.streamErr = ""
			m.runForm = m.buildRunForm()
			return m, m.runForm.Init()
		case "s":
			return m, m.saveOutput()
		case "esc", "q":
			m.pane = PaneList
		}
	case PaneCreate, PaneDeploy:
		if key == "esc" {
			m.pane = PaneList
		}
	case PaneExamples:
		return m.handleExamplesKey(key)
	}
	return m, nil
}

func (m AgentsModel) handleListKey(key string) (AgentsModel, tea.Cmd) {
	if m.searching {
		switch key {
		case "esc", "enter":
			m.searching = false
			m.filtered = filterAgents(m.agents, m.search)
			m.cursor = 0
		case "backspace":
			if len(m.search) > 0 {
				m.search = m.search[:len(m.search)-1]
				m.filtered = filterAgents(m.agents, m.search)
				m.cursor = 0
			}
		default:
			if len(key) == 1 {
				m.search += key
				m.filtered = filterAgents(m.agents, m.search)
				m.cursor = 0
			}
		}
		return m, nil
	}

	if m.delConfirm {
		switch key {
		case "y", "Y", "enter":
			if m.cursor < len(m.filtered) {
				name := m.filtered[m.cursor].Name
				return m, m.deleteAgent(name)
			}
		case "n", "N", "esc":
			m.delConfirm = false
		}
		return m, nil
	}

	switch key {
	case "up", "k":
		// If button bar is focused, move back to table
		if m.btnCursor >= 0 {
			m.btnCursor = -1
		} else if m.cursor > 0 {
			m.cursor--
		}
	case "down", "j":
		// Move to next row; if at bottom, focus button bar
		if m.btnCursor >= 0 {
			// already on button bar, do nothing
		} else if m.cursor < len(m.filtered)-1 {
			m.cursor++
		} else {
			m.btnCursor = 0 // move focus to first button
		}
	case "left", "h":
		if m.btnCursor > 0 {
			m.btnCursor--
		}
	case "right", "l":
		if m.btnCursor >= 0 && m.btnCursor < len(agentListButtons)-1 {
			m.btnCursor++
		}
	case "enter", " ", "space":
		if m.btnCursor >= 0 {
			// Activate the focused button
			return m.activateButton(m.btnCursor)
		}
		// Enter on a table row → detail
		if m.cursor < len(m.filtered) {
			a := m.filtered[m.cursor]
			m.detail = &a
			m.pane = PaneDetail
		}
	// Direct shortcut keys always work regardless of btnCursor
	case "r":
		if m.cursor < len(m.filtered) {
			m.runAgentName = m.filtered[m.cursor].Name
			m.runPrompt = ""
			m.runSessionID = ""
			m.runFormErr = ""
			m.pane = PaneRun
			m.runForm = m.buildRunForm()
			return m, m.runForm.Init()
		}
	case "n":
		m.createName = ""
		m.createModel = "openai/gpt-4o"
		m.pane = PaneCreate
		m.createForm = m.buildCreateForm()
		return m, m.createForm.Init()
	case "E":
		return m.openExamples()
	case "D":
		m.pane = PaneDeploy
	case "d":
		if len(m.filtered) > 0 {
			m.delConfirm = true
		}
	case "R":
		m.loading = true
		m.err = ""
		return m, m.loadAgents()
	case "/":
		m.searching = true
		m.search = ""
		m.btnCursor = -1
	case "esc":
		m.search = ""
		m.filtered = m.agents
		m.cursor = 0
		m.btnCursor = -1
	}
	return m, nil
}

// activateButton executes the action for the given button index.
// updateRunForm routes a key to the run huh form, handling completion/abort.
func (m AgentsModel) updateRunForm(msg tea.Msg) (AgentsModel, tea.Cmd) {
	form, cmd := m.runForm.Update(msg)
	if f, ok := form.(*huh.Form); ok {
		m.runForm = f
		switch m.runForm.State {
		case huh.StateCompleted:
			return m, m.startAgent()
		case huh.StateAborted:
			m.pane = PaneList
			m.runForm = nil
			return m, nil
		}
	}
	return m, cmd
}

// updateCreateForm routes a key to the create huh form, handling completion/abort.
func (m AgentsModel) updateCreateForm(msg tea.Msg) (AgentsModel, tea.Cmd) {
	form, cmd := m.createForm.Update(msg)
	if f, ok := form.(*huh.Form); ok {
		m.createForm = f
		switch m.createForm.State {
		case huh.StateCompleted:
			return m, m.createAgent()
		case huh.StateAborted:
			m.pane = PaneList
			m.createForm = nil
			return m, nil
		}
	}
	return m, cmd
}

func (m AgentsModel) activateButton(idx int) (AgentsModel, tea.Cmd) {
	if idx < 0 || idx >= len(agentListButtons) {
		return m, nil
	}
	switch agentListButtons[idx].Key {
	case "r":
		if m.cursor < len(m.filtered) {
			m.runAgentName = m.filtered[m.cursor].Name
			m.runPrompt = ""
			m.runSessionID = ""
			m.runFormErr = ""
			m.pane = PaneRun
			m.runForm = m.buildRunForm()
			return m, m.runForm.Init()
		}
	case "n":
		m.createName = ""
		m.createModel = "openai/gpt-4o"
		m.pane = PaneCreate
		m.createForm = m.buildCreateForm()
		return m, m.createForm.Init()
	case "E":
		return m.openExamples()
	case "D":
		m.pane = PaneDeploy
	case "d":
		if len(m.filtered) > 0 {
			m.delConfirm = true
		}
	case "/":
		m.searching = true
		m.search = ""
		m.btnCursor = -1
	case "R":
		m.loading = true
		m.err = ""
		return m, m.loadAgents()
	}
	return m, nil
}

func (m AgentsModel) handleDetailKey(key string) (AgentsModel, tea.Cmd) {
	if m.delConfirm {
		switch key {
		case "y", "Y":
			if m.detail != nil {
				return m, m.deleteAgent(m.detail.Name)
			}
		case "n", "N", "esc":
			m.delConfirm = false
		}
		return m, nil
	}
	switch key {
	case "esc", "q":
		m.detail = nil
		m.pane = PaneList
	case "r":
		if m.detail != nil {
			m.runAgentName = m.detail.Name
			m.runPrompt = ""
			m.runSessionID = ""
			m.runFormErr = ""
			m.pane = PaneRun
			m.runForm = m.buildRunForm()
			return m, m.runForm.Init()
		}
	case "d":
		m.delConfirm = true
	}
	return m, nil
}

func (m AgentsModel) handleStreamKey(key string) (AgentsModel, tea.Cmd) {
	switch key {
	case "f":
		m.following = !m.following
		if m.following {
			m.vp.GotoBottom()
		}
	case "ctrl+c":
		m.pane = PaneDone
		m.streamStatus = "STOPPED"
	case "s":
		return m, m.saveOutput()
	default:
		var cmd tea.Cmd
		m.vp, cmd = m.vp.Update(tea.KeyPressMsg(tea.Key{Text: key}))
		return m, cmd
	}
	return m, nil
}

// ─── View ────────────────────────────────────────────────────────────────────

func (m AgentsModel) View() string {
	cw := ui.ContentWidth(m.width)
	ch := ui.ContentHeight(m.height)

	switch m.pane {
	case PaneDetail:
		return m.renderDetail(cw, ch)
	case PaneRun:
		return m.renderRunForm(cw, ch)
	case PaneStream, PaneDone:
		return m.renderStream(cw, ch)
	case PaneCreate:
		return m.renderCreate(cw, ch)
	case PaneDeploy:
		return m.renderDeploy(cw, ch)
	case PaneExamples:
		return m.renderExamples(cw, ch)
	default:
		return m.renderList(cw, ch)
	}
}

func (m AgentsModel) renderList(cw, ch int) string {
	innerW := cw - 4

	// Action button bar — btnCursor highlights the focused button
	actionBar := ui.ButtonBar(agentListButtons, m.btnCursor)

	// Search bar
	var searchBar string
	if m.searching {
		searchBar = "\n" + ui.DimStyle.Render("search: ") +
			lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(m.search+"▌")
	} else if m.search != "" {
		searchBar = "\n" + ui.DimStyle.Render("filter: "+m.search+"  (esc to clear)")
	}

	// Banners
	var banner string
	if m.err != "" {
		if strings.HasPrefix(m.err, "Created ") {
			banner = "\n" + ui.SuccessBanner(innerW, m.err)
		} else {
			banner = "\n" + ui.ErrorBanner(innerW, m.err)
		}
	}
	if m.delConfirm && m.cursor < len(m.filtered) {
		banner += "\n" + lipgloss.NewStyle().Foreground(ui.ColorYellow).Bold(true).
			Render(fmt.Sprintf("  Delete '%s'? [y/N]", m.filtered[m.cursor].Name))
	}

	// Table
	count := ui.DimStyle.Render(fmt.Sprintf(" (%d)", len(m.filtered)))
	heading := ui.SectionHeadingStyle.Render("Registered Agents") + count

	var tableContent string
	if m.loading {
		tableContent = "\n" + ui.DimStyle.Render(fmt.Sprintf("  %s  Loading...", ui.SpinnerFrame(m.tick)))
	} else if len(m.filtered) == 0 {
		if m.search != "" {
			tableContent = "\n" + ui.EmptyState("No agents match '"+m.search+"'.")
		} else {
			tableContent = "\n" + ui.EmptyState("No agents registered.\n\n  n  create a new agent config\n  D  deploy from a Python/TypeScript project")
		}
	} else {
		tableContent = "\n" + m.renderTable(innerW)
	}

	// Navigation hint at bottom
	var navHint string
	if m.btnCursor >= 0 {
		navHint = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "←→", Label: "move"},
			ui.ButtonDef{Key: "enter", Label: "activate"},
			ui.ButtonDef{Key: "↑", Label: "back to list"},
		)
	} else {
		navHint = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "↑↓", Label: "navigate"},
			ui.ButtonDef{Key: "enter", Label: "inspect"},
			ui.ButtonDef{Key: "↓", Label: "focus buttons"},
		)
	}

	body := actionBar + "\n\n" + heading + searchBar + banner + tableContent + navHint
	return ui.ContentPanel(cw, ch, "Agents", body)
}

func (m AgentsModel) renderTable(width int) string {
	descW := width - 22 - 9 - 14 - 14 - 8
	if descW < 8 {
		descW = 8
	}
	colWidths := []int{22, 9, 14, 14, descW}
	headers := []string{"NAME", "VERSION", "TYPE", "UPDATED", "DESCRIPTION"}
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width))

	var rows strings.Builder
	for i, a := range m.filtered {
		updated := "—"
		if a.UpdateTime != nil {
			updated = time.UnixMilli(*a.UpdateTime).Format("2006-01-02")
		}
		cells := []string{
			ui.Truncate(a.Name, colWidths[0]-2),
			fmt.Sprintf("v%d", a.Version),
			ui.Truncate(a.Type, colWidths[2]-2),
			updated,
			ui.Truncate(a.Description, colWidths[4]-2),
		}
		line := renderTableRow(cells, colWidths, false)
		cursor := "  "
		if i == m.cursor {
			cursor = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("▶ ")
			line = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render(line)
		}
		rows.WriteString(cursor + line + "\n")
	}
	return renderTableRow(headers, colWidths, true) + "\n" + sep + "\n" + rows.String()
}

func (m AgentsModel) renderDetail(cw, ch int) string {
	a := m.detail
	innerW := cw - 4

	updated := "—"
	if a.UpdateTime != nil {
		updated = time.UnixMilli(*a.UpdateTime).Format("2006-01-02 15:04")
	}
	tags := "—"
	if len(a.Tags) > 0 {
		tags = strings.Join(a.Tags, ", ")
	}

	rows := []string{
		ui.CardRow("Name:", lipgloss.NewStyle().Bold(true).Foreground(ui.ColorLimeGreen).Render(a.Name)),
		ui.CardRow("Version:", fmt.Sprintf("v%d", a.Version)),
		ui.CardRow("Type:", a.Type),
		ui.CardRow("Updated:", updated),
		ui.CardRow("Tags:", tags),
		ui.CardRow("Checksum:", ui.Truncate(a.Checksum, 24)),
	}
	if a.Description != "" {
		rows = append(rows, "",
			ui.DimStyle.Render("Description:"),
			lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(wordWrap(a.Description, innerW-4)))
	}

	var delLine string
	if m.delConfirm {
		delLine = "\n\n" + lipgloss.NewStyle().Foreground(ui.ColorRed).Bold(true).
			Render(fmt.Sprintf("  Delete '%s'? [y/N]", a.Name))
	}

	actions := "\n\n" + lipgloss.JoinHorizontal(lipgloss.Top,
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Padding(0, 1).
			Border(lipgloss.RoundedBorder()).BorderForeground(ui.ColorDarkGreen).Render("r  Run"),
		"  ",
		lipgloss.NewStyle().Foreground(ui.ColorRed).Padding(0, 1).
			Border(lipgloss.RoundedBorder()).BorderForeground(ui.ColorRed).Render("d  Delete"),
		"  ",
		lipgloss.NewStyle().Foreground(ui.ColorGrey).Padding(0, 1).
			Border(lipgloss.RoundedBorder()).BorderForeground(ui.ColorGrey).Render("esc  Back"),
	)

	body := strings.Join(rows, "\n") + delLine + actions
	return ui.ContentPanel(cw, ch,
		"Agent: "+lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render(a.Name), body)
}

func (m AgentsModel) renderRunForm(cw, ch int) string {
	var content strings.Builder
	if m.runForm != nil && m.runForm.State != huh.StateCompleted {
		content.WriteString(m.runForm.View())
	}
	if m.runFormErr != "" {
		content.WriteString("\n\n" + ui.ErrorBanner(cw-8, m.runFormErr))
	}
	content.WriteString("\n\n" + ui.DimStyle.Render("  tab next field  enter run  esc back to list"))
	return ui.ContentPanel(cw, ch, "Run Agent", content.String())
}

func (m AgentsModel) renderStream(cw, ch int) string {
	innerW := cw - 6
	vpH := ch - 10
	if vpH < 5 {
		vpH = 5
	}
	m.vp.SetWidth(innerW)
	m.vp.SetHeight(vpH)

	statusBadge := ui.StatusBadge(m.streamStatus)
	followStr := ""
	if m.following && m.pane == PaneStream {
		followStr = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("  [↓ following]")
	}
	execHeader := lipgloss.NewStyle().Foreground(ui.ColorWhite).Bold(true).
		Render("Execution: "+components.TruncateID(m.executionID)) +
		"  " + statusBadge + followStr

	vpFrame := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).BorderForeground(ui.ColorDarkGreen).
		Background(ui.ColorDeepBg).
		Width(innerW + 2).Height(vpH + 2).
		Render(m.vp.View())

	var extra string
	if m.streamErr != "" {
		extra = "\n" + ui.ErrorBanner(innerW, m.streamErr)
	} else if m.pane == PaneDone {
		extra = "\n" + ui.SuccessBanner(innerW, "Execution completed.") +
			"\n" + ui.HintBar(
			ui.ButtonDef{Key: "r", Label: "run again"},
			ui.ButtonDef{Key: "s", Label: "save output"},
			ui.ButtonDef{Key: "esc", Label: "back"},
		)
	} else {
		extra = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "↑↓", Label: "scroll"},
			ui.ButtonDef{Key: "f", Label: "follow"},
			ui.ButtonDef{Key: "ctrl+c", Label: "stop", Danger: true},
			ui.ButtonDef{Key: "s", Label: "save"},
		)
	}

	body := execHeader + "\n\n" + vpFrame + extra
	return ui.ContentPanel(cw, ch, "", body)
}

func (m AgentsModel) renderCreate(cw, ch int) string {
	var content strings.Builder
	content.WriteString(ui.DimStyle.Render("Creates a new agent YAML config file you can edit and deploy.\n\n"))
	if m.createForm != nil {
		content.WriteString(m.createForm.View())
	}
	content.WriteString("\n\n" + ui.DimStyle.Render("  After creating, run: agentspan deploy --config <name>.yaml"))
	content.WriteString("\n" + ui.DimStyle.Render("  esc back to list"))
	return ui.ContentPanel(cw, ch, "Create Agent", content.String())
}

func (m AgentsModel) renderDeploy(cw, ch int) string {
	innerW := cw - 8

	intro := ui.DimStyle.Render("Deploy agents from a Python or TypeScript project to the AgentSpan server.\n\n")

	cmdBox := lipgloss.NewStyle().
		Foreground(ui.ColorLimeGreen).
		Border(lipgloss.NormalBorder()).BorderForeground(ui.ColorDarkGreen).
		Padding(0, 2).Width(innerW).
		Render("agentspan deploy [--language python|typescript] [--package <pkg>]")

	steps := "\n\n" + ui.SectionHeadingStyle.Render("What happens:") + "\n" +
		"  " + lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("1") +
		ui.DimStyle.Render("  Discovers agent definitions in your project\n") +
		"  " + lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("2") +
		ui.DimStyle.Render("  Shows what will be deployed (with confirmation)\n") +
		"  " + lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("3") +
		ui.DimStyle.Render("  Registers agents with the AgentSpan server\n") +
		"  " + lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("4") +
		ui.DimStyle.Render("  Agents appear in the list once deployed\n")

	examples := "\n" + ui.SectionHeadingStyle.Render("Examples:") + "\n" +
		lipgloss.NewStyle().Foreground(ui.ColorBrightGrey).
			Render("  agentspan deploy\n") +
		lipgloss.NewStyle().Foreground(ui.ColorBrightGrey).
			Render("  agentspan deploy --language python --package mypackage\n") +
		lipgloss.NewStyle().Foreground(ui.ColorBrightGrey).
			Render("  agentspan deploy --agents agent1,agent2\n")

	body := intro + cmdBox + steps + examples + "\n\n" + ui.DimStyle.Render("  esc back to agents list")
	return ui.ContentPanel(cw, ch, "Deploy Agents", body)
}

// ─── Forms ───────────────────────────────────────────────────────────────────

func (m *AgentsModel) buildRunForm() *huh.Form {
	opts := make([]huh.Option[string], len(m.agents))
	for i, a := range m.agents {
		opts[i] = huh.NewOption(a.Name, a.Name)
	}
	if len(opts) == 0 {
		opts = []huh.Option[string]{huh.NewOption("(no agents registered)", "")}
	}

	return huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Agent").
				Description("Select the registered agent to run").
				Options(opts...).
				Value(&m.runAgentName),
			huh.NewText().
				Title("Prompt").
				Description("What should the agent do?").
				CharLimit(4000).
				Value(&m.runPrompt),
			huh.NewInput().
				Title("Session ID  (optional)").
				Description("Leave blank for a new session").
				Placeholder("sess_abc123").
				Value(&m.runSessionID),
		),
	).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

func (m *AgentsModel) buildCreateForm() *huh.Form {
	return huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("Agent Name").
				Description("A unique identifier (e.g. my-agent, summarizer)").
				Placeholder("my-agent").
				Value(&m.createName),
			huh.NewInput().
				Title("Model").
				Description("LLM to use  (provider/model-name)").
				Placeholder("openai/gpt-4o").
				Value(&m.createModel),
		),
	).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

// ─── Commands ────────────────────────────────────────────────────────────────

func (m AgentsModel) loadAgents() tea.Cmd {
	return func() tea.Msg {
		agents, err := m.client.ListAgents()
		return AgentsLoadedMsg{Agents: agents, Err: err}
	}
}

func (m AgentsModel) deleteAgent(name string) tea.Cmd {
	return func() tea.Msg {
		err := m.client.DeleteAgent(name, nil)
		return AgentDeletedMsg{Name: name, Err: err}
	}
}

func (m AgentsModel) startAgent() tea.Cmd {
	name := m.runAgentName
	prompt := m.runPrompt
	sessionID := m.runSessionID
	c := m.client
	return func() tea.Msg {
		agentDef, err := c.GetAgent(name, nil)
		if err != nil {
			return RunStartedMsg{Err: fmt.Errorf("get agent '%s': %w", name, err)}
		}
		resp, err := c.Start(&client.StartRequest{
			AgentConfig: agentDef,
			Prompt:      prompt,
			SessionID:   sessionID,
		})
		if err != nil {
			return RunStartedMsg{Err: err}
		}
		return RunStartedMsg{ExecutionID: resp.ExecutionID, AgentName: resp.AgentName}
	}
}

func (m AgentsModel) createAgent() tea.Cmd {
	name := m.createName
	model := m.createModel
	return func() tea.Msg {
		if name == "" {
			return AgentCreatedMsg{Err: fmt.Errorf("agent name cannot be empty")}
		}
		filename := name + ".yaml"
		content := fmt.Sprintf("name: %s\ndescription: \"%s agent\"\nmodel: %s\ninstructions: \"You are %s, a helpful AI assistant.\"\nmaxTurns: 25\ntools: []\n",
			name, name, model, name)
		err := os.WriteFile(filename, []byte(content), 0644)
		return AgentCreatedMsg{Filename: filename, Err: err}
	}
}

func (m AgentsModel) startSSE() (AgentsModel, tea.Cmd) {
	ch := &sseChans{
		events: make(chan client.SSEEvent, 200),
		done:   make(chan error, 1),
	}
	m.sseCh = ch
	executionID := m.executionID
	go m.client.Stream(executionID, "", ch.events, ch.done)
	return m, nextSSEEvent(ch)
}

func (m AgentsModel) streamSSE() tea.Cmd {
	if m.sseCh == nil {
		return nil
	}
	return nextSSEEvent(m.sseCh)
}

func (m AgentsModel) saveOutput() tea.Cmd {
	lines := m.streamLines
	execID := m.executionID
	return func() tea.Msg {
		if len(execID) < 8 {
			return nil
		}
		_ = os.WriteFile("output-"+execID[:8]+".txt", []byte(strings.Join(lines, "\n")), 0644)
		return nil
	}
}

// SelectedAgent returns the agent at the cursor (for cross-view navigation).
func (m AgentsModel) SelectedAgent() *client.AgentSummary {
	if m.cursor < len(m.filtered) {
		a := m.filtered[m.cursor]
		return &a
	}
	return nil
}

// FormActive returns true when a huh form is being actively edited.
func (m AgentsModel) FormActive() bool {
	switch m.pane {
	case PaneRun:
		return m.runForm != nil && m.runForm.State == huh.StateNormal
	case PaneCreate:
		return m.createForm != nil && m.createForm.State == huh.StateNormal
	}
	return false
}

// FooterHints returns context-sensitive key hints.
func (m AgentsModel) FooterHints() string {
	switch m.pane {
	case PaneDetail:
		return ui.KeyHint("r", "run") + "  " + ui.KeyHint("d", "delete") + "  " + ui.KeyHint("esc", "back")
	case PaneRun:
		return ui.KeyHint("tab", "next") + "  " + ui.KeyHint("enter", "run") + "  " + ui.KeyHint("esc", "back")
	case PaneStream:
		return ui.KeyHint("↑↓", "scroll") + "  " + ui.KeyHint("f", "follow") + "  " +
			ui.KeyHint("ctrl+c", "stop") + "  " + ui.KeyHint("s", "save")
	case PaneDone:
		return ui.KeyHint("r", "run again") + "  " + ui.KeyHint("s", "save") + "  " + ui.KeyHint("esc", "back")
	case PaneCreate:
		return ui.KeyHint("tab", "next") + "  " + ui.KeyHint("enter", "create") + "  " + ui.KeyHint("esc", "back")
	case PaneDeploy:
		return ui.KeyHint("esc", "back to list")
	case PaneExamples:
		if m.exInstalling {
			return ui.KeyHint("please wait", "installing...")
		}
		if len(m.exResults) > 0 {
			return ui.KeyHint("esc", "back") + "  " + ui.KeyHint("E", "browse more")
		}
		return strings.Join([]string{
			ui.KeyHint("↑↓", "navigate"),
			ui.KeyHint("space", "select"),
			ui.KeyHint("p/t", "filter lang"),
			ui.KeyHint("/", "search"),
			ui.KeyHint("enter", "install selected"),
			ui.KeyHint("esc", "back"),
		}, "  ")
	default:
		return strings.Join([]string{
			ui.KeyHint("↑↓", "navigate"),
			ui.KeyHint("enter", "inspect"),
			ui.KeyHint("r", "run"),
			ui.KeyHint("n", "new"),
			ui.KeyHint("D", "deploy"),
			ui.KeyHint("d", "delete"),
			ui.KeyHint("/", "search"),
			ui.KeyHint("R", "refresh"),
		}, "  ")
	}
}

// ─── Shared helpers (used by agents.go only) ─────────────────────────────────

func filterAgents(agents []client.AgentSummary, query string) []client.AgentSummary {
	if query == "" {
		return agents
	}
	q := strings.ToLower(query)
	var out []client.AgentSummary
	for _, a := range agents {
		if strings.Contains(strings.ToLower(a.Name), q) ||
			strings.Contains(strings.ToLower(a.Type), q) ||
			strings.Contains(strings.ToLower(a.Description), q) {
			out = append(out, a)
		}
	}
	return out
}

func wordWrap(s string, width int) string {
	if width <= 0 {
		return s
	}
	words := strings.Fields(s)
	var lines []string
	var cur strings.Builder
	for _, w := range words {
		if cur.Len()+len(w)+1 > width {
			lines = append(lines, cur.String())
			cur.Reset()
		}
		if cur.Len() > 0 {
			cur.WriteString(" ")
		}
		cur.WriteString(w)
	}
	if cur.Len() > 0 {
		lines = append(lines, cur.String())
	}
	return strings.Join(lines, "\n")
}

// ─── Examples pane ────────────────────────────────────────────────────────────

// openExamples transitions to PaneExamples and starts loading.
func (m AgentsModel) openExamples() (AgentsModel, tea.Cmd) {
	m.pane = PaneExamples
	m.exLoading = true
	m.exErr = ""
	m.exList = nil
	m.exFiltered = nil
	m.exCursor = 0
	m.exSelected = make(map[int]bool)
	m.exResults = nil
	m.exInstalling = false
	m.exLang = ""
	m.exSearch = ""
	m.exSearching = false
	wd, _ := os.Getwd()
	m.exDestDir = wd
	return m, tea.Batch(fetchExamplesCmd(), ui.SpinnerTickCmd())
}

// fetchExamplesCmd fetches the example list from GitHub in a background goroutine.
func fetchExamplesCmd() tea.Cmd {
	return func() tea.Msg {
		exs, err := examples.FetchExampleList()
		if err != nil {
			return ExamplesLoadedMsg{Err: err}
		}
		entries := make([]exampleEntry, len(exs))
		for i, e := range exs {
			entries[i] = exampleEntry{
				Filename:    e.Filename,
				Name:        e.Name,
				Number:      e.Number,
				Language:    string(e.Language),
				Path:        e.Path,
				DownloadURL: e.DownloadURL,
				Tags:        e.Tags,
			}
		}
		return ExamplesLoadedMsg{Examples: entries}
	}
}

// installExamplesCmd downloads, writes, and deploys selected examples.
// Steps per file:
//  1. Download raw content from GitHub
//  2. Write to destDir
//  3. Run the language-appropriate deploy subprocess against destDir
func installExamplesCmd(selected []exampleEntry, destDir string, serverURL string) tea.Cmd {
	return func() tea.Msg {
		exs := make([]examples.Example, len(selected))
		for i, e := range selected {
			exs[i] = examples.Example{
				Filename:    e.Filename,
				Name:        e.Name,
				Number:      e.Number,
				Language:    examples.Language(e.Language),
				Path:        e.Path,
				DownloadURL: e.DownloadURL,
			}
		}

		// Step 1+2: write all files first
		writeResults := examples.InstallExamples(exs, destDir)

		// Step 3: deploy each successfully written file
		var out []exInstallResult
		for _, ex := range exs {
			r := exInstallResult{
				Filename:    ex.Filename,
				WrittenPath: filepath.Join(destDir, ex.Filename),
				Err:         writeResults[ex.Filename],
			}
			if r.Err != nil {
				// File write failed — skip deploy
				out = append(out, r)
				continue
			}

			// Run deploy subprocess for this single file
			deployedName, err := deployExampleFile(r.WrittenPath, string(ex.Language), destDir, serverURL)
			if err != nil {
				r.DeployErr = err
			} else if deployedName == "" {
				r.DeploySkipped = true
			} else {
				r.DeployedName = deployedName
			}
			out = append(out, r)
		}
		return ExamplesInstalledMsg{Results: out}
	}
}

// deployExampleFile runs the language-specific deploy subprocess for a single file.
// Returns the registered agent name, or "" if no agent was found.
// It auto-installs the agentspan SDK if it's not present.
func deployExampleFile(filePath, language, projectDir, serverURL string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()

	// Build subprocess env: inject server URL, suppress auto-start
	filtered := buildDeployEnv(serverURL)

	var data []byte

	switch language {
	case "python":
		pythonBin := findPythonBinaryForDeploy(projectDir)
		if pythonBin == "" {
			return "", fmt.Errorf("Python interpreter not found — install Python 3.10+ or set the PYTHON env var")
		}

		// Check if agentspan SDK is importable; install if missing
		if err := ensurePythonSDK(ctx, pythonBin, filtered); err != nil {
			return "", fmt.Errorf("install agentspan SDK: %w", err)
		}

		cmd := exec.CommandContext(ctx, pythonBin, "-m", "agentspan.cli.deploy",
			"--path", projectDir)
		cmd.Env = filtered
		cmd.Dir = projectDir
		var stdout, stderr strings.Builder
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr
		if runErr := cmd.Run(); runErr != nil && stdout.Len() == 0 {
			errMsg := strings.TrimSpace(stderr.String())
			// Trim the long Python traceback — show last meaningful line
			if lines := strings.Split(errMsg, "\n"); len(lines) > 0 {
				errMsg = lines[len(lines)-1]
			}
			return "", fmt.Errorf("%s", errMsg)
		}
		data = []byte(stdout.String())

	case "typescript":
		deployScript, sdkDir, findErr := findTSDeployScript(projectDir)
		if findErr != nil {
			return "", fmt.Errorf("TypeScript deploy requires Node.js + @agentspan-ai/sdk: %w", findErr)
		}
		// Run npx tsx <deploy.ts> --path <projectDir>
		// Must run from the SDK dir so it resolves @agentspan-ai/sdk from its own node_modules
		cmd := exec.CommandContext(ctx, "npx", "tsx", deployScript, "--path", projectDir)
		cmd.Env = filtered
		cmd.Dir = sdkDir
		var stdout, stderr strings.Builder
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr
		if runErr := cmd.Run(); runErr != nil && stdout.Len() == 0 {
			errMsg := strings.TrimSpace(stderr.String())
			if lines := strings.Split(errMsg, "\n"); len(lines) > 0 {
				errMsg = lines[len(lines)-1]
			}
			return "", fmt.Errorf("%s", errMsg)
		}
		data = []byte(stdout.String())

	default:
		return "", fmt.Errorf("unsupported language: %s", language)
	}

	return parseDeployResultForName(data)
}

// buildDeployEnv constructs the subprocess environment for deploy calls.
func buildDeployEnv(serverURL string) []string {
	env := os.Environ()
	filtered := make([]string, 0, len(env)+3)
	for _, e := range env {
		if !strings.HasPrefix(e, "AGENTSPAN_SERVER_URL=") &&
			!strings.HasPrefix(e, "AGENTSPAN_AUTO_START_SERVER=") {
			filtered = append(filtered, e)
		}
	}
	if serverURL != "" {
		filtered = append(filtered, "AGENTSPAN_SERVER_URL="+serverURL)
	}
	filtered = append(filtered, "AGENTSPAN_AUTO_START_SERVER=false")
	return filtered
}

// ensurePythonSDK checks if `agentspan` is importable with the given Python binary.
// If not, it runs `pip install agentspan` to install it.
func ensurePythonSDK(ctx context.Context, pythonBin string, env []string) error {
	// Quick check: can we import agentspan?
	check := exec.CommandContext(ctx, pythonBin, "-c", "import agentspan")
	check.Env = env
	if check.Run() == nil {
		return nil // already installed
	}

	// Not installed — run pip install agentspan
	// Use a 90s timeout for the pip install
	pipCtx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()

	pip := exec.CommandContext(pipCtx, pythonBin, "-m", "pip", "install", "agentspan", "--quiet")
	pip.Env = env
	var stderr strings.Builder
	pip.Stderr = &stderr
	if err := pip.Run(); err != nil {
		return fmt.Errorf("pip install agentspan failed: %s", strings.TrimSpace(stderr.String()))
	}
	return nil
}

// parseDeployResultForName extracts the first successfully deployed agent name from JSON.
func parseDeployResultForName(data []byte) (string, error) {
	if len(data) == 0 {
		return "", nil
	}
	var results []struct {
		AgentName      string  `json:"agent_name"`
		RegisteredName *string `json:"registered_name"`
		Success        bool    `json:"success"`
		Error          *string `json:"error"`
	}
	if err := json.Unmarshal(data, &results); err != nil {
		// Not JSON or no results — not necessarily an error
		return "", nil
	}
	var names []string
	for _, r := range results {
		if r.Success {
			name := r.AgentName
			if r.RegisteredName != nil && *r.RegisteredName != "" {
				name = *r.RegisteredName
			}
			names = append(names, name)
		}
	}
	if len(names) == 0 {
		return "", nil
	}
	return strings.Join(names, ", "), nil
}

// findPythonBinaryForDeploy finds a Python interpreter (venv or system).
func findPythonBinaryForDeploy(dir string) string {
	if p := os.Getenv("PYTHON"); p != "" {
		return p
	}
	for _, venv := range []string{".venv", "venv"} {
		for _, bin := range []string{"python3", "python"} {
			p := filepath.Join(dir, venv, "bin", bin)
			if _, err := os.Stat(p); err == nil {
				return p
			}
		}
	}
	for _, name := range []string{"python3", "python"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}
	return ""
}

// findTSDeployScript locates the deploy.ts script and its parent SDK directory.
// Returns (deployScript, sdkDir, error).
// It searches node_modules in the project dir, then walks up the tree.
// sdkDir is the directory that contains node_modules for the SDK (so npm
// dependencies resolve correctly when running deploy.ts via npx tsx).
func findTSDeployScript(projectDir string) (deployScript, sdkDir string, err error) {
	// Check npm in project node_modules
	candidates := []struct{ script, sdkDir string }{
		{
			filepath.Join(projectDir, "node_modules", "@agentspan-ai", "sdk", "cli-bin", "deploy.ts"),
			filepath.Join(projectDir, "node_modules", "@agentspan-ai", "sdk"),
		},
		{
			filepath.Join(projectDir, "node_modules", "@agentspan", "sdk", "cli-bin", "deploy.ts"),
			filepath.Join(projectDir, "node_modules", "@agentspan", "sdk"),
		},
	}

	// Walk up from projectDir looking for node_modules/@agentspan-ai/sdk
	cur := projectDir
	for i := 0; i < 5; i++ {
		for _, suffix := range []string{"@agentspan-ai/sdk", "@agentspan/sdk"} {
			sdkPath := filepath.Join(cur, "node_modules", suffix)
			script := filepath.Join(sdkPath, "cli-bin", "deploy.ts")
			candidates = append(candidates, struct{ script, sdkDir string }{script, sdkPath})
		}
		parent := filepath.Dir(cur)
		if parent == cur {
			break
		}
		cur = parent
	}

	for _, c := range candidates {
		if _, statErr := os.Stat(c.script); statErr == nil {
			return c.script, c.sdkDir, nil
		}
	}

	return "", "", fmt.Errorf("deploy.ts not found — run 'npm install @agentspan-ai/sdk' in your project directory")
}

func (m AgentsModel) handleExamplesKey(key string) (AgentsModel, tea.Cmd) {
	// If showing install results
	if len(m.exResults) > 0 {
		switch key {
		case "esc", "q":
			m.pane = PaneList
			m.exResults = nil
		case "E":
			m.exResults = nil
		}
		return m, nil
	}

	if m.exSearching {
		switch key {
		case "esc", "enter":
			m.exSearching = false
			m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
			m.exCursor = 0
		case "backspace":
			if len(m.exSearch) > 0 {
				m.exSearch = m.exSearch[:len(m.exSearch)-1]
				m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
				m.exCursor = 0
			}
		default:
			if len(key) == 1 {
				m.exSearch += key
				m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
				m.exCursor = 0
			}
		}
		return m, nil
	}

	switch key {
	case "up", "k":
		if m.exCursor > 0 {
			m.exCursor--
		}
	case "down", "j":
		if m.exCursor < len(m.exFiltered)-1 {
			m.exCursor++
		}
	case " ", "space", "x":
		// Toggle selection
		if m.exSelected == nil {
			m.exSelected = make(map[int]bool)
		}
		m.exSelected[m.exCursor] = !m.exSelected[m.exCursor]
	case "a":
		// Select all / deselect all
		if m.exSelected == nil {
			m.exSelected = make(map[int]bool)
		}
		if len(m.exSelected) == len(m.exFiltered) {
			m.exSelected = make(map[int]bool)
		} else {
			for i := range m.exFiltered {
				m.exSelected[i] = true
			}
		}
	case "p":
		// Filter Python only
		if m.exLang == "python" {
			m.exLang = ""
		} else {
			m.exLang = "python"
		}
		m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
		m.exCursor = 0
		m.exSelected = make(map[int]bool)
	case "t":
		// Filter TypeScript only
		if m.exLang == "typescript" {
			m.exLang = ""
		} else {
			m.exLang = "typescript"
		}
		m.exFiltered = filterExamples(m.exList, m.exLang, m.exSearch)
		m.exCursor = 0
		m.exSelected = make(map[int]bool)
	case "/":
		m.exSearching = true
		m.exSearch = ""
	case "enter":
		// Install selected examples
		if len(m.exSelected) == 0 {
			// If nothing selected, select current
			if m.exSelected == nil {
				m.exSelected = make(map[int]bool)
			}
			m.exSelected[m.exCursor] = true
		}
		var toInstall []exampleEntry
		for i, sel := range m.exSelected {
			if sel && i < len(m.exFiltered) {
				toInstall = append(toInstall, m.exFiltered[i])
			}
		}
		if len(toInstall) > 0 {
			m.exInstalling = true
			return m, installExamplesCmd(toInstall, m.exDestDir, m.serverURL)
		}
	case "esc", "q":
		m.pane = PaneList
	}
	return m, nil
}

func (m AgentsModel) renderExamples(cw, ch int) string {
	innerW := cw - 4

	// Title + filter bar
	title := ui.SectionHeadingStyle.Render("Install Examples")

	// Language filter pills
	pyActive := m.exLang == "python"
	tsActive := m.exLang == "typescript"
	filterBar := lipgloss.JoinHorizontal(lipgloss.Top,
		ui.Button("p  🐍 Python", pyActive, false),
		" ",
		ui.Button("t  📘 TypeScript", tsActive, false),
		"    ",
		ui.DimStyle.Render("/ search  a select all  space toggle  enter install"),
	)

	// Search
	var searchBar string
	if m.exSearching {
		searchBar = "\n" + ui.DimStyle.Render("search: ") +
			lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(m.exSearch+"▌")
	} else if m.exSearch != "" {
		searchBar = "\n" + ui.DimStyle.Render("filter: "+m.exSearch+"  esc clear")
	}

	// Body
	var body string

	switch {
	case m.exInstalling:
		body = "\n" + lipgloss.NewStyle().Foreground(ui.ColorYellow).
			Render(ui.SpinnerFrame(m.spinTick)+"  Downloading, installing and deploying examples...") +
			"\n\n" + ui.DimStyle.Render("Steps per file:") +
			"\n" + ui.DimStyle.Render("  1. Fetch from GitHub") +
			"\n" + ui.DimStyle.Render("  2. Write to current directory") +
			"\n" + ui.DimStyle.Render("  3. Check agentspan SDK (pip install if missing — may take 30s)") +
			"\n" + ui.DimStyle.Render("  4. Deploy agent to server") +
			"\n\n" + ui.DimStyle.Render("Please wait...")

	case len(m.exResults) > 0:
		body = m.renderInstallResults(innerW)

	case m.exLoading:
		body = "\n" + ui.DimStyle.Render(ui.SpinnerFrame(m.spinTick)+"  Fetching examples from GitHub...") +
			"\n\n" + ui.DimStyle.Render("Connecting to github.com/agentspan-ai/agentspan")

	case m.exErr != "":
		body = "\n" + ui.ErrorBanner(innerW, m.exErr) +
			"\n\n" + ui.DimStyle.Render("Check your internet connection and try again (esc to go back).")

	default:
		body = "\n" + m.renderExamplesList(innerW)
	}

	// Selection count
	var selCount string
	if len(m.exSelected) > 0 {
		n := 0
		for _, v := range m.exSelected {
			if v {
				n++
			}
		}
		if n > 0 {
			selCount = "\n" + lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).
				Render(fmt.Sprintf("  %d example(s) selected — press enter to install to %s", n, m.exDestDir))
		}
	}

	full := title + "\n" + filterBar + searchBar + body + selCount
	return ui.ContentPanel(cw, ch, "", full)
}

func (m AgentsModel) renderExamplesList(width int) string {
	if len(m.exFiltered) == 0 {
		if len(m.exList) == 0 {
			return ui.EmptyState("No examples loaded.")
		}
		return ui.EmptyState("No examples match the current filter.")
	}

	// Table header
	colNum := 5
	colLang := 4
	colName := 30
	colTags := width - colNum - colLang - colName - 8
	if colTags < 8 {
		colTags = 8
	}

	header := lipgloss.JoinHorizontal(lipgloss.Top,
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(2).Render(""),
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(colNum).Render("#"),
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(colLang).Render(""),
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(colName).Render("NAME"),
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Render("TAGS"),
	)
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width))

	var rows strings.Builder
	// Show a window of rows around the cursor
	pageH := 20
	start := m.exCursor - pageH/2
	if start < 0 {
		start = 0
	}
	end := start + pageH
	if end > len(m.exFiltered) {
		end = len(m.exFiltered)
		start = end - pageH
		if start < 0 {
			start = 0
		}
	}

	for i := start; i < end; i++ {
		e := m.exFiltered[i]
		isCursor := i == m.exCursor
		isSelected := m.exSelected[i]

		// Checkbox
		checkBox := "  "
		if isSelected {
			checkBox = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Render("✓ ")
		} else if isCursor {
			checkBox = lipgloss.NewStyle().Foreground(ui.ColorGrey).Render("○ ")
		}

		// Language icon
		langIcon := "🐍"
		if e.Language == "typescript" {
			langIcon = "📘"
		}

		// Tags
		tagStr := ""
		if len(e.Tags) > 0 {
			tagStr = strings.Join(e.Tags, " · ")
		}

		numStyle := lipgloss.NewStyle().Foreground(ui.ColorBrightGrey).Width(colNum)
		nameStyle := lipgloss.NewStyle().Foreground(ui.ColorWhite).Width(colName)
		tagStyle := lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true)

		if isCursor {
			numStyle = numStyle.Foreground(ui.ColorLimeGreen)
			nameStyle = nameStyle.Foreground(ui.ColorLimeGreen).Bold(true)
			tagStyle = tagStyle.Foreground(ui.ColorBrightGrey).Faint(false)
		}
		if isSelected {
			nameStyle = nameStyle.Foreground(ui.ColorLimeGreen)
		}

		line := checkBox +
			numStyle.Render(e.Number) +
			lipgloss.NewStyle().Width(colLang).Render(langIcon) +
			nameStyle.Render(ui.Truncate(e.Name, colName-2)) +
			tagStyle.Render(ui.Truncate(tagStr, colTags))

		rows.WriteString(line + "\n")
	}

	// Pagination info
	total := len(m.exFiltered)
	pageInfo := ui.DimStyle.Render(fmt.Sprintf("  %d–%d of %d examples", start+1, end, total))

	return header + "\n" + sep + "\n" + rows.String() + pageInfo
}

func (m AgentsModel) renderInstallResults(width int) string {
	var sb strings.Builder
	sb.WriteString("\n")

	// Column widths
	fileCol := 32
	deployCol := width - fileCol - 6
	if deployCol < 20 {
		deployCol = 20
	}

	// Header
	sb.WriteString(
		lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(fileCol).Render("FILE") +
			lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).Width(fileCol).Render("DEPLOY STATUS") + "\n")
	sb.WriteString(lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).
		Render(strings.Repeat("─", width-4)) + "\n")

	okWrite, failWrite, okDeploy, failDeploy, skipDeploy := 0, 0, 0, 0, 0

	for _, r := range m.exResults {
		var filePart, deployPart string

		if r.Err != nil {
			failWrite++
			filePart = lipgloss.NewStyle().Foreground(ui.ColorRed).Width(fileCol).
				Render("✗ " + ui.Truncate(r.Filename, fileCol-4))
			deployPart = lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true).
				Render("skipped (write failed)")
		} else {
			okWrite++
			filePart = lipgloss.NewStyle().Foreground(ui.ColorGreen).Width(fileCol).
				Render("✓ " + ui.Truncate(r.Filename, fileCol-4))

			switch {
			case r.DeploySkipped:
				skipDeploy++
				deployPart = lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true).
					Render("– no agents found in file")
			case r.DeployErr != nil:
				failDeploy++
				deployPart = lipgloss.NewStyle().Foreground(ui.ColorRed).
					Render("✗ " + ui.Truncate(r.DeployErr.Error(), deployCol-4))
			case r.DeployedName != "":
				okDeploy++
				deployPart = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Bold(true).
					Render("● " + r.DeployedName)
			default:
				deployPart = lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true).
					Render("– not deployed")
			}
		}

		sb.WriteString(filePart + deployPart + "\n")
	}

	sb.WriteString("\n")

	// Summary
	if failWrite == 0 && failDeploy == 0 {
		line := fmt.Sprintf("%d file(s) written, %d agent(s) deployed to server", okWrite, okDeploy)
		if skipDeploy > 0 {
			line += fmt.Sprintf("  (%d file(s) had no agents)", skipDeploy)
		}
		sb.WriteString(ui.SuccessBanner(width, line))
	} else {
		parts := []string{}
		if okWrite > 0 {
			parts = append(parts, fmt.Sprintf("%d written", okWrite))
		}
		if failWrite > 0 {
			parts = append(parts, fmt.Sprintf("%d write failed", failWrite))
		}
		if okDeploy > 0 {
			parts = append(parts, fmt.Sprintf("%d deployed", okDeploy))
		}
		if failDeploy > 0 {
			parts = append(parts, fmt.Sprintf("%d deploy failed", failDeploy))
		}
		sb.WriteString(ui.WarnStyle.Render("  " + strings.Join(parts, "  ·  ")))
	}

	sb.WriteString("\n\n")
	if okDeploy > 0 {
		sb.WriteString(lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).
			Render("  Agents are registered and ready — press 2 to go to Agents view\n"))
	}
	sb.WriteString(ui.DimStyle.Render("  esc back to agents  E browse more examples"))
	return sb.String()
}

// filterExamples filters the example list by language and search query.
func filterExamples(list []exampleEntry, lang, query string) []exampleEntry {
	var out []exampleEntry
	q := strings.ToLower(query)
	for _, e := range list {
		if lang != "" && e.Language != lang {
			continue
		}
		if q != "" {
			lower := strings.ToLower(e.Name + " " + e.Filename + " " + strings.Join(e.Tags, " "))
			if !strings.Contains(lower, q) {
				continue
			}
		}
		out = append(out, e)
	}
	return out
}

// NewAgentsRunWithConfig creates agents model in run mode with serverURL for deploy.
func NewAgentsRunWithConfig(c *client.Client, preselected, serverURL string) AgentsModel {
	m := NewAgentsWithConfig(c, serverURL)
	m.runAgentName = preselected
	m.pane = PaneRun
	return m
}

// ─── Test accessors (exported for tui package tests) ─────────────────────────

func (m AgentsModel) Cursor() int        { return m.cursor }
func (m AgentsModel) BtnCursor() int     { return m.btnCursor }
func (m AgentsModel) Searching() bool    { return m.searching }
func (m AgentsModel) Search() string     { return m.search }
func (m AgentsModel) Pane() AgentsPane   { return m.pane }
func (m AgentsModel) DelConfirm() bool   { return m.delConfirm }
func (m AgentsModel) RunAgentName() string { return m.runAgentName }
func (m AgentsModel) ExLang() string     { return m.exLang }
func (m AgentsModel) ExSearching() bool  { return m.exSearching }
func (m AgentsModel) ExSearch() string   { return m.exSearch }
func (m AgentsModel) ExSelected() map[int]bool { return m.exSelected }
func (m AgentsModel) ExLoading() bool    { return m.exLoading }

func (m *AgentsModel) SetFiltered(agents []AgentsTestEntry) {
	m.filtered = make([]client.AgentSummary, len(agents))
	m.agents = make([]client.AgentSummary, len(agents))
	for i, a := range agents {
		m.filtered[i] = client.AgentSummary{Name: a.Name}
		m.agents[i] = m.filtered[i]
	}
}

func (m *AgentsModel) SetExList(entries []AgentExampleEntry) {
	m.exList = make([]exampleEntry, len(entries))
	m.exFiltered = make([]exampleEntry, len(entries))
	for i, e := range entries {
		m.exList[i] = exampleEntry{Filename: e.Filename, Name: e.Name, Language: e.Language, Number: e.Number}
		m.exFiltered[i] = m.exList[i]
	}
	m.exLoading = false
	m.exSelected = make(map[int]bool)
}

// AgentExampleEntry is a test helper type.
type AgentExampleEntry struct {
	Filename, Name, Language, Number string
}

// agentsTestEntry is a simple struct for injecting test agents.
type AgentsTestEntry struct{ Name string }
type agentsTestEntry = AgentsTestEntry // backward compat

// WantsEsc returns true if the view wants to handle esc internally
// (e.g. to close a sub-pane or exit search mode) rather than returning
// to the sidebar.
func (m AgentsModel) WantsEsc() bool {
	switch m.pane {
	case PaneList:
		return m.searching || m.delConfirm || m.search != ""
	case PaneDetail, PaneRun, PaneCreate, PaneDeploy, PaneExamples:
		return true // esc navigates within the view
	case PaneDone, PaneStream:
		return true
	}
	return false
}
