package tui

import (
	"errors"
	"image/color"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// newTestApp creates an AppModel wired to nothing (no real client).
// It sends a WindowSizeMsg so all views start with correct dimensions.
func newTestApp() *AppModel {
	m := New("test")
	// Simulate the WindowSizeMsg that BubbleTea sends on startup
	result, _ := m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	return result.(*AppModel)
}

func pressKey(text string) tea.KeyPressMsg {
	return tea.KeyPressMsg(tea.Key{Text: text})
}

func pressSpecial(code rune) tea.KeyPressMsg {
	return tea.KeyPressMsg(tea.Key{Code: code})
}

// TestDefaultFocusSidebar verifies that on startup the sidebar has focus
// (contentFocused = false) so arrow keys move the nav cursor.
func TestDefaultFocusSidebar(t *testing.T) {
	m := newTestApp()
	if m.contentFocused {
		t.Error("expected contentFocused=false on startup")
	}
}

// TestArrowDownMovesSidebarCursor verifies ↓ moves the nav cursor.
func TestArrowDownMovesSidebarCursor(t *testing.T) {
	m := newTestApp()
	before := m.nav.cursor

	result, _ := m.Update(pressSpecial(tea.KeyDown))
	m2 := result.(*AppModel)

	if m2.nav.cursor != before+1 {
		t.Errorf("expected cursor %d, got %d", before+1, m2.nav.cursor)
	}
}

// TestArrowUpMovesSidebarCursor verifies ↑ moves the nav cursor.
func TestArrowUpMovesSidebarCursor(t *testing.T) {
	m := newTestApp()
	m.nav.cursor = 3

	result, _ := m.Update(pressSpecial(tea.KeyUp))
	m2 := result.(*AppModel)

	if m2.nav.cursor != 2 {
		t.Errorf("expected cursor 2, got %d", m2.nav.cursor)
	}
}

// TestEnterNavigatesAndFocusesContent verifies Enter on nav item:
// 1. switches to the selected view
// 2. immediately focuses the content panel so arrow keys work in the view.
func TestEnterNavigatesAndFocusesContent(t *testing.T) {
	m := newTestApp()
	m.nav.cursor = 1 // Agents

	result, _ := m.Update(pressSpecial(tea.KeyEnter))
	m2 := result.(*AppModel)

	if m2.activeView != ViewAgents {
		t.Errorf("expected ViewAgents, got %d", m2.activeView)
	}
	if !m2.contentFocused {
		t.Error("expected contentFocused=true after enter — arrow keys must work in content immediately")
	}
}

// TestTabAlsoFocusesContent verifies Tab behaves the same as Enter.
func TestTabAlsoFocusesContent(t *testing.T) {
	m := newTestApp()
	m.nav.cursor = 1 // Agents

	result, _ := m.Update(pressSpecial(tea.KeyTab))
	m2 := result.(*AppModel)

	if !m2.contentFocused {
		t.Error("expected contentFocused=true after tab")
	}
	if m2.activeView != ViewAgents {
		t.Errorf("expected ViewAgents after tab, got %d", m2.activeView)
	}
}

// TestArrowKeysWorkInContentAfterEnter is the key regression test:
// after pressing enter on a nav item, up/down must go to the active view,
// NOT back to the sidebar cursor.
func TestArrowKeysWorkInContentAfterEnter(t *testing.T) {
	m := newTestApp()
	m.nav.cursor = 0 // Dashboard

	// Press enter to open Dashboard and focus content
	result, _ := m.Update(pressSpecial(tea.KeyEnter))
	m2 := result.(*AppModel)

	if !m2.contentFocused {
		t.Fatal("contentFocused must be true after enter for this test to be valid")
	}

	// Now press down — should go to the content view, NOT move nav cursor
	navCursorBefore := m2.nav.cursor
	result2, _ := m2.Update(pressSpecial(tea.KeyDown))
	m3 := result2.(*AppModel)

	if m3.nav.cursor != navCursorBefore {
		t.Errorf("nav cursor moved from %d to %d — arrow key was stolen by sidebar when content is focused",
			navCursorBefore, m3.nav.cursor)
	}
}

// TestEscInContentReturnsFocusToSidebar verifies Esc returns to sidebar.
func TestEscInContentReturnsFocusToSidebar(t *testing.T) {
	m := newTestApp()
	m.contentFocused = true
	m.activeView = ViewAgents

	result, _ := m.Update(pressSpecial(tea.KeyEscape))
	m2 := result.(*AppModel)

	if m2.contentFocused {
		t.Error("expected contentFocused=false after esc")
	}
}

// TestNumberJumpsToView verifies 1-5 shortcut keys jump directly to views.
func TestNumberJumpsToView(t *testing.T) {
	tests := []struct {
		key      string
		wantView ViewID
	}{
		{"1", ViewDashboard},
		{"2", ViewAgents},
		{"3", ViewExecutions},
		{"4", ViewServer},
		{"5", ViewSkills},
		{"6", ViewCredentials},
		{"7", ViewDoctor},
		{"8", ViewConfigure},
	}
	for _, tt := range tests {
		m := newTestApp()
		result, _ := m.Update(pressKey(tt.key))
		m2 := result.(*AppModel)
		if m2.activeView != tt.wantView {
			t.Errorf("key %q: expected view %d, got %d", tt.key, tt.wantView, m2.activeView)
		}
	}
}

// TestHelpOverlayToggle verifies ? toggles the help overlay.
func TestHelpOverlayToggle(t *testing.T) {
	m := newTestApp()
	if m.showHelp {
		t.Error("help should be off initially")
	}

	result, _ := m.Update(pressKey("?"))
	m2 := result.(*AppModel)
	if !m2.showHelp {
		t.Error("expected help on after ?")
	}

	result2, _ := m2.Update(pressKey("?"))
	m3 := result2.(*AppModel)
	if m3.showHelp {
		t.Error("expected help off after second ?")
	}
}

// TestAnyKeyClosesHelp verifies any key closes the help overlay.
func TestAnyKeyClosesHelp(t *testing.T) {
	m := newTestApp()
	m.showHelp = true

	result, _ := m.Update(pressKey("x"))
	m2 := result.(*AppModel)
	if m2.showHelp {
		t.Error("expected help closed after any key")
	}
}

// TestQInSidebarQuitsApp verifies q in sidebar mode quits.
func TestQInSidebarQuitsApp(t *testing.T) {
	m := newTestApp()
	_, cmd := m.Update(pressKey("q"))
	if cmd == nil {
		t.Fatal("expected a quit cmd")
	}
	msg := cmd()
	if _, ok := msg.(tea.QuitMsg); !ok {
		t.Errorf("expected QuitMsg, got %T", msg)
	}
}

// TestNavigationPreservesDimensions verifies that navigating to a view and
// back gives a full-size content panel — not a tiny 20-wide fallback.
// Before the fix, New*() called with width=0 would give ContentWidth(0)=20.
func TestNavigationPreservesDimensions(t *testing.T) {
	m := newTestApp() // width=120, height=40

	// Navigate to Agents — new model must have received the size
	result, _ := m.Update(NavSelectMsg{View: ViewAgents})
	m2 := result.(*AppModel)
	got := m2.agents.View()
	// A correctly sized view should be much wider than the 20-col fallback
	lines := splitLines(got)
	if len(lines) > 0 && visibleWidth(lines[0]) < 50 {
		t.Errorf("agents view looks narrow (%d cols) after navigation — dimensions not set",
			visibleWidth(lines[0]))
	}

	// Navigate to Server
	result, _ = m2.Update(NavSelectMsg{View: ViewServer})
	m3 := result.(*AppModel)
	got = m3.server.View()
	lines = splitLines(got)
	if len(lines) > 0 && visibleWidth(lines[0]) < 50 {
		t.Errorf("server view looks narrow (%d cols) after navigation", visibleWidth(lines[0]))
	}

	// Navigate back to Agents — still full size
	result, _ = m3.Update(NavSelectMsg{View: ViewAgents})
	m4 := result.(*AppModel)
	got = m4.agents.View()
	lines = splitLines(got)
	if len(lines) > 0 && visibleWidth(lines[0]) < 50 {
		t.Errorf("agents view narrow after navigating back — regression")
	}
}

func splitLines(s string) []string {
	var lines []string
	for _, l := range []string{} {
		lines = append(lines, l)
	}
	start := 0
	for i, c := range s {
		if c == '\n' {
			lines = append(lines, s[start:i])
			start = i + 1
		}
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

// visibleWidth estimates the visible column width of a string,
// stripping ANSI escape sequences.
func visibleWidth(s string) int {
	inEscape := false
	w := 0
	for _, c := range s {
		if c == '\x1b' {
			inEscape = true
			continue
		}
		if inEscape {
			if c == 'm' {
				inEscape = false
			}
			continue
		}
		w++
	}
	return w
}

// TestCtrlCAlwaysQuits verifies ctrl+c always quits regardless of focus.
func TestCtrlCAlwaysQuits(t *testing.T) {
	for _, focused := range []bool{true, false} {
		m := newTestApp()
		m.contentFocused = focused
		_, cmd := m.Update(pressKey("ctrl+c"))
		if cmd == nil {
			t.Fatalf("contentFocused=%v: expected quit cmd", focused)
		}
		msg := cmd()
		if _, ok := msg.(tea.QuitMsg); !ok {
			t.Errorf("contentFocused=%v: expected QuitMsg, got %T", focused, msg)
		}
	}
}

func TestDetectInitialThemeRespectsEnvOverride(t *testing.T) {
	t.Setenv("AGENTSPAN_THEME", "light")

	theme := detectInitialTheme()
	if theme.isDark {
		t.Error("AGENTSPAN_THEME=light should force the light theme")
	}
	if !theme.locked {
		t.Error("AGENTSPAN_THEME should lock the theme against auto-detection updates")
	}
}

func TestBackgroundColorIgnoredWhenThemeLocked(t *testing.T) {
	prev := ui.IsDarkBackground
	t.Cleanup(func() { ui.SetTheme(prev) })

	ui.SetTheme(false)
	m := newTestApp()
	m.themeLocked = true

	result, _ := m.Update(tea.BackgroundColorMsg{color.Black})
	m2 := result.(*AppModel)

	if !m2.themeLocked {
		t.Error("theme lock should persist after a background-color message")
	}
	if ui.IsDarkBackground {
		t.Error("locked theme should ignore terminal background updates")
	}
}

func TestBackgroundColorUpdatesWhenThemeUnlocked(t *testing.T) {
	prev := ui.IsDarkBackground
	t.Cleanup(func() { ui.SetTheme(prev) })

	ui.SetTheme(false)
	m := newTestApp()
	m.themeLocked = false

	_, _ = m.Update(tea.BackgroundColorMsg{color.Black})
	if !ui.IsDarkBackground {
		t.Error("auto theme should track terminal background updates")
	}
}

func TestCtrlTTogglesThemeAndLocksIt(t *testing.T) {
	prev := ui.IsDarkBackground
	t.Cleanup(func() { ui.SetTheme(prev) })

	ui.SetTheme(true)
	m := newTestApp()
	m.themeLocked = false

	result, _ := m.Update(pressKey("ctrl+t"))
	m2 := result.(*AppModel)

	if !m2.themeLocked {
		t.Error("ctrl+t should lock the theme in the user-selected mode")
	}
	if ui.IsDarkBackground {
		t.Error("ctrl+t should toggle the theme")
	}

	_, _ = m2.Update(tea.BackgroundColorMsg{color.Black})
	if ui.IsDarkBackground {
		t.Error("terminal background updates should not override a manual theme toggle")
	}
}

func TestDetectDarkBackgroundFallsBackToAppleTerminalProfile(t *testing.T) {
	prevGOOS := runtimeGOOS
	prevQuery := queryBackgroundColor
	prevReadProfile := readAppleTerminalProfile
	t.Cleanup(func() {
		runtimeGOOS = prevGOOS
		queryBackgroundColor = prevQuery
		readAppleTerminalProfile = prevReadProfile
	})

	runtimeGOOS = "darwin"
	t.Setenv("COLORFGBG", "")
	t.Setenv("TERM_PROGRAM", "Apple_Terminal")
	queryBackgroundColor = func() (color.Color, error) {
		return nil, errors.New("osc query failed")
	}
	readAppleTerminalProfile = func(key string) (string, error) {
		if key == "Default Window Settings" {
			return "Basic", nil
		}
		return "", errors.New("unexpected key")
	}

	if detectDarkBackground() {
		t.Error("Apple Terminal Basic profile should fall back to light theme")
	}
}

func TestClassifyAppleTerminalProfile(t *testing.T) {
	cases := []struct {
		profile string
		want    bool
		ok      bool
	}{
		{profile: "Basic", want: false, ok: true},
		{profile: "Clear Light", want: false, ok: true},
		{profile: "Clear Dark", want: true, ok: true},
		{profile: "Pro", want: true, ok: true},
		{profile: "Unknown Custom", want: false, ok: false},
	}

	for _, tc := range cases {
		got, ok := classifyAppleTerminalProfile(tc.profile)
		if got != tc.want || ok != tc.ok {
			t.Errorf("profile %q: got (%v, %v), want (%v, %v)", tc.profile, got, ok, tc.want, tc.ok)
		}
	}
}
