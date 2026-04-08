package ui

import (
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"charm.land/lipgloss/v2/table"
)

// ─── Global spinner tick ──────────────────────────────────────────────────────

// SpinnerTickMsg is broadcast every 100ms to drive spinner animations.
type SpinnerTickMsg struct{}

// SpinnerTickCmd returns a tea.Cmd that fires SpinnerTickMsg every 100ms.
func SpinnerTickCmd() tea.Cmd {
	return tea.Tick(100*time.Millisecond, func(time.Time) tea.Msg {
		return SpinnerTickMsg{}
	})
}

// ─── Color Palette ──────────────────────────────────────────────────────────

// Sidebar width constant.
const SidebarWidth = 20

var (
	ColorLimeGreen  = lipgloss.Color("#A8FF3E") // primary accent, selected, active
	ColorGreen      = lipgloss.Color("#39D353") // success, COMPLETED, checkmarks
	ColorDarkGreen  = lipgloss.Color("#1A7F37") // borders, sidebar bg tint
	ColorGrey       = lipgloss.Color("#6E7681") // dimmed text, secondary labels
	ColorDarkGrey   = lipgloss.Color("#2D333B") // panel backgrounds
	ColorDeepBg     = lipgloss.Color("#1C2128") // stream/log viewport bg
	ColorWhite      = lipgloss.Color("#E6EDF3") // primary body text
	ColorBrightGrey = lipgloss.Color("#8B949E") // meta labels, timestamps
	ColorRed        = lipgloss.Color("#F85149") // errors, FAILED
	ColorYellow     = lipgloss.Color("#D29922") // warnings, RUNNING/PAUSED
	ColorBlue       = lipgloss.Color("#58A6FF") // tool calls
)

// ─── Base Styles ────────────────────────────────────────────────────────────

var (
	// Subtle divider line
	Divider = lipgloss.NewStyle().
		Foreground(ColorDarkGreen).
		Render("─")

	// Logo / brand text
	LogoStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorLimeGreen)

	// Version & meta text
	MetaStyle = lipgloss.NewStyle().
			Foreground(ColorGrey)

	// Bold section headings inside panels
	SectionHeadingStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(ColorLimeGreen)

	// Dimmed secondary text
	DimStyle = lipgloss.NewStyle().
			Foreground(ColorGrey).
			Faint(true)

	// Error text
	ErrorStyle = lipgloss.NewStyle().
			Foreground(ColorRed).
			Bold(true)

	// Success text
	SuccessStyle = lipgloss.NewStyle().
			Foreground(ColorGreen)

	// Warning text
	WarnStyle = lipgloss.NewStyle().
			Foreground(ColorYellow)

	// Key hint — for footer help bar
	KeyStyle   = lipgloss.NewStyle().Foreground(ColorLimeGreen).Bold(true)
	HintStyle  = lipgloss.NewStyle().Foreground(ColorGrey).Faint(true)
	KeyHintSep = HintStyle.Render("  ")
)

// ─── Pattern 1: Panel ────────────────────────────────────────────────────────
// Used as the outer wrapper for major content sections.

func PanelStyle(width, height int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Padding(0, 1).
		Width(width).
		Height(height)
}

func PanelStyleFlat(width int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ColorDarkGreen).
		Padding(0, 1).
		Width(width)
}

func InnerPanelStyle(width int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorGrey).
		Padding(0, 1).
		Width(width)
}

// ─── Pattern 2: Status Badge ─────────────────────────────────────────────────
// Inline pill badge for execution/server statuses.

func StatusBadge(status string) string {
	base := lipgloss.NewStyle().Bold(true).Padding(0, 1)
	switch status {
	case "RUNNING":
		return base.Foreground(ColorYellow).Render("● RUNNING")
	case "COMPLETED":
		return base.Foreground(ColorGreen).Render("✓ COMPLETED")
	case "FAILED":
		return base.Foreground(ColorRed).Render("✗ FAILED")
	case "TERMINATED":
		return lipgloss.NewStyle().Faint(true).Foreground(ColorRed).Padding(0, 1).Render("✗ TERMINATED")
	case "TIMED_OUT":
		return lipgloss.NewStyle().Faint(true).Foreground(ColorRed).Padding(0, 1).Render("⏱ TIMED_OUT")
	case "PAUSED":
		return base.Foreground(ColorYellow).Render("⏸ PAUSED")
	case "WAITING":
		return base.Foreground(ColorYellow).Render("⏸ WAITING")
	case "live", "healthy":
		return lipgloss.NewStyle().Foreground(ColorGreen).Render("● live")
	case "offline", "unhealthy":
		return lipgloss.NewStyle().Foreground(ColorRed).Faint(true).Render("◌ offline")
	case "checking":
		return lipgloss.NewStyle().Foreground(ColorYellow).Render("⟳ checking")
	default:
		return lipgloss.NewStyle().Foreground(ColorGrey).Padding(0, 1).Render("– " + status)
	}
}

// ─── Pattern 3: DataTable ────────────────────────────────────────────────────
// Styled lipgloss table for list views.

func NewDataTable() *table.Table {
	return table.New().
		Border(lipgloss.NormalBorder()).
		BorderStyle(lipgloss.NewStyle().Foreground(ColorDarkGreen)).
		StyleFunc(func(row, col int) lipgloss.Style {
			if row == table.HeaderRow {
				return lipgloss.NewStyle().
					Bold(true).
					Foreground(ColorLimeGreen).
					Padding(0, 1)
			}
			if row%2 == 0 {
				return lipgloss.NewStyle().
					Foreground(ColorWhite).
					Background(ColorDarkGrey).
					Padding(0, 1)
			}
			return lipgloss.NewStyle().
				Foreground(ColorWhite).
				Background(lipgloss.Color("#252B32")).
				Padding(0, 1)
		})
}

// ─── Pattern 4: Stream Viewport styling ──────────────────────────────────────
// Container style for the stream viewport (bubbles/viewport lives inside).

func StreamContainerStyle(width, height int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorDeepBg).
		Width(width).
		Height(height)
}

// ─── Nav Item Styles ─────────────────────────────────────────────────────────

var (
	NavItemStyle = lipgloss.NewStyle().
			Foreground(ColorBrightGrey).
			Padding(0, 1)

	NavItemSelectedStyle = lipgloss.NewStyle().
				Foreground(ColorLimeGreen).
				Background(ColorDarkGreen).
				Bold(true).
				Padding(0, 1)

	NavItemActiveStyle = lipgloss.NewStyle().
				Foreground(ColorGreen).
				Padding(0, 1)
)

// ─── Header / Footer bar styles ──────────────────────────────────────────────

var (
	HeaderStyle = lipgloss.NewStyle().
			Background(ColorDarkGrey).
			Foreground(ColorWhite).
			Padding(0, 1)

	FooterStyle = lipgloss.NewStyle().
			Background(ColorDarkGrey).
			Foreground(ColorGrey).
			Faint(true).
			Padding(0, 1)
)

// ─── Form Panel ──────────────────────────────────────────────────────────────

func FormPanelStyle(width int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorDarkGrey).
		Padding(1, 2).
		Width(width)
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

// KeyHint renders a "key desc" pair for the footer bar.
func KeyHint(key, desc string) string {
	return KeyStyle.Render(key) + HintStyle.Render(" "+desc)
}

// Truncate shortens a string and adds "..." if over limit.
func Truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	if max <= 3 {
		return s[:max]
	}
	return s[:max-3] + "..."
}

// ─── Button helpers ───────────────────────────────────────────────────────────

// Button renders a single pill button.
// active = currently focused/selected (lime green border + text).
// danger = destructive action (red border).
func Button(label string, active bool, danger bool) string {
	var s lipgloss.Style
	switch {
	case active && danger:
		s = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorRed).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorRed).
			Padding(0, 1)
	case active:
		s = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorLimeGreen).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorLimeGreen).
			Padding(0, 1)
	case danger:
		s = lipgloss.NewStyle().
			Foreground(ColorRed).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#4A1010")).
			Padding(0, 1)
	default:
		s = lipgloss.NewStyle().
			Foreground(ColorBrightGrey).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorGrey).
			Padding(0, 1)
	}
	return s.Render(label)
}

// ButtonDef describes a single button in a bar.
type ButtonDef struct {
	Key    string // keyboard shortcut shown in label, e.g. "r"
	Label  string // display text after key, e.g. "run"
	Danger bool   // red colouring for destructive actions
}

// ButtonBar renders a row of pill buttons.
// cursor is the index of the currently focused button (-1 = none focused).
func ButtonBar(buttons []ButtonDef, cursor int) string {
	parts := make([]string, len(buttons))
	for i, b := range buttons {
		label := lipgloss.NewStyle().
			Foreground(ColorLimeGreen).Bold(true).Render(b.Key) +
			" " + b.Label
		parts[i] = Button(label, i == cursor, b.Danger)
	}
	result := lipgloss.JoinHorizontal(lipgloss.Top, joinWithSpace(parts)...)
	return result
}

func joinWithSpace(parts []string) []string {
	if len(parts) == 0 {
		return parts
	}
	out := make([]string, 0, len(parts)*2-1)
	for i, p := range parts {
		out = append(out, p)
		if i < len(parts)-1 {
			out = append(out, " ")
		}
	}
	return out
}

// HintBar renders a row of key hint pills (non-interactive display).
// Used in view bodies for inline hints like "f follow  ↑↓ scroll".
func HintBar(hints ...ButtonDef) string {
	parts := make([]string, len(hints))
	for i, h := range hints {
		keyPart := lipgloss.NewStyle().Foreground(ColorLimeGreen).Bold(true).Render(h.Key)
		descPart := lipgloss.NewStyle().Foreground(ColorGrey).Render(" " + h.Label)
		pill := lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorGrey).
			Padding(0, 1).
			Render(keyPart + descPart)
		parts[i] = pill
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, joinWithSpace(parts)...)
}
