package ui_test

import (
	"testing"

	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// TestLayoutFillsTerminal verifies that the full rendered output fits within
// the terminal without overflow across common screen sizes.
func TestLayoutFillsTerminal(t *testing.T) {
	sizes := []struct{ w, h int }{
		{220, 50},
		{120, 30},
		{80, 24},
		{200, 60},
		{160, 40},
	}

	for _, sz := range sizes {
		header := ui.RenderHeader(sz.w, "dev", "● live")
		footer := ui.RenderFooter(sz.w, "hints")
		cw := ui.ContentWidth(sz.w)
		ch := ui.ContentHeight(sz.h)
		panel := ui.ContentPanel(cw, ch, "Test", "body content")
		sidebar := lipgloss.NewStyle().
			Border(lipgloss.NormalBorder()).
			Width(ui.SidebarWidth).
			Render("nav")
		body := ui.RenderLayout(sz.w, sz.h, sidebar, panel)
		full := header + "\n" + body + "\n" + footer
		totalH := lipgloss.Height(full)

		if totalH > sz.h {
			t.Errorf("term=%dx%d: output height %d > terminal height %d (overflow)",
				sz.w, sz.h, totalH, sz.h)
		}
		// Allow up to 3 rows of slack (the \n separators take 2 rows)
		if totalH < sz.h-3 {
			t.Errorf("term=%dx%d: output height %d too short (expected ~%d)",
				sz.w, sz.h, totalH, sz.h)
		}
	}
}

// TestContentWidthNeverNegative ensures ContentWidth is always positive.
func TestContentWidthNeverNegative(t *testing.T) {
	for _, w := range []int{0, 10, 20, 40, 80, 120, 220} {
		if ui.ContentWidth(w) < 1 {
			t.Errorf("ContentWidth(%d) = %d, want >= 1", w, ui.ContentWidth(w))
		}
	}
}

// TestContentHeightNeverNegative ensures ContentHeight is always positive.
func TestContentHeightNeverNegative(t *testing.T) {
	for _, h := range []int{0, 5, 10, 24, 30, 50, 60} {
		if ui.ContentHeight(h) < 1 {
			t.Errorf("ContentHeight(%d) = %d, want >= 1", h, ui.ContentHeight(h))
		}
	}
}
