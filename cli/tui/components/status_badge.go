package components

import (
	"fmt"
	"time"

	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// Badge renders a coloured status badge string.
func Badge(status string) string {
	return ui.StatusBadge(status)
}

// ServerBadge renders a compact server status indicator.
func ServerBadge(healthy bool, checking bool) string {
	if checking {
		return lipgloss.NewStyle().Foreground(ui.ColorYellow).Render("⟳ checking")
	}
	if healthy {
		return lipgloss.NewStyle().Foreground(ui.ColorGreen).Render("● live")
	}
	return lipgloss.NewStyle().Foreground(ui.ColorRed).Faint(true).Render("◌ offline")
}

// FormatDuration renders milliseconds as a human-readable duration.
func FormatDuration(ms int64) string {
	if ms <= 0 {
		return "—"
	}
	d := time.Duration(ms) * time.Millisecond
	if d < time.Second {
		return fmt.Sprintf("%dms", ms)
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs", d.Seconds())
	}
	if d < time.Hour {
		return fmt.Sprintf("%.1fm", d.Minutes())
	}
	return fmt.Sprintf("%.1fh", d.Hours())
}

// RelativeTime converts an ISO-8601 or epoch string to "Xm ago" format.
func RelativeTime(t string) string {
	if t == "" {
		return "—"
	}
	// Try ISO8601 first (first 19 chars like the CLI does)
	if len(t) >= 19 {
		t = t[:19]
	}
	parsed, err := time.Parse("2006-01-02T15:04:05", t)
	if err != nil {
		parsed, err = time.Parse("2006-01-02 15:04:05", t)
		if err != nil {
			return t
		}
	}
	diff := time.Since(parsed)
	switch {
	case diff < time.Minute:
		return "just now"
	case diff < time.Hour:
		return fmt.Sprintf("%dm ago", int(diff.Minutes()))
	case diff < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(diff.Hours()))
	case diff < 7*24*time.Hour:
		return fmt.Sprintf("%dd ago", int(diff.Hours()/24))
	default:
		return parsed.Format("2006-01-02")
	}
}

// TruncateID shortens a UUID-like execution ID for display.
func TruncateID(id string) string {
	if len(id) <= 12 {
		return id
	}
	return id[:12] + "..."
}
