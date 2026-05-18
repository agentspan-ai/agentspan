package ui

import (
	"image/color"
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

// IsDarkBackground tracks whether the terminal has a dark background.
// Updated automatically via tea.BackgroundColorMsg; defaults to true.
var IsDarkBackground = true

// Color vars are reassigned by SetTheme(). Views reference these at render
// time so they always pick up the active palette. Colors are kept terminal-
// native where possible so custom macOS Terminal profiles can control the
// actual rendered palette rather than fighting fixed RGB values.
var (
	ColorLimeGreen  color.Color // primary accent, selected, active
	ColorGreen      color.Color // success, COMPLETED, checkmarks
	ColorDarkGreen  color.Color // borders, sidebar bg tint
	ColorGrey       color.Color // dimmed text, secondary labels
	ColorDarkGrey   color.Color // panel backgrounds
	ColorDeepBg     color.Color // stream/log viewport bg
	ColorWhite      color.Color // primary body text
	ColorBrightGrey color.Color // meta labels, timestamps
	ColorRed        color.Color // errors, FAILED
	ColorYellow     color.Color // warnings, RUNNING/PAUSED
	ColorBlue       color.Color // tool calls
	ColorTableAlt   color.Color // alternating table row bg
	ColorDangerBg   color.Color // danger button border
	ColorBg         color.Color // full-screen background (nil = terminal default)
	hasBg           bool        // whether to paint an explicit full-screen bg
)

// SetTheme reconfigures all color and style vars for the given background.
// Call this from AppModel.Update when tea.BackgroundColorMsg arrives.
func SetTheme(isDark bool) {
	IsDarkBackground = isDark
	if isDark {
		setDarkPalette()
	} else {
		setLightPalette()
	}
	rebuildStyles()
}

func setDarkPalette() { setTerminalPalette(true) }

func setLightPalette() { setTerminalPalette(false) }

func setTerminalPalette(isDark bool) {
	lightDark := lipgloss.LightDark(isDark)
	noColor := lipgloss.NoColor{}

	ColorLimeGreen = lightDark(lipgloss.Green, lipgloss.BrightGreen)
	ColorGreen = lightDark(lipgloss.Green, lipgloss.BrightGreen)
	ColorDarkGreen = lipgloss.BrightBlack
	ColorGrey = lipgloss.BrightBlack
	ColorDarkGrey = noColor
	ColorDeepBg = noColor
	ColorWhite = noColor
	ColorBrightGrey = lipgloss.BrightBlack
	ColorRed = lightDark(lipgloss.Red, lipgloss.BrightRed)
	ColorYellow = lightDark(lipgloss.Yellow, lipgloss.BrightYellow)
	ColorBlue = lightDark(lipgloss.Blue, lipgloss.BrightBlue)
	ColorTableAlt = noColor
	ColorDangerBg = lightDark(lipgloss.Red, lipgloss.BrightRed)
	ColorBg = noColor
	hasBg = false
}

func init() {
	// Default to dark theme; overridden when BackgroundColorMsg arrives.
	setDarkPalette()
	rebuildStyles()
}

// ─── Base Styles ────────────────────────────────────────────────────────────

var (
	Divider             string
	LogoStyle           lipgloss.Style
	MetaStyle           lipgloss.Style
	SectionHeadingStyle lipgloss.Style
	DimStyle            lipgloss.Style
	ErrorStyle          lipgloss.Style
	SuccessStyle        lipgloss.Style
	WarnStyle           lipgloss.Style
	KeyStyle            lipgloss.Style
	HintStyle           lipgloss.Style
	KeyHintSep          string
)

// rebuildStyles reconstructs all style vars from the current color palette.
func rebuildStyles() {
	Divider = lipgloss.NewStyle().
		Foreground(ColorDarkGreen).
		Render("─")

	LogoStyle = lipgloss.NewStyle().
		Bold(true).
		Foreground(ColorLimeGreen)

	MetaStyle = lipgloss.NewStyle().
		Foreground(ColorGrey)

	SectionHeadingStyle = lipgloss.NewStyle().
		Bold(true).
		Foreground(ColorLimeGreen)

	DimStyle = lipgloss.NewStyle().
		Foreground(ColorGrey).
		Faint(true)

	ErrorStyle = lipgloss.NewStyle().
		Foreground(ColorRed).
		Bold(true)

	SuccessStyle = lipgloss.NewStyle().
		Foreground(ColorGreen)

	WarnStyle = lipgloss.NewStyle().
		Foreground(ColorYellow)

	KeyStyle = lipgloss.NewStyle().Foreground(ColorLimeGreen).Bold(true)
	HintStyle = lipgloss.NewStyle().Foreground(ColorGrey).Faint(true)
	KeyHintSep = HintStyle.Render("  ")

	rebuildNavStyles()
	rebuildHeaderFooterStyles()
}

// ─── Pattern 1: Panel ────────────────────────────────────────────────────────
// Used as the outer wrapper for major content sections.

func PanelStyle(width, height int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(width).
		Height(height)
}

func PanelStyleFlat(width int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(width)
}

func InnerPanelStyle(width int) lipgloss.Style {
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorGrey).
		Background(ColorBg).
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
				Background(ColorTableAlt).
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
	NavItemStyle         lipgloss.Style
	NavItemSelectedStyle lipgloss.Style
	NavItemActiveStyle   lipgloss.Style
)

func rebuildNavStyles() {
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
}

// ─── Header / Footer bar styles ──────────────────────────────────────────────

var (
	HeaderStyle lipgloss.Style
	FooterStyle lipgloss.Style
)

func rebuildHeaderFooterStyles() {
	HeaderStyle = lipgloss.NewStyle().
		Background(ColorDarkGrey).
		Foreground(ColorWhite).
		Padding(0, 1)

	FooterStyle = lipgloss.NewStyle().
		Background(ColorDarkGrey).
		Foreground(ColorGrey).
		Faint(true).
		Padding(0, 1)
}

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
			BorderForeground(ColorDangerBg).
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
