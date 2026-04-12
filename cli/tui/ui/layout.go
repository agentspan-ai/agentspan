package ui

import (
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
)

// RenderHeader renders the top header bar at full terminal width.
func RenderHeader(width int, version string, serverStatus string) string {
	logo := LogoStyle.Render("◆ agentspan")
	ver := MetaStyle.Render(" " + version)
	left := logo + ver
	right := "server: " + serverStatus

	leftWidth := lipgloss.Width(left)
	rightWidth := lipgloss.Width(right)
	gap := width - leftWidth - rightWidth - 2
	if gap < 1 {
		gap = 1
	}

	content := left + strings.Repeat(" ", gap) + right
	return HeaderStyle.Width(width).Render(content)
}

// RenderFooter renders the context-sensitive footer help bar.
func RenderFooter(width int, hints string) string {
	return FooterStyle.Width(width).Render(hints)
}

// ContentWidth returns the outer width for the content panel.
// The sidebar occupies SidebarWidth cols + its NormalBorder (1 left + 1 right = 2) = SidebarWidth+2.
// Content panel gets the rest.
func ContentWidth(termWidth int) int {
	w := termWidth - SidebarWidth - 2
	if w < 20 {
		return 20
	}
	return w
}

// ContentHeight returns the outer height for ContentPanel.
// The screen layout is:
//
//	header(1) + \n(1) + body(bodyH) + \n(1) + footer(1) = termHeight
//
// So bodyH = termHeight - 4.
func ContentHeight(termHeight int) int {
	h := termHeight - 4
	if h < 4 {
		return 4
	}
	return h
}

// RenderLayout joins sidebar and content side by side, both padded to bodyH rows.
func RenderLayout(termWidth, termHeight int, sidebar, content string) string {
	bodyH := termHeight - 4
	if bodyH < 1 {
		bodyH = 1
	}
	sidebarPadded := lipgloss.NewStyle().Height(bodyH).Render(sidebar)
	contentPadded := lipgloss.NewStyle().Height(bodyH).Render(content)
	return lipgloss.JoinHorizontal(lipgloss.Top, sidebarPadded, contentPadded)
}

// ContentPanel wraps body in a rounded-border panel.
// width  = outer width  (use ContentWidth(termWidth)).
// height = outer height (use ContentHeight(termHeight)).
// The border consumes 2 rows and 2 cols; inner area = (width-4) x (height-2).
func ContentPanel(width, height int, title, body string) string {
	if width < 6 {
		width = 6
	}
	if height < 4 {
		height = 4
	}

	var titleBar string
	if title != "" {
		titleBar = SectionHeadingStyle.Render(title) + "\n\n"
	}

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(width).
		Height(height).
		Render(titleBar + body)
}

// SplitHorizontal divides width into two side-by-side panels.
func SplitHorizontal(totalWidth int, leftContent, rightContent string) string {
	half := (totalWidth - 3) / 2
	if half < 5 {
		half = 5
	}
	left := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(half).
		Render(leftContent)
	right := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(half).
		Render(rightContent)
	return lipgloss.JoinHorizontal(lipgloss.Top, left, right)
}

// CardRow renders a key-value row inside a card/panel.
func CardRow(key, value string) string {
	keyStyle := lipgloss.NewStyle().Foreground(ColorBrightGrey).Width(14)
	valStyle := lipgloss.NewStyle().Foreground(ColorWhite)
	return keyStyle.Render(key) + valStyle.Render(value)
}

// Card renders a titled box with labeled rows.
func Card(width int, title string, rows ...string) string {
	heading := SectionHeadingStyle.Render(title)
	body := heading + "\n" + strings.Repeat("─", lipgloss.Width(title)) + "\n"
	for _, r := range rows {
		body += r + "\n"
	}
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorDarkGreen).
		Background(ColorBg).
		Padding(0, 1).
		Width(width).
		Render(body)
}

// EmptyState renders a styled "nothing here" placeholder.
func EmptyState(msg string) string {
	return lipgloss.NewStyle().
		Foreground(ColorGrey).
		Italic(true).
		Padding(1, 2).
		Render(msg)
}

// ErrorBanner renders a full-width error message.
func ErrorBanner(width int, msg string) string {
	if width < 6 {
		width = 6
	}
	return lipgloss.NewStyle().
		Foreground(ColorRed).
		Bold(true).
		Border(lipgloss.NormalBorder()).
		BorderForeground(ColorRed).
		Padding(0, 1).
		Width(width).
		Render("✗ " + msg)
}

// SuccessBanner renders a full-width success message.
func SuccessBanner(width int, msg string) string {
	if width < 6 {
		width = 6
	}
	return lipgloss.NewStyle().
		Foreground(ColorGreen).
		Border(lipgloss.NormalBorder()).
		BorderForeground(ColorGreen).
		Padding(0, 1).
		Width(width).
		Render("✓ " + msg)
}

// Spinner frames for lightweight animated spinners.
var spinnerFrames = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

// SpinnerFrame returns the spinner character for the given tick count.
func SpinnerFrame(tick int) string {
	frame := spinnerFrames[tick%len(spinnerFrames)]
	return lipgloss.NewStyle().Foreground(ColorLimeGreen).Render(frame)
}

// ProgressBar renders a simple progress bar.
func ProgressBar(width int, percent float64, desc string) string {
	barWidth := width - 20
	if barWidth < 10 {
		barWidth = 10
	}
	filled := int(float64(barWidth) * percent / 100.0)
	if filled > barWidth {
		filled = barWidth
	}
	empty := barWidth - filled

	bar := lipgloss.NewStyle().Foreground(ColorLimeGreen).Render(strings.Repeat("█", filled)) +
		lipgloss.NewStyle().Foreground(ColorDarkGreen).Render(strings.Repeat("░", empty))

	pct := lipgloss.NewStyle().Foreground(ColorWhite).Render(fmt.Sprintf(" %3.0f%%", percent))
	return desc + " [" + bar + "]" + pct
}

// WrapScreen applies the full-screen background color so the selected palette
// renders consistently even when the terminal's native background differs.
func WrapScreen(content string, width, height int) string {
	if !hasBg {
		return content
	}
	return lipgloss.NewStyle().
		Background(ColorBg).
		Width(width).
		Height(height).
		Render(content)
}
