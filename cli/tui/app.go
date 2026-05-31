package tui

import (
	"fmt"
	"image/color"
	"math"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/agentspan-ai/agentspan/cli/tui/components"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
	"github.com/agentspan-ai/agentspan/cli/tui/views"
)

// NavigateMsg requests navigation to a specific view.
type NavigateMsg struct {
	View        ViewID
	ExecutionID string
	AgentName   string
	OpenRun     bool
}

// AppModel is the root BubbleTea model.
type AppModel struct {
	nav            NavModel
	width          int
	height         int
	showHelp       bool
	version        string
	contentFocused bool // true = content panel has focus, false = sidebar
	themeLocked    bool // true when theme was set explicitly by env or ctrl+t

	// Views (run+deploy merged into agents)
	dashboard   views.DashboardModel
	agents      views.AgentsModel
	executions  views.ExecutionsModel
	status      views.StatusModel
	server      views.ServerModel
	credentials views.CredentialsModel
	doctor      views.DoctorModel
	configure   views.ConfigureModel
	skills      views.SkillsModel

	activeView     ViewID
	client         *client.Client
	cfg            *config.Config
	serverHealthy  bool
	serverChecking bool
}

type themeSelection struct {
	isDark bool
	locked bool
}

var (
	runtimeGOOS          = runtime.GOOS
	queryBackgroundColor = func() (color.Color, error) {
		return lipgloss.BackgroundColor(os.Stdin, os.Stdout)
	}
	readAppleTerminalProfile = func(key string) (string, error) {
		out, err := exec.Command("defaults", "read", "com.apple.Terminal", key).Output()
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(string(out)), nil
	}
)

// New creates the root App model.
func New(version string) *AppModel {
	cfg := config.Load()
	c := client.New(cfg)

	m := &AppModel{
		nav:            NewNav(),
		version:        version,
		activeView:     ViewDashboard,
		client:         c,
		cfg:            cfg,
		serverChecking: true,
		contentFocused: false, // sidebar has focus on startup
	}

	m.dashboard = views.NewDashboard(c)
	m.agents = views.NewAgentsWithConfig(c, cfg.ServerURL)
	m.executions = views.NewExecutions(c)
	m.status = views.NewStatus(c, "")
	m.server = views.NewServer(c)
	m.credentials = views.NewCredentials(c)
	m.doctor = views.NewDoctor(c)
	m.configure = views.NewConfigure(cfg)
	m.skills = views.NewSkills(c)

	return m
}

func (m *AppModel) Init() tea.Cmd {
	return tea.Batch(
		m.dashboard.Init(),
		m.server.Init(),
	)
}

func (m *AppModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	// ── Terminal background detection ─────────────────────────────────────
	case tea.BackgroundColorMsg:
		if !m.themeLocked {
			ui.SetTheme(msg.IsDark())
		}
		return m, nil

	// ── Window resize ──────────────────────────────────────────────────────
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.nav, _ = m.nav.Update(msg)
		var cmds []tea.Cmd
		var cmd tea.Cmd
		m.dashboard, cmd = m.dashboard.Update(msg)
		cmds = append(cmds, cmd)
		m.agents, cmd = m.agents.Update(msg)
		cmds = append(cmds, cmd)
		m.executions, cmd = m.executions.Update(msg)
		cmds = append(cmds, cmd)
		m.status, cmd = m.status.Update(msg)
		cmds = append(cmds, cmd)
		m.server, cmd = m.server.Update(msg)
		cmds = append(cmds, cmd)
		m.credentials, cmd = m.credentials.Update(msg)
		cmds = append(cmds, cmd)
		m.doctor, cmd = m.doctor.Update(msg)
		cmds = append(cmds, cmd)
		m.configure, cmd = m.configure.Update(msg)
		cmds = append(cmds, cmd)
		m.skills, cmd = m.skills.Update(msg)
		cmds = append(cmds, cmd)
		return m, tea.Batch(cmds...)

	// ── Nav selected a view — always focus content after selection ───────────
	case NavSelectMsg:
		newModel, cmd := m.handleNavigation(NavigateMsg{View: msg.View})
		newModel.(*AppModel).contentFocused = true
		return newModel, cmd

	// ── Content panel now has focus (tab was pressed in sidebar) ──────────
	case FocusContent:
		m.contentFocused = true
		return m, nil

	// ── Programmatic navigation ────────────────────────────────────────────
	case NavigateMsg:
		return m.handleNavigation(msg)

	// ── Server health updates ──────────────────────────────────────────────
	case views.ServerHealthMsg:
		m.serverChecking = false
		m.serverHealthy = msg.Healthy
		m.nav.healthy = msg.Healthy
		m.nav.checking = false
		var cmd tea.Cmd
		m.dashboard, cmd = m.dashboard.Update(msg)
		return m, cmd

	// ── Key presses ────────────────────────────────────────────────────────
	case tea.KeyPressMsg:
		return m.handleKeyPress(msg)
	}

	// Everything else → active view
	return m.delegateToActiveView(msg)
}

// handleKeyPress implements the key routing logic:
//
//	Global (always):
//	  ctrl+c       → quit
//	  ?            → toggle help overlay
//
//	Help overlay open:
//	  any key      → close help
//
//	Content focused:
//	  esc / shift+tab → return focus to sidebar
//	  all other keys  → active view
//
//	Sidebar focused (default):
//	  ↑ / k        → move nav cursor up
//	  ↓ / j        → move nav cursor down
//	  enter / space → load selected view, keep sidebar focus
//	  tab          → load selected view AND move focus to content
//	  q            → quit
//	  1-0          → jump to numbered view
//	  all other    → active view (so 'r', 's', etc. still work from sidebar)
func (m *AppModel) handleKeyPress(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// ── Always-active globals ──────────────────────────────────────────────
	switch key {
	case "ctrl+c":
		return m, tea.Quit
	case "ctrl+t":
		m.themeLocked = true
		ui.SetTheme(!ui.IsDarkBackground)
		return m, nil
	case "?":
		m.showHelp = !m.showHelp
		return m, nil
	}

	// ── Help overlay: any key closes it ───────────────────────────────────
	if m.showHelp {
		m.showHelp = false
		return m, nil
	}

	// ── Content panel has focus ────────────────────────────────────────────
	if m.contentFocused {
		// If the active view has an embedded huh form (tab/enter/esc go to form)
		// or wants to handle esc internally (sub-pane, search mode), send ALL
		// keys to the view first. Only ctrl+c bypasses this.
		if m.activeViewWantsAllKeys() || (key == "esc" && m.activeViewWantsEsc()) {
			newModel, cmd := m.delegateToActiveView(msg)
			return newModel, cmd
		}

		switch key {
		case "esc", "shift+tab":
			// Return focus to sidebar
			m.contentFocused = false
			return m, nil
		case "q":
			// q in content = back to sidebar
			m.contentFocused = false
			return m, nil
		}
		// All other keys go to active view
		newModel, cmd := m.delegateToActiveView(msg)
		m2 := newModel.(*AppModel)
		// Check if this key should trigger cross-view navigation.
		// Apply it synchronously so the view transition is immediate.
		if nav := m2.checkViewNav(key); nav != nil {
			navModel, navCmd := m2.handleNavigation(*nav)
			navModel.(*AppModel).contentFocused = true
			return navModel, tea.Batch(cmd, navCmd)
		}
		return newModel, cmd
	}

	// ── Sidebar has focus (default) ────────────────────────────────────────
	switch key {
	case "up", "k", "down", "j":
		// Move sidebar cursor only — does NOT load the view yet
		var navCmd tea.Cmd
		m.nav, navCmd = m.nav.Update(msg)
		return m, navCmd

	case "enter", " ", "tab":
		// Load the highlighted view AND move focus to content.
		// Both enter and tab do the same thing: select + focus content.
		selectedView := m.nav.items[m.nav.cursor].ID
		newModel, navCmd := m.handleNavigation(NavigateMsg{View: selectedView})
		m2 := newModel.(*AppModel)
		m2.contentFocused = true
		return m2, navCmd

	case "q":
		return m, tea.Quit

	// Number shortcuts → match the 8-item sidebar order and focus content
	case "1":
		return m.jumpTo(ViewDashboard)
	case "2":
		return m.jumpTo(ViewAgents)
	case "3":
		return m.jumpTo(ViewExecutions)
	case "4":
		return m.jumpTo(ViewServer)
	case "5":
		return m.jumpTo(ViewSkills)
	case "6":
		return m.jumpTo(ViewCredentials)
	case "7":
		return m.jumpTo(ViewDoctor)
	case "8":
		return m.jumpTo(ViewConfigure)

	default:
		// Any other key passes to active view; apply cross-view nav synchronously.
		newModel, cmd := m.delegateToActiveView(msg)
		m2 := newModel.(*AppModel)
		if nav := m2.checkViewNav(key); nav != nil {
			navModel, navCmd := m2.handleNavigation(*nav)
			navModel.(*AppModel).contentFocused = true
			return navModel, tea.Batch(cmd, navCmd)
		}
		return newModel, cmd
	}
}

// checkViewNav returns a NavigateMsg if the given key should trigger cross-view
// navigation from the currently active view. Returns nil if no navigation needed.
func (m *AppModel) checkViewNav(key string) *NavigateMsg {
	switch m.activeView {
	case ViewDashboard:
		switch key {
		case "r":
			return &NavigateMsg{View: ViewAgents, OpenRun: true}
		case "enter":
			if id := m.dashboard.SelectedExecutionID(); id != "" {
				return &NavigateMsg{View: ViewExecutions, ExecutionID: id}
			}
		case "s":
			if m.dashboard.SelectedIsRunning() {
				if id := m.dashboard.SelectedExecutionID(); id != "" {
					return &NavigateMsg{View: ViewAgents, ExecutionID: id}
				}
			}
		}
	case ViewExecutions:
		if key == "enter" {
			if id := m.executions.SelectedExecutionID(); id != "" {
				return &NavigateMsg{View: ViewExecutions, ExecutionID: id}
			}
		}
		if key == "s" && m.executions.WantsStream("s") {
			if id := m.executions.SelectedExecutionID(); id != "" {
				return &NavigateMsg{View: ViewAgents, ExecutionID: id,
					AgentName: "stream:" + m.cfg.ServerURL}
			}
		}
	}
	return nil
}

// jumpTo navigates to a view via number shortcut and focuses content immediately.
func (m *AppModel) jumpTo(v ViewID) (tea.Model, tea.Cmd) {
	newModel, cmd := m.handleNavigation(NavigateMsg{View: v})
	newModel.(*AppModel).contentFocused = true
	return newModel, cmd
}

// handleNavigation switches to a view and re-initialises it.
// It immediately fires a WindowSizeMsg so the new view gets correct dimensions.
func (m *AppModel) handleNavigation(nav NavigateMsg) (tea.Model, tea.Cmd) {
	m.activeView = nav.View
	m.nav.SetActive(nav.View)

	// After creating a fresh view model we synthesise a WindowSizeMsg so it
	// knows the current terminal dimensions immediately (not zero).
	sizeMsg := tea.WindowSizeMsg{Width: m.width, Height: m.height}

	var initCmd tea.Cmd
	switch nav.View {
	case ViewDashboard:
		m.dashboard = views.NewDashboard(m.client)
		m.dashboard, _ = m.dashboard.Update(sizeMsg)
		initCmd = m.dashboard.Init()
	case ViewAgents:
		if nav.ExecutionID != "" && strings.HasPrefix(nav.AgentName, "stream:") {
			// Reconnect to an existing running execution's SSE stream
			serverURL := strings.TrimPrefix(nav.AgentName, "stream:")
			m.agents = views.NewAgentsStream(m.client, nav.ExecutionID, "", serverURL)
		} else if nav.OpenRun {
			m.agents = views.NewAgentsRunWithConfig(m.client, nav.AgentName, m.cfg.ServerURL)
		} else {
			m.agents = views.NewAgentsWithConfig(m.client, m.cfg.ServerURL)
		}
		m.agents, _ = m.agents.Update(sizeMsg)
		initCmd = m.agents.Init()
	case ViewExecutions:
		if nav.ExecutionID != "" {
			m.status = views.NewStatus(m.client, nav.ExecutionID)
			m.status, _ = m.status.Update(sizeMsg)
			initCmd = m.status.Init()
		} else {
			m.status = views.NewStatus(m.client, "")
			m.executions = views.NewExecutions(m.client)
			m.executions, _ = m.executions.Update(sizeMsg)
			initCmd = m.executions.Init()
		}
	case ViewServer:
		m.server = views.NewServer(m.client)
		m.server, _ = m.server.Update(sizeMsg)
		initCmd = m.server.Init()
	case ViewCredentials:
		m.credentials = views.NewCredentials(m.client)
		m.credentials, _ = m.credentials.Update(sizeMsg)
		initCmd = m.credentials.Init()
	case ViewDoctor:
		m.doctor = views.NewDoctor(m.client)
		m.doctor, _ = m.doctor.Update(sizeMsg)
		initCmd = m.doctor.Init()
	case ViewConfigure:
		m.configure = views.NewConfigure(m.cfg)
		m.configure, _ = m.configure.Update(sizeMsg)
		initCmd = m.configure.Init()
	case ViewSkills:
		m.skills = views.NewSkills(m.client)
		m.skills, _ = m.skills.Update(sizeMsg)
		initCmd = m.skills.Init()
	}
	return m, initCmd
}

// activeViewWantsEsc returns true when the active view has internal state
// that esc should clear (search mode, sub-panes, confirm dialogs) rather
// than returning focus to the sidebar.
func (m *AppModel) activeViewWantsEsc() bool {
	switch m.activeView {
	case ViewAgents:
		return m.agents.WantsEsc()
	case ViewExecutions:
		return m.executions.WantsEsc()
	case ViewServer:
		return m.server.WantsEsc()
	case ViewCredentials:
		return m.credentials.WantsEsc()
	}
	return false
}

// activeViewWantsAllKeys returns true when the active view has an embedded
// huh form that is currently being edited. In that state ALL keys (including
// esc, tab, enter, arrows) must be forwarded to the view so the form works.
func (m *AppModel) activeViewWantsAllKeys() bool {
	switch m.activeView {
	case ViewConfigure:
		return m.configure.FormActive()
	case ViewAgents:
		return m.agents.FormActive()
	case ViewCredentials:
		return m.credentials.FormActive()
	}
	return false
}

// delegateToActiveView sends a message to the currently displayed view.
func (m *AppModel) delegateToActiveView(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch m.activeView {
	case ViewDashboard:
		m.dashboard, cmd = m.dashboard.Update(msg)
	case ViewAgents:
		m.agents, cmd = m.agents.Update(msg)
	case ViewExecutions:
		if m.status.IsLoaded() {
			m.status, cmd = m.status.Update(msg)
		} else {
			m.executions, cmd = m.executions.Update(msg)
		}
	case ViewServer:
		m.server, cmd = m.server.Update(msg)
	case ViewCredentials:
		m.credentials, cmd = m.credentials.Update(msg)
	case ViewDoctor:
		m.doctor, cmd = m.doctor.Update(msg)
	case ViewConfigure:
		m.configure, cmd = m.configure.Update(msg)
	case ViewSkills:
		m.skills, cmd = m.skills.Update(msg)
	}
	return m, cmd
}

// View renders the full screen.
func (m *AppModel) View() tea.View {
	if m.width == 0 {
		v := tea.NewView("Loading agentspan...")
		v.AltScreen = true
		return v
	}

	statusStr := "● live"
	if m.serverChecking {
		statusStr = "⟳ checking"
	} else if !m.serverHealthy {
		statusStr = "◌ offline"
	}

	header := ui.RenderHeader(m.width, m.version, statusStr)
	footer := ui.RenderFooter(m.width, m.footerHints())

	// Help overlay
	if m.showHelp {
		helpContent := components.HelpOverlay(m.width-4, m.height-4)
		screen := ui.WrapScreen(header+"\n"+helpContent+"\n"+footer, m.width, m.height)
		v := tea.NewView(screen)
		v.AltScreen = true
		return v
	}

	m.nav.height = m.height

	sidebar := m.nav.View(m.contentFocused)
	content := m.renderActiveView()
	body := ui.RenderLayout(m.width, m.height, sidebar, content)

	// header + body + footer: each lipgloss render ends without \n,
	// so we add exactly one \n between each to stack them as rows.
	screen := ui.WrapScreen(header+"\n"+body+"\n"+footer, m.width, m.height)
	v := tea.NewView(screen)
	v.AltScreen = true
	return v
}

func (m *AppModel) renderActiveView() string {
	switch m.activeView {
	case ViewDashboard:
		return m.dashboard.View()
	case ViewAgents:
		return m.agents.View()
	case ViewExecutions:
		if m.status.IsLoaded() {
			return m.status.View()
		}
		return m.executions.View()
	case ViewServer:
		return m.server.View()
	case ViewCredentials:
		return m.credentials.View()
	case ViewDoctor:
		return m.doctor.View()
	case ViewConfigure:
		return m.configure.View()
	case ViewSkills:
		return m.skills.View()
	}
	return ""
}

// footerHints returns context-sensitive key hints.
func (m *AppModel) footerHints() string {
	if !m.contentFocused {
		// Sidebar mode — arrow keys move cursor, enter opens view
		theme := "dark"
		if ui.IsDarkBackground {
			theme = "light"
		}
		return ui.KeyHint("↑↓", "navigate") + "  " +
			ui.KeyHint("enter", "open view") + "  " +
			ui.KeyHint("1-0", "jump") + "  " +
			ui.KeyHint("ctrl+t", theme) + "  " +
			ui.KeyHint("?", "help") + "  " +
			ui.KeyHint("q", "quit")
	}

	// Content focused mode — show view-specific hints
	var viewHints string
	switch m.activeView {
	case ViewDashboard:
		viewHints = m.dashboard.FooterHints()
	case ViewAgents:
		viewHints = m.agents.FooterHints()
	case ViewExecutions:
		if m.status.IsLoaded() {
			viewHints = m.status.FooterHints()
		} else {
			viewHints = m.executions.FooterHints()
		}
	case ViewServer:
		viewHints = m.server.FooterHints()
	case ViewCredentials:
		viewHints = m.credentials.FooterHints()
	case ViewDoctor:
		viewHints = m.doctor.FooterHints()
	case ViewConfigure:
		viewHints = m.configure.FooterHints()
	case ViewSkills:
		viewHints = m.skills.FooterHints()
	default:
		viewHints = ui.KeyHint("q", "quit")
	}
	return viewHints + "  " + ui.KeyHint("esc", "sidebar") + "  " + ui.KeyHint("?", "help")
}

// detectInitialTheme returns the initial theme selection for the app.
// AGENTSPAN_THEME=light|dark pins the palette until the user changes it.
// Otherwise we auto-detect from terminal metadata.
func detectInitialTheme() themeSelection {
	if t := strings.TrimSpace(os.Getenv("AGENTSPAN_THEME")); t != "" {
		switch strings.ToLower(t) {
		case "light":
			return themeSelection{isDark: false, locked: true}
		case "dark":
			return themeSelection{isDark: true, locked: true}
		case "auto":
			return themeSelection{isDark: detectDarkBackground()}
		}
	}
	return themeSelection{isDark: detectDarkBackground()}
}

// detectDarkBackground checks whether the terminal has a dark background.
// It tries the COLORFGBG convention first and then falls back to the OSC 11
// terminal query via lipgloss. Defaults to true (dark) if nothing works.
func detectDarkBackground() bool {
	// 1. COLORFGBG env var (set by Terminal.app, iTerm2, xterm, etc.)
	//    Format: "foreground;background" where background >= 8 is typically light.
	if colorfgbg := os.Getenv("COLORFGBG"); colorfgbg != "" {
		parts := strings.Split(colorfgbg, ";")
		if len(parts) >= 2 {
			if bg, err := strconv.Atoi(parts[len(parts)-1]); err == nil {
				// ANSI colors 0-6 are dark, 7+ are light (white/bright)
				return bg < 7
			}
		}
	}

	// 2. Synchronous OSC 11 query (must run before BubbleTea takes the terminal).
	// AGENTSPAN_TEST_DISABLE_OSC_QUERY is an internal test seam so PTY tests can
	// deterministically exercise fallback detection inside a spawned binary.
	if os.Getenv("AGENTSPAN_TEST_DISABLE_OSC_QUERY") != "1" {
		if bg, err := queryBackgroundColor(); err == nil && bg != nil {
			return isDarkColor(bg)
		}
	}

	// 3. Best-effort macOS Terminal fallback. Terminal.app often runs without
	// COLORFGBG, and on some setups the OSC 11 query is unavailable, which
	// would otherwise force the dark default even for the stock light profile.
	if isDark, ok := detectAppleTerminalTheme(); ok {
		return isDark
	}

	// 4. Safe fallback when nothing else is available.
	return true
}

func isDarkColor(c color.Color) bool {
	r, g, b, _ := c.RGBA()
	rr := float64(r) / 65535.0
	gg := float64(g) / 65535.0
	bb := float64(b) / 65535.0

	luminance := 0.2126*srgbToLinear(rr) + 0.7152*srgbToLinear(gg) + 0.0722*srgbToLinear(bb)
	return luminance < 0.5
}

func srgbToLinear(v float64) float64 {
	if v <= 0.04045 {
		return v / 12.92
	}
	return math.Pow((v+0.055)/1.055, 2.4)
}

func detectAppleTerminalTheme() (bool, bool) {
	if runtimeGOOS != "darwin" || os.Getenv("TERM_PROGRAM") != "Apple_Terminal" {
		return false, false
	}

	for _, key := range []string{"Default Window Settings", "Startup Window Settings"} {
		profile, err := readAppleTerminalProfile(key)
		if err != nil || profile == "" {
			continue
		}
		if isDark, ok := classifyAppleTerminalProfile(profile); ok {
			return isDark, true
		}
	}

	return false, false
}

func classifyAppleTerminalProfile(profile string) (bool, bool) {
	p := strings.TrimSpace(strings.ToLower(profile))
	switch {
	case p == "":
		return false, false
	case strings.Contains(p, "dark"):
		return true, true
	case strings.Contains(p, "light"):
		return false, true
	}

	switch p {
	case "basic", "novel", "man page", "silver aerogel":
		return false, true
	case "clear dark", "grass", "homebrew", "ocean", "pro", "red sands":
		return true, true
	default:
		return false, false
	}
}

// Start launches the full-screen TUI.
func Start(version string) error {
	// Detect terminal background BEFORE BubbleTea takes over stdin/stdout.
	theme := detectInitialTheme()
	ui.SetTheme(theme.isDark)

	m := New(version)
	m.themeLocked = theme.locked
	p := tea.NewProgram(m)
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "TUI error: %v\n", err)
		return err
	}
	return nil
}
