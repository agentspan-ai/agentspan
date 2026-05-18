package tui

import (
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// NavItem is a single sidebar menu entry.
type NavItem struct {
	ID    ViewID
	Label string
}

// ViewID identifies which view is active.
type ViewID int

const (
	ViewDashboard   ViewID = iota
	ViewAgents             // merged: list + run + create + deploy
	ViewExecutions         // history + status + stream + HITL respond
	ViewServer             // start/stop/logs
	ViewSkills             // skill run/load/serve
	ViewCredentials        // set/list/delete/bind
	ViewDoctor             // system diagnostics
	ViewConfigure          // server URL + auth + login/logout
	// Keep these as aliases so existing app.go code compiles
	ViewRunAgent = ViewAgents // "Run Agent" merges into Agents
	ViewDeploy   = ViewAgents // "Deploy" merges into Agents
)

var navItems = []NavItem{
	{ViewDashboard, "Dashboard"},
	{ViewAgents, "Agents"},
	{ViewExecutions, "Executions"},
	{ViewServer, "Server"},
	{ViewSkills, "Skills"},
	{ViewCredentials, "Credentials"},
	{ViewDoctor, "Doctor"},
	{ViewConfigure, "Configure"},
}

// NavSelectMsg is emitted when the user presses Enter on a nav item.
type NavSelectMsg struct{ View ViewID }

// FocusContent is emitted when the user tabs into the content panel.
type FocusContent struct{}

// NavModel is the sidebar state.
type NavModel struct {
	items    []NavItem
	cursor   int    // highlighted row in sidebar
	active   ViewID // currently loaded view
	height   int
	healthy  bool
	checking bool
}

func NewNav() NavModel {
	return NavModel{
		items:    navItems,
		cursor:   0,
		active:   ViewDashboard,
		checking: true,
	}
}

// Update handles ALL key events — the app always routes up/down/enter here first.
// Returns (updated model, cmd). cmd may be NavSelectMsg or FocusContent.
func (n NavModel) Update(msg tea.Msg) (NavModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		n.height = msg.Height

	case tea.KeyPressMsg:
		switch msg.String() {
		case "up", "k":
			if n.cursor > 0 {
				n.cursor--
			} else {
				n.cursor = len(n.items) - 1 // wrap
			}

		case "down", "j":
			if n.cursor < len(n.items)-1 {
				n.cursor++
			} else {
				n.cursor = 0 // wrap
			}

		case "enter", " ", "space":
			n.active = n.items[n.cursor].ID
			selected := n.items[n.cursor].ID
			return n, func() tea.Msg { return NavSelectMsg{View: selected} }

		case "tab":
			// Shift focus into content panel
			return n, func() tea.Msg { return FocusContent{} }
		}
	}
	return n, nil
}

// SetActive sets both the active view and the cursor position.
func (n *NavModel) SetActive(v ViewID) {
	n.active = v
	for i, item := range n.items {
		if item.ID == v {
			n.cursor = i
			return
		}
	}
}

// ActiveView returns the currently displayed ViewID.
func (n NavModel) ActiveView() ViewID { return n.active }

// View renders the sidebar. contentFocused=true dims the sidebar slightly.
func (n NavModel) View(contentFocused bool) string {
	var sb strings.Builder
	sb.WriteString("\n")

	for i, item := range n.items {
		isCursor := i == n.cursor
		isActive := item.ID == n.active
		w := ui.SidebarWidth - 4

		var line string
		switch {
		case isCursor && !contentFocused:
			// Sidebar is active AND this row is highlighted → lime green bg
			line = ui.NavItemSelectedStyle.Width(w).Render(" > " + item.Label)

		case isActive && contentFocused:
			// Sidebar has a loaded view but content is focused → green text, no bg
			line = ui.NavItemActiveStyle.Width(w).Render(" > " + item.Label)

		case isActive:
			// Active but cursor is elsewhere
			line = ui.NavItemActiveStyle.Width(w).Render("   " + item.Label)

		default:
			line = ui.NavItemStyle.Width(w).Render("   " + item.Label)
		}
		sb.WriteString(line + "\n")
	}

	// Divider
	divider := lipgloss.NewStyle().
		Foreground(ui.ColorDarkGreen).
		Render(strings.Repeat("─", ui.SidebarWidth-4))
	sb.WriteString("\n" + divider + "\n")

	// Server status
	var srvStatus string
	switch {
	case n.checking:
		srvStatus = lipgloss.NewStyle().Foreground(ui.ColorYellow).Render("⟳ checking")
	case n.healthy:
		srvStatus = lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("● live")
	default:
		srvStatus = lipgloss.NewStyle().Foreground(ui.ColorRed).Faint(true).Render("◌ offline")
	}
	sb.WriteString(" " + srvStatus + "\n")

	borderColor := ui.ColorLimeGreen
	if contentFocused {
		borderColor = ui.ColorDarkGreen
	}

	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(borderColor).
		Width(ui.SidebarWidth).
		Render(sb.String())
}
