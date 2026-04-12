package tui

// visual_test.go — captures and validates the rendered output of every TUI
// view at a fixed terminal size, checking alignment, borders, and widths.
//
// Run with:
//
//	go test ./tui/ -run TestVisual -v
//
// Snapshot files are written to tui/testdata/snapshots/*.txt for human review.
// The -update flag regenerates them:
//
//	go test ./tui/ -run TestVisual -update

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

var updateSnapshots = flag.Bool("update", false, "Regenerate snapshot files")

// termW × termH is the simulated terminal size for all snapshots.
const (
	snapW = 220
	snapH = 50
)

// snapshotDir is where .txt snapshot files are written.
var snapshotDir = filepath.Join("testdata", "snapshots")

// ─── Helpers ─────────────────────────────────────────────────────────────────

// stripANSI removes ANSI escape sequences, returning plain text.
func stripANSI(s string) string {
	// Matches ESC[ ... m (SGR) and other common sequences
	re := regexp.MustCompile(`\x1b\[[0-9;]*[a-zA-Z]`)
	return re.ReplaceAllString(s, "")
}

// renderLines splits a rendered string into lines of plain text.
func renderLines(s string) []string {
	plain := stripANSI(s)
	return strings.Split(plain, "\n")
}

// visibleWidth returns the visible column width of a single plain-text line.
func lineWidth(line string) int {
	// lipgloss.Width handles multi-byte runes correctly
	return lipgloss.Width(line)
}

// maxWidth returns the maximum visible width across all lines.
func maxWidth(lines []string) int {
	max := 0
	for _, l := range lines {
		if w := visibleWidth(l); w > max {
			max = w
		}
	}
	return max
}

// saveSnapshot writes rendered output to testdata/snapshots/<name>.txt.
func saveSnapshot(t *testing.T, name, rendered string) {
	t.Helper()
	if err := os.MkdirAll(snapshotDir, 0o755); err != nil {
		t.Fatalf("create snapshot dir: %v", err)
	}
	path := filepath.Join(snapshotDir, name+".txt")
	plain := stripANSI(rendered)
	if err := os.WriteFile(path, []byte(plain), 0o644); err != nil {
		t.Fatalf("write snapshot %s: %v", path, err)
	}
	t.Logf("snapshot → %s", path)
}

// checkOverflow fails if any line exceeds maxW visible columns.
func checkOverflow(t *testing.T, name string, lines []string, maxW int) {
	t.Helper()
	for i, line := range lines {
		if w := lineWidth(line); w > maxW {
			t.Errorf("%s: line %d overflows terminal (width %d > %d):\n  %q", name, i+1, w, maxW, line)
		}
	}
}

// checkMinHeight fails if the rendered output is fewer than minH lines.
func checkMinHeight(t *testing.T, name string, lines []string, minH int) {
	t.Helper()
	if len(lines) < minH {
		t.Errorf("%s: output only %d lines, expected >= %d", name, len(lines), minH)
	}
}

// checkContains fails if none of the lines contain the expected substring.
func checkContains(t *testing.T, name, expected string, lines []string) {
	t.Helper()
	for _, l := range lines {
		if strings.Contains(l, expected) {
			return
		}
	}
	t.Errorf("%s: rendered output does not contain %q", name, expected)
}

// checkBorder validates that the output has rounded border characters (╭ ╰).
func checkBorder(t *testing.T, name string, lines []string) {
	t.Helper()
	full := strings.Join(lines, "\n")
	if !strings.Contains(full, "╭") && !strings.Contains(full, "┌") {
		t.Errorf("%s: no top border character found in output", name)
	}
}

// renderApp renders the full app at the given size with the given active view.
func renderApp(t *testing.T, viewID ViewID) (string, []string) {
	t.Helper()
	app := newTestApp()

	// Send window size
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	// Navigate to the target view
	if viewID != ViewDashboard {
		result, _ = app.Update(NavSelectMsg{View: viewID})
		app = result.(*AppModel)
		// Propagate size to new view
		result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
		app = result.(*AppModel)
	}

	rendered := app.View().Content
	lines := renderLines(rendered)
	return rendered, lines
}

// ─── Visual Snapshot Tests ────────────────────────────────────────────────────

func TestVisualSnapshots(t *testing.T) {
	if err := os.MkdirAll(snapshotDir, 0o755); err != nil {
		t.Fatalf("create snapshot dir: %v", err)
	}

	// Build a base app with correct dimensions
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	views := []struct {
		name   string
		viewID ViewID
	}{
		{"01_dashboard", ViewDashboard},
		{"02_agents_list", ViewAgents},
		{"03_executions", ViewExecutions},
		{"04_server", ViewServer},
		{"05_credentials", ViewCredentials},
		{"06_doctor", ViewDoctor},
		{"07_configure", ViewConfigure},
		{"08_skills", ViewSkills},
	}

	for _, v := range views {
		t.Run(v.name, func(t *testing.T) {
			rendered, lines := renderApp(t, v.viewID)

			// Save snapshot
			saveSnapshot(t, v.name, rendered)

			// Validate
			checkOverflow(t, v.name, lines, snapW)
			checkMinHeight(t, v.name, lines, snapH-5)
			checkBorder(t, v.name, lines)
		})
	}
}

// ─── Specific Alignment Tests ─────────────────────────────────────────────────

func TestLayoutHeader(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)

	if len(lines) == 0 {
		t.Fatal("no output rendered")
	}
	header := lines[0]

	// Header must contain the logo
	if !strings.Contains(header, "agentspan") {
		t.Errorf("header line does not contain 'agentspan': %q", header)
	}
	// Header must contain server status
	if !strings.Contains(header, "server") && !strings.Contains(header, "live") &&
		!strings.Contains(header, "offline") && !strings.Contains(header, "checking") {
		t.Errorf("header does not contain server status: %q", header)
	}
	// Header width should not exceed terminal width
	if w := lineWidth(header); w > snapW {
		t.Errorf("header overflows: width %d > %d", w, snapW)
	}
}

func TestLayoutFooter(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)

	if len(lines) == 0 {
		t.Fatal("no output")
	}
	// Footer is the last non-empty line
	footer := ""
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) != "" {
			footer = lines[i]
			break
		}
	}
	if footer == "" {
		t.Fatal("no footer line found")
	}
	if !strings.Contains(footer, "navigate") && !strings.Contains(footer, "open") &&
		!strings.Contains(footer, "quit") && !strings.Contains(footer, "help") {
		t.Errorf("footer doesn't contain expected hints: %q", footer)
	}
}

func TestLayoutSidebar(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)

	// Every body line (after header, before footer) should have content
	// from the sidebar at the expected column position
	navItems := []string{"Dashboard", "Agents", "Executions", "Server",
		"Credentials", "Doctor", "Configure"}

	plain := strings.Join(lines, "\n")
	for _, item := range navItems {
		if !strings.Contains(plain, item) {
			t.Errorf("sidebar missing nav item: %q", item)
		}
	}
}

func TestLayoutContentPanelFills(t *testing.T) {
	// The content panel should fill close to the full terminal height/width
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)

	// Should have approximately snapH lines total
	if len(lines) < snapH-5 {
		t.Errorf("output too short: %d lines, expected ~%d", len(lines), snapH)
	}
	if len(lines) > snapH+2 {
		t.Errorf("output overflows terminal: %d lines > %d", len(lines), snapH)
	}

	// Content width should be close to snapW
	mw := maxWidth(lines)
	if mw < snapW-10 {
		t.Errorf("content too narrow: max line width %d, expected ~%d", mw, snapW)
	}
	if mw > snapW {
		t.Errorf("content overflows terminal: max line width %d > %d", mw, snapW)
	}
}

func TestAgentsPaneButtons(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)
	result, _ = app.Update(NavSelectMsg{View: ViewAgents})
	app = result.(*AppModel)
	result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")

	// Check all action buttons appear
	buttons := []string{"run", "new", "examples", "deploy", "delete", "search", "refresh"}
	for _, btn := range buttons {
		if !strings.Contains(strings.ToLower(plain), btn) {
			t.Errorf("agents view missing button label %q", btn)
		}
	}
}

func TestAgentsButtonBarNavigation(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)
	result, _ = app.Update(NavSelectMsg{View: ViewAgents})
	app = result.(*AppModel)
	result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	// Tab into content, then press ↓ until we reach the button bar
	// (on empty list, 1 down press should reach buttons)
	for i := 0; i < 5; i++ {
		result, _ = app.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyDown}))
		app = result.(*AppModel)
	}

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")

	// Should still show all buttons
	if !strings.Contains(strings.ToLower(plain), "run") {
		t.Error("action buttons disappeared after navigation")
	}
}

func TestServerViewContainsMetrics(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)
	result, _ = app.Update(NavSelectMsg{View: ViewServer})
	app = result.(*AppModel)
	result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")

	// Server view should show status and key sections
	checkContains(t, "server", "Server", lines)
	checkContains(t, "server", "Logs", lines)

	// Should have stop or start button
	if !strings.Contains(plain, "stop") && !strings.Contains(plain, "start") {
		t.Error("server view missing start/stop button")
	}
}

func TestDoctorViewSections(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)
	result, _ = app.Update(NavSelectMsg{View: ViewDoctor})
	app = result.(*AppModel)
	result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")

	// Doctor always shows the title
	if !strings.Contains(plain, "System Diagnostics") {
		t.Error("doctor view missing 'System Diagnostics' title")
	}

	// Checks are async — either loading spinner or results are valid
	hasSpinner := strings.Contains(plain, "Running diagnostics") || strings.Contains(plain, "running")
	hasSections := strings.Contains(plain, "System") || strings.Contains(plain, "AI Providers")
	hasChecks := strings.Contains(plain, "✓") || strings.Contains(plain, "✗") || strings.Contains(plain, "–")

	if !hasSpinner && !hasSections && !hasChecks {
		t.Error("doctor view shows neither loading state nor results")
	}
	if hasSpinner {
		t.Log("doctor: async checks still loading (expected in unit tests)")
	}
}

func TestConfigureViewForm(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)
	result, _ = app.Update(NavSelectMsg{View: ViewConfigure})
	app = result.(*AppModel)
	result, _ = app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")

	// Configure view should show the URL field
	if !strings.Contains(plain, "Server URL") {
		t.Error("configure view missing 'Server URL' field")
	}
	if !strings.Contains(plain, "Config file") {
		t.Error("configure view missing config file summary")
	}
}

func TestHelpOverlayRendering(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	// Toggle help overlay
	result, _ = app.Update(tea.KeyPressMsg(tea.Key{Text: "?"}))
	app = result.(*AppModel)

	if !app.showHelp {
		t.Fatal("help overlay not showing after '?' keypress")
	}

	rendered := app.View().Content
	lines := renderLines(rendered)
	plain := strings.Join(lines, "\n")
	saveSnapshot(t, "help_overlay", rendered)

	// Should contain keyboard shortcut sections
	if !strings.Contains(plain, "navigate") {
		t.Error("help overlay missing navigation hints")
	}
	if !strings.Contains(plain, "close") && !strings.Contains(plain, "esc") {
		t.Error("help overlay missing close hint")
	}
	checkOverflow(t, "help_overlay", lines, snapW)
}

func TestAllViewsNoOverflow(t *testing.T) {
	viewIDs := []struct {
		id   ViewID
		name string
	}{
		{ViewDashboard, "dashboard"},
		{ViewAgents, "agents"},
		{ViewExecutions, "executions"},
		{ViewServer, "server"},
		{ViewCredentials, "credentials"},
		{ViewDoctor, "doctor"},
		{ViewConfigure, "configure"},
		{ViewSkills, "skills"},
	}

	for _, v := range viewIDs {
		t.Run(v.name, func(t *testing.T) {
			_, lines := renderApp(t, v.id)
			checkOverflow(t, v.name, lines, snapW)
		})
	}
}

func TestAllViewsFillHeight(t *testing.T) {
	viewIDs := []struct {
		id   ViewID
		name string
		minH int // minimum expected height
	}{
		{ViewDashboard, "dashboard", snapH - 8},
		{ViewAgents, "agents", snapH - 8},
		{ViewServer, "server", snapH - 8},
		{ViewDoctor, "doctor", snapH - 8},
	}

	for _, v := range viewIDs {
		t.Run(v.name, func(t *testing.T) {
			_, lines := renderApp(t, v.id)
			if len(lines) < v.minH {
				t.Errorf("%s: only %d lines rendered, expected >= %d (terminal height %d)",
					v.name, len(lines), v.minH, snapH)
			}
		})
	}
}

// ─── Print report ────────────────────────────────────────────────────────────

func TestVisualReport(t *testing.T) {
	app := newTestApp()
	result, _ := app.Update(tea.WindowSizeMsg{Width: snapW, Height: snapH})
	app = result.(*AppModel)

	report := &strings.Builder{}
	fmt.Fprintf(report, "\n═══ TUI Visual Validation Report ═══\n")
	fmt.Fprintf(report, "Terminal: %d×%d\n\n", snapW, snapH)

	viewIDs := []struct {
		id   ViewID
		name string
	}{
		{ViewDashboard, "Dashboard"},
		{ViewAgents, "Agents"},
		{ViewExecutions, "Executions"},
		{ViewServer, "Server"},
		{ViewCredentials, "Credentials"},
		{ViewDoctor, "Doctor"},
		{ViewConfigure, "Configure"},
		{ViewSkills, "Skills"},
	}

	allOK := true
	for _, v := range viewIDs {
		_, lines := renderApp(t, v.id)

		h := len(lines)
		mw := maxWidth(lines)
		overflow := mw > snapW
		tooShort := h < snapH-8

		status := "✓"
		if overflow || tooShort {
			status = "✗"
			allOK = false
		}

		fmt.Fprintf(report, "  %s  %-16s  height=%d/%d  maxWidth=%d/%d",
			status, v.name, h, snapH, mw, snapW)
		if overflow {
			fmt.Fprintf(report, "  ← OVERFLOW by %d", mw-snapW)
		}
		if tooShort {
			fmt.Fprintf(report, "  ← TOO SHORT by %d", snapH-8-h)
		}
		fmt.Fprintln(report)
	}

	fmt.Fprintln(report)
	if allOK {
		fmt.Fprintf(report, "  All views pass alignment checks ✓\n")
	} else {
		fmt.Fprintf(report, "  Some views have alignment issues — see above ✗\n")
	}
	fmt.Fprintf(report, "\n  Snapshots saved to: cli/tui/testdata/snapshots/\n")
	fmt.Fprintln(report, "═════════════════════════════════════")

	t.Log(report.String())

	// Save the report
	if err := os.MkdirAll(snapshotDir, 0o755); err == nil {
		_ = os.WriteFile(filepath.Join(snapshotDir, "00_report.txt"), []byte(report.String()), 0o644)
	}
}

// ─── ContentWidth/Height regression ─────────────────────────────────────────

func TestUIHelpers(t *testing.T) {
	cases := []struct{ w, h int }{
		{220, 50}, {120, 30}, {80, 24}, {200, 60},
	}
	for _, c := range cases {
		cw := ui.ContentWidth(c.w)
		ch := ui.ContentHeight(c.h)
		if cw <= 0 {
			t.Errorf("ContentWidth(%d)=%d, want > 0", c.w, cw)
		}
		if ch <= 0 {
			t.Errorf("ContentHeight(%d)=%d, want > 0", c.h, ch)
		}
		if cw >= c.w {
			t.Errorf("ContentWidth(%d)=%d must be < terminal width", c.w, cw)
		}
		if ch >= c.h {
			t.Errorf("ContentHeight(%d)=%d must be < terminal height", c.h, ch)
		}
	}
}
