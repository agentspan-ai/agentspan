package views

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/internal/serverctl"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type ServerStatusMsg struct {
	Healthy bool
	Err     error
}

type ServerLogLineMsg struct {
	Lines []string
}

type ServerStartedMsg struct {
	PID int
	Err error
}

type ServerStoppedMsg struct {
	Err error
}

// ServerStartProgressMsg carries a live event from the launch goroutine.
type ServerStartProgressMsg struct {
	Stage   string
	Message string
}

type ServerTickMsg struct{ Time time.Time }

// ServerMetrics holds live resource usage for the server process.
type ServerMetrics struct {
	PID     int
	CPUPct  string // e.g. "12.4%"
	MemRSS  string // e.g. "512 MB"
	Uptime  string // e.g. "2h 14m"
	Threads string // e.g. "42"
	Err     error
}

type ServerMetricsMsg struct {
	Metrics ServerMetrics
}

// ─── Server Actions ──────────────────────────────────────────────────────────

type ServerAction int

const (
	ServerActionNone ServerAction = iota
	ServerActionConfirmStop
	ServerActionStarting
	ServerActionStopping
)

// ─── Model ───────────────────────────────────────────────────────────────────

type ServerModel struct {
	client        *client.Client
	width         int
	height        int
	healthy       bool
	checking      bool
	action        ServerAction
	logLines      []string
	vp            viewport.Model
	following     bool
	logPath       string
	tick          int
	err           string
	spinTick      int
	metrics       ServerMetrics
	startProgress []string // live lines during server start
}

func NewServer(c *client.Client) ServerModel {
	home, _ := os.UserHomeDir()
	logPath := filepath.Join(home, ".agentspan", "server", "server.log")
	return ServerModel{
		client:    c,
		checking:  true,
		following: true,
		logPath:   logPath,
	}
}

func (m ServerModel) Init() tea.Cmd {
	return tea.Batch(
		m.checkHealth(),
		m.loadLogs(),
		serverTickCmd(),
	)
}

// statusCardLines is the fixed height (lines) of the status card section.
// Status card: title(1) + divider(1) + 4 rows + buttons(1) + padding(2) + border(2) = ~11
const statusCardLines = 11

// logViewportHeight computes viewport rows for the log panel.
// Breakdown of fixed rows inside the content panel (inner = ContentHeight - 2):
//
//	title "Server" + blank line = 2
//	status card border(top+bottom) = 2, card content = 2  → 4
//	sep line = 1
//	log heading line = 1
//	hint bar (HintBar pill: top border + content + bottom border) = 3
//	log frame border (top+bottom via Height(vpH+2)) counted separately
//
// Fixed overhead = 2 + 4 + 1 + 1 + 3 = 11
func (m ServerModel) logViewportHeight() int {
	inner := ui.ContentHeight(m.height) - 2 // subtract panel border rows
	const overhead = 13                     // measured from snapshot: each component renders more rows than estimated
	h := inner - overhead
	if h < 5 {
		h = 5
	}
	return h
}

func (m ServerModel) Update(msg tea.Msg) (ServerModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.vp.SetWidth(ui.ContentWidth(m.width) - 6)
		m.vp.SetHeight(m.logViewportHeight())

	case ServerTickMsg:
		m.spinTick++
		return m, tea.Batch(serverTickCmd(), m.checkHealth(), m.loadLogs(), m.fetchMetrics())

	case ServerStatusMsg:
		m.checking = false
		m.healthy = msg.Healthy

	case ServerMetricsMsg:
		m.metrics = msg.Metrics

	case ServerLogLineMsg:
		m.logLines = msg.Lines
		content := strings.Join(m.logLines, "\n")
		m.vp.SetContent(content)
		if m.following {
			m.vp.GotoBottom()
		}

	case ServerStartProgressMsg:
		m.startProgress = append(m.startProgress, msg.Message)

	case serverStartProgressWithNext:
		m.startProgress = append(m.startProgress, msg.msg.Message)
		return m, continueStartCmd(msg.ch)

	case ServerStartedMsg:
		m.action = ServerActionNone
		m.startProgress = nil
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.err = ""
			m.healthy = true
			m.checking = false
			return m, tea.Batch(m.checkHealth(), m.loadLogs())
		}

	case ServerStoppedMsg:
		m.action = ServerActionNone
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.err = ""
			m.healthy = false
			m.checking = true
			return m, m.checkHealth()
		}

	case tea.KeyPressMsg:
		// Confirm stop dialog
		if m.action == ServerActionConfirmStop {
			switch msg.String() {
			case "y", "Y", "enter":
				m.action = ServerActionStopping
				return m, m.stopServer()
			case "n", "N", "esc":
				m.action = ServerActionNone
			}
			return m, nil
		}

		switch msg.String() {
		case "s":
			if !m.healthy {
				m.action = ServerActionStarting
				return m, m.startServer()
			}
		case "t":
			if m.healthy {
				m.action = ServerActionConfirmStop
			}
		case "f":
			m.following = !m.following
			if m.following {
				m.vp.GotoBottom()
			}
		case "R":
			m.checking = true
			m.err = ""
			return m, tea.Batch(m.checkHealth(), m.loadLogs())
		case "up", "k":
			m.following = false
			m.vp.ScrollUp(1)
		case "down", "j":
			m.vp.ScrollDown(1)
		}
	}
	return m, nil
}

func (m ServerModel) View() string {
	cw := ui.ContentWidth(m.width)
	ch := ui.ContentHeight(m.height)
	innerW := cw - 4 // inside content panel border + padding

	// ── Status bar (compact single line across the top) ──────────────────
	statusBar := m.renderStatusBar(innerW)

	// ── Optional banners (confirm / error / action) ───────────────────────
	var banners string
	if m.action == ServerActionConfirmStop {
		banners += lipgloss.NewStyle().
			Foreground(ui.ColorYellow).Bold(true).
			Render("  Stop the server? [y/N]") + "\n"
	}
	if m.err != "" {
		banners += ui.ErrorBanner(innerW, m.err) + "\n"
	}
	if m.action == ServerActionStarting {
		// Show live progress lines from the launch goroutine
		for _, line := range m.startProgress {
			banners += lipgloss.NewStyle().Foreground(ui.ColorGreen).
				Render("  ✓  "+line) + "\n"
		}
		banners += lipgloss.NewStyle().Foreground(ui.ColorYellow).
			Render(fmt.Sprintf("  %s  Starting server...", ui.SpinnerFrame(m.spinTick))) + "\n"
	} else if m.action == ServerActionStopping {
		banners += lipgloss.NewStyle().Foreground(ui.ColorYellow).
			Render(fmt.Sprintf("  %s  Stopping server...", ui.SpinnerFrame(m.spinTick))) + "\n"
	}

	// ── Log viewport — takes all remaining space ──────────────────────────
	vpH := m.logViewportHeight()
	// Re-size viewport to match current dimensions every frame
	m.vp.SetWidth(innerW - 2)
	m.vp.SetHeight(vpH)

	followIndicator := ""
	if m.following {
		followIndicator = "  " + lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("[↓ following]")
	} else {
		followIndicator = "  " + ui.DimStyle.Render("[f to follow]")
	}

	logHeading := ui.SectionHeadingStyle.Render("Server Logs") + followIndicator
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", innerW))

	logFrame := lipgloss.NewStyle().
		Border(lipgloss.NormalBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Background(ui.ColorDeepBg).
		Width(innerW).
		Height(vpH + 2). // +2 for border rows
		Render(m.vp.View())

	hint := ui.HintBar(
		ui.ButtonDef{Key: "f", Label: "follow"},
		ui.ButtonDef{Key: "↑↓", Label: "scroll"},
		ui.ButtonDef{Key: "s", Label: "start"},
		ui.ButtonDef{Key: "t", Label: "stop", Danger: true},
		ui.ButtonDef{Key: "R", Label: "refresh"},
	)

	body := statusBar + "\n" +
		banners +
		sep + "\n" +
		logHeading + "\n" +
		logFrame + "\n" +
		hint

	return ui.ContentPanel(cw, ch, "Server", body)
}

// renderStatusBar renders the server status card with metrics + action buttons.
func (m ServerModel) renderStatusBar(width int) string {
	dim := ui.DimStyle
	val := lipgloss.NewStyle().Foreground(ui.ColorWhite)

	// Status indicator
	var statusStr string
	if m.checking {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorYellow).
			Render(fmt.Sprintf("%s checking...", ui.SpinnerFrame(m.spinTick)))
	} else if m.healthy {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorGreen).Bold(true).Render("● Running")
	} else {
		statusStr = lipgloss.NewStyle().Foreground(ui.ColorRed).Bold(true).Render("◌ Offline")
	}

	// JAR size
	home, _ := os.UserHomeDir()
	jarPath := filepath.Join(home, ".agentspan", "server", "agentspan-runtime.jar")
	var jarInfo string
	if fi, err := os.Stat(jarPath); err == nil {
		jarInfo = fmt.Sprintf("%.0f MB", float64(fi.Size())/1024/1024)
	} else {
		jarInfo = "not cached"
	}

	// Metric rows
	rows := []string{
		lipgloss.JoinHorizontal(lipgloss.Top,
			dim.Render("Status  "), statusStr,
			"    ",
			dim.Render("JAR  "), val.Render(jarInfo),
		),
	}

	mx := m.metrics
	if mx.PID > 0 {
		rows = append(rows,
			lipgloss.JoinHorizontal(lipgloss.Top,
				dim.Render("PID     "), val.Render(fmt.Sprintf("%d", mx.PID)),
				"    ",
				dim.Render("CPU  "), val.Render(mx.CPUPct),
				"    ",
				dim.Render("RAM  "), val.Render(mx.MemRSS),
				"    ",
				dim.Render("Uptime  "), val.Render(mx.Uptime),
			),
		)
		if mx.Threads != "" {
			rows = append(rows,
				lipgloss.JoinHorizontal(lipgloss.Top,
					dim.Render("Threads  "), val.Render(mx.Threads),
				),
			)
		}
	}

	// Action button
	var btn string
	if m.healthy {
		btn = ui.Button("t  stop", false, true)
	} else {
		btn = ui.Button("s  start", true, false)
	}

	// Build the card: rows on left, button on right
	bodyLines := strings.Join(rows, "\n")
	bodyLinesW := lipgloss.Width(bodyLines)
	btnW := lipgloss.Width(btn)
	gap := width - 4 - bodyLinesW - btnW - 2
	if gap < 1 {
		gap = 1
	}

	// First line: status + jar + gap + button
	firstLine := rows[0] + strings.Repeat(" ", gap) + btn
	var cardBody string
	if len(rows) > 1 {
		cardBody = firstLine + "\n" + strings.Join(rows[1:], "\n")
	} else {
		cardBody = firstLine
	}

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ui.ColorDarkGreen).
		Width(width).
		Padding(0, 1).
		Render(cardBody)
}

// ─── Commands ────────────────────────────────────────────────────────────────

func serverTickCmd() tea.Cmd {
	return tea.Tick(5*time.Second, func(t time.Time) tea.Msg {
		return ServerTickMsg{Time: t}
	})
}

func (m ServerModel) checkHealth() tea.Cmd {
	return func() tea.Msg {
		err := m.client.HealthCheck()
		return ServerStatusMsg{Healthy: err == nil, Err: err}
	}
}

func (m ServerModel) loadLogs() tea.Cmd {
	logPath := m.logPath
	return func() tea.Msg {
		f, err := os.Open(logPath)
		if err != nil {
			return ServerLogLineMsg{Lines: []string{
				ui.DimStyle.Render("  (log file not found — server may not have started yet)")}}
		}
		defer f.Close()

		var lines []string
		scanner := bufio.NewScanner(f)
		for scanner.Scan() {
			lines = append(lines, scanner.Text())
		}
		// Keep last 200 lines
		if len(lines) > 200 {
			lines = lines[len(lines)-200:]
		}
		return ServerLogLineMsg{Lines: lines}
	}
}

func (m ServerModel) startServer() tea.Cmd {
	// Send a stream of progress events then a final Started/Error message.
	// Uses a channel so the goroutine can send incremental progress back to
	// the BubbleTea loop via returned Cmds.
	return func() tea.Msg {
		jarPath := serverctl.DefaultJarPath()

		// Step 1: ensure JAR exists (download if needed)
		progressCh := make(chan serverctl.StartEvent, 20)

		// Run everything in a goroutine, return first progress event immediately.
		// The TUI will keep calling nextStartEvent(progressCh) for subsequent ones.
		go func() {
			if err := serverctl.EnsureJAR(jarPath, func(pct float64, msg string) {
				progressCh <- serverctl.StartEvent{Stage: "jar", Message: msg}
			}); err != nil {
				progressCh <- serverctl.StartEvent{Stage: "error", Message: err.Error()}
				close(progressCh)
				return
			}
			progressCh <- serverctl.StartEvent{Stage: "jar", Message: "JAR ready"}

			pid, err := serverctl.Launch(jarPath, serverctl.Options{Port: "6767"}, progressCh)
			if err != nil {
				progressCh <- serverctl.StartEvent{Stage: "error", Message: fmt.Sprintf("err:%s", err.Error())}
			} else {
				progressCh <- serverctl.StartEvent{Stage: "ready", Message: fmt.Sprintf("done:%d", pid)}
			}
			close(progressCh)
		}()

		return nextStartEvent(progressCh)
	}
}

// nextStartEvent reads the next event from the start progress channel and
// converts it to the appropriate tea.Msg.
func nextStartEvent(ch <-chan serverctl.StartEvent) tea.Msg {
	evt, ok := <-ch
	if !ok {
		return ServerStartedMsg{Err: fmt.Errorf("start channel closed unexpectedly")}
	}
	switch evt.Stage {
	case "ready":
		var pid int
		fmt.Sscanf(strings.TrimPrefix(evt.Message, "done:"), "%d", &pid)
		return ServerStartedMsg{PID: pid}
	case "error":
		return ServerStartedMsg{Err: fmt.Errorf("%s", strings.TrimPrefix(evt.Message, "err:"))}
	default:
		// Progress event — return it and schedule reading the next one
		return serverStartProgressWithNext{
			msg: ServerStartProgressMsg{Stage: evt.Stage, Message: evt.Message},
			ch:  ch,
		}
	}
}

// serverStartProgressWithNext carries a progress message plus the channel to
// continue reading from.
type serverStartProgressWithNext struct {
	msg ServerStartProgressMsg
	ch  <-chan serverctl.StartEvent
}

// continueStartCmd returns a Cmd that reads the next event from the channel.
func continueStartCmd(ch <-chan serverctl.StartEvent) tea.Cmd {
	return func() tea.Msg {
		return nextStartEvent(ch)
	}
}

func (m ServerModel) stopServer() tea.Cmd {
	return func() tea.Msg {
		if err := serverctl.Stop(); err != nil {
			return ServerStoppedMsg{Err: err}
		}
		return ServerStoppedMsg{}
	}
}

// fetchMetrics reads PID file and uses `ps` to get CPU/RAM/threads for the
// server process. Works on macOS and Linux. Falls back gracefully if missing.
func (m ServerModel) fetchMetrics() tea.Cmd {
	return func() tea.Msg {
		home, _ := os.UserHomeDir()
		pidFile := filepath.Join(home, ".agentspan", "server", "server.pid")
		data, err := os.ReadFile(pidFile)
		if err != nil {
			return ServerMetricsMsg{Metrics: ServerMetrics{}}
		}
		var pid int
		fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &pid)
		if pid <= 0 {
			return ServerMetricsMsg{Metrics: ServerMetrics{}}
		}

		mx := ServerMetrics{PID: pid}

		// CPU% and RSS (in KB on Linux, KB on macOS via ps -o rss)
		out, err := exec.Command("ps", "-p", fmt.Sprintf("%d", pid),
			"-o", "%cpu,rss,nlwp,etime", "--no-headers").Output()
		if err != nil {
			// Try macOS format (no --no-headers)
			out, err = exec.Command("ps", "-p", fmt.Sprintf("%d", pid),
				"-o", "%cpu=,rss=,nlwp=,etime=").Output()
		}
		if err == nil {
			fields := strings.Fields(strings.TrimSpace(string(out)))
			if len(fields) >= 1 {
				mx.CPUPct = fields[0] + "%"
			}
			if len(fields) >= 2 {
				rssKB := 0
				fmt.Sscanf(fields[1], "%d", &rssKB)
				if rssKB > 1024*1024 {
					mx.MemRSS = fmt.Sprintf("%.1f GB", float64(rssKB)/1024/1024)
				} else if rssKB > 1024 {
					mx.MemRSS = fmt.Sprintf("%.0f MB", float64(rssKB)/1024)
				} else {
					mx.MemRSS = fmt.Sprintf("%d KB", rssKB)
				}
			}
			if len(fields) >= 3 {
				mx.Threads = fields[2]
			}
			if len(fields) >= 4 {
				mx.Uptime = formatElapsed(fields[3])
			}
		}
		return ServerMetricsMsg{Metrics: mx}
	}
}

// formatElapsed converts ps etime format (e.g. "02:14:32" or "1-02:14:32") to a human string.
func formatElapsed(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return ""
	}
	// Handle day prefix "D-HH:MM:SS"
	days := 0
	if idx := strings.Index(s, "-"); idx >= 0 {
		fmt.Sscanf(s[:idx], "%d", &days)
		s = s[idx+1:]
	}
	parts := strings.Split(s, ":")
	var h, min, sec int
	switch len(parts) {
	case 3:
		fmt.Sscanf(parts[0], "%d", &h)
		fmt.Sscanf(parts[1], "%d", &min)
		fmt.Sscanf(parts[2], "%d", &sec)
	case 2:
		fmt.Sscanf(parts[0], "%d", &min)
		fmt.Sscanf(parts[1], "%d", &sec)
	}
	h += days * 24
	switch {
	case h > 0:
		return fmt.Sprintf("%dh %dm", h, min)
	case min > 0:
		return fmt.Sprintf("%dm %ds", min, sec)
	default:
		return fmt.Sprintf("%ds", sec)
	}
}

// FooterHints returns context-sensitive key hints.
func (m ServerModel) FooterHints() string {
	hints := []string{
		ui.KeyHint("f", "follow logs"),
		ui.KeyHint("↑↓", "scroll"),
	}
	if m.healthy {
		hints = append(hints, ui.KeyHint("t", "stop server"))
	} else {
		hints = append(hints, ui.KeyHint("s", "start server"))
	}
	hints = append(hints, ui.KeyHint("R", "refresh"), ui.KeyHint("q", "quit"))
	return strings.Join(hints, "  ")
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m ServerModel) Following() bool         { return m.following }
func (m ServerModel) Action() ServerAction    { return m.action }
func (m ServerModel) Err() string             { return m.err }
func (m ServerModel) Checking() bool          { return m.checking }
func (m *ServerModel) SetHealthy(v bool)      { m.healthy = v; m.checking = false }
func (m *ServerModel) SetErr(e string)        { m.err = e }

// WantsEsc returns true when there is a confirm dialog open.
func (m ServerModel) WantsEsc() bool {
	return m.action == ServerActionConfirmStop
}
