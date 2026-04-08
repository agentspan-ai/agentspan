package components

import (
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// KeyBinding is a single keyboard shortcut displayed in the help overlay.
type KeyBinding struct {
	Key  string
	Desc string
}

// FooterHints renders a context-sensitive help bar.
func FooterHints(width int, hints ...KeyBinding) string {
	parts := make([]string, 0, len(hints))
	for _, h := range hints {
		parts = append(parts, ui.KeyHint(h.Key, h.Desc))
	}
	return ui.FooterStyle.Width(width).Render(strings.Join(parts, ui.KeyHintSep))
}

// HelpOverlay renders a full-screen help overlay.
func HelpOverlay(width, height int) string {
	sections := []struct {
		title    string
		bindings []KeyBinding
	}{
		{
			title: "Navigation (Sidebar — default mode)",
			bindings: []KeyBinding{
				{"↑ / k", "move up"},
				{"↓ / j", "move down"},
				{"enter", "select view"},
				{"tab", "focus content panel"},
				{"1-0", "jump to view directly"},
				{"q", "quit"},
			},
		},
		{
			title: "Navigation (Content Panel)",
			bindings: []KeyBinding{
				{"↑↓", "scroll / move cursor"},
				{"enter", "confirm / open detail"},
				{"esc", "back to sidebar"},
				{"tab", "next field / section"},
				{"?", "toggle this help"},
			},
		},
		{
			title: "Agents",
			bindings: []KeyBinding{
				{"r", "run selected agent"},
				{"d", "delete agent"},
				{"/", "search"},
				{"R", "refresh"},
			},
		},
		{
			title: "Executions / Stream",
			bindings: []KeyBinding{
				{"s", "stream live events"},
				{"f", "toggle follow mode"},
				{"← →", "prev/next page"},
				{"ctrl+c", "stop streaming"},
			},
		},
		{
			title: "Server",
			bindings: []KeyBinding{
				{"s", "start server"},
				{"t", "stop server"},
				{"f", "follow log output"},
				{"R", "refresh status"},
			},
		},
	}

	innerWidth := width - 6
	col := lipgloss.NewStyle().Width(innerWidth / 2)
	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(ui.ColorLimeGreen)

	var sb strings.Builder
	sb.WriteString("\n")
	for _, sec := range sections {
		sb.WriteString("  " + titleStyle.Render(sec.title) + "\n")
		for i := 0; i < len(sec.bindings); i += 2 {
			left := ui.KeyHint(sec.bindings[i].Key, sec.bindings[i].Desc)
			right := ""
			if i+1 < len(sec.bindings) {
				right = ui.KeyHint(sec.bindings[i+1].Key, sec.bindings[i+1].Desc)
			}
			sb.WriteString("  " + col.Render(left) + col.Render(right) + "\n")
		}
		sb.WriteString("\n")
	}
	sb.WriteString(ui.DimStyle.Render("  Press ? or esc to close") + "\n")

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Background(ui.ColorDarkGrey).
		Padding(0, 1).
		Width(width).
		Height(height).
		Render(sb.String())
}
