package views

import (
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type ConfigSavedMsg struct {
	Err error
}

// ─── Model ───────────────────────────────────────────────────────────────────

type ConfigureModel struct {
	width      int
	height     int
	serverURL  string
	authKey    string
	authSecret string
	form       *huh.Form
	saved      bool
	err        string
}

func NewConfigure(cfg *config.Config) ConfigureModel {
	m := ConfigureModel{
		serverURL:  cfg.ServerURL,
		authKey:    cfg.AuthKey,
		authSecret: cfg.AuthSecret,
	}
	m.form = m.buildForm()
	return m
}

func (m ConfigureModel) Init() tea.Cmd {
	if m.form != nil {
		return m.form.Init()
	}
	return nil
}

func (m ConfigureModel) Update(msg tea.Msg) (ConfigureModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case ConfigSavedMsg:
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.saved = true
			m.err = ""
		}

	case tea.KeyPressMsg:
		// huh does not bind esc to abort by default — intercept it here
		// to cancel the form and return to the content panel.
		if msg.String() == "esc" && m.form != nil && m.form.State == huh.StateNormal {
			m.form = m.buildForm()
			return m, m.form.Init()
		}
	}

	if m.form != nil {
		form, cmd := m.form.Update(msg)
		if f, ok := form.(*huh.Form); ok {
			m.form = f
			if m.form.State == huh.StateCompleted {
				m.serverURL = m.form.GetString("server_url")
				m.authKey = m.form.GetString("auth_key")
				m.authSecret = m.form.GetString("auth_secret")
				return m, m.saveConfig()
			}
		}
		return m, cmd
	}
	return m, nil
}

func (m ConfigureModel) View() string {
	cw := ui.ContentWidth(m.width)

	var content strings.Builder

	// Current config summary
	currentCfg := lipglossInfoBox(cw-4,
		"Current Configuration",
		[]string{
			ui.CardRow("Server URL", m.serverURL),
			ui.CardRow("Auth Key", maskValue(m.authKey)),
			ui.CardRow("Auth Secret", maskValue(m.authSecret)),
			ui.CardRow("Config file", "~/.agentspan/config.json"),
		},
	)
	content.WriteString(currentCfg + "\n\n")

	// Saved banner
	if m.saved {
		content.WriteString(ui.SuccessBanner(cw-4, "Configuration saved!") + "\n\n")
	}
	// Error banner
	if m.err != "" {
		content.WriteString(ui.ErrorBanner(cw-4, m.err) + "\n\n")
	}

	// Form
	if m.form != nil && m.form.State != huh.StateCompleted {
		content.WriteString(m.form.View())
	} else if m.saved {
		content.WriteString(ui.DimStyle.Render("  Press esc to go back or edit the form above."))
	}

	return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Configure", content.String())
}

func (m *ConfigureModel) buildForm() *huh.Form {
	return huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Key("server_url").
				Title("Server URL").
				Description("AgentSpan runtime server URL").
				Placeholder("http://localhost:6767").
				Value(&m.serverURL),

			huh.NewInput().
				Key("auth_key").
				Title("Auth Key").
				Description("Optional: for Orkes Cloud auth").
				Value(&m.authKey),

			huh.NewInput().
				Key("auth_secret").
				Title("Auth Secret").
				Description("Optional: for Orkes Cloud auth").
				EchoMode(huh.EchoModePassword).
				Value(&m.authSecret),
		),
	).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

func (m ConfigureModel) saveConfig() tea.Cmd {
	serverURL := m.serverURL
	authKey := m.authKey
	authSecret := m.authSecret
	if m.form != nil {
		serverURL = m.form.GetString("server_url")
		authKey = m.form.GetString("auth_key")
		authSecret = m.form.GetString("auth_secret")
	}
	return func() tea.Msg {
		cfg := config.Load()
		cfg.ServerURL = serverURL
		cfg.AuthKey = authKey
		cfg.AuthSecret = authSecret
		saveErr := config.Save(cfg)
		return ConfigSavedMsg{Err: saveErr}
	}
}

func maskValue(v string) string {
	if v == "" {
		return ui.DimStyle.Render("(not set)")
	}
	if len(v) <= 8 {
		return strings.Repeat("●", len(v))
	}
	return v[:4] + strings.Repeat("●", 8) + v[len(v)-4:]
}

func lipglossInfoBox(width int, title string, rows []string) string {
	return ui.Card(width, title, rows...)
}

// FormActive returns true when the huh form is currently being edited.
// This tells the app to forward ALL keys (including esc/tab) to this view.
func (m ConfigureModel) FormActive() bool {
	return m.form != nil && m.form.State == huh.StateNormal
}

// FooterHints returns context-sensitive key hints.
func (m ConfigureModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("tab", "next field"),
		ui.KeyHint("enter", "save"),
		ui.KeyHint("esc", "back"),
	}, "  ")
}
