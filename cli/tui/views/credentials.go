package views

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// ─── Messages ────────────────────────────────────────────────────────────────

type SecretsLoadedMsg struct {
	Creds []client.CredentialMeta
	Err   error
}

type SecretActionMsg struct {
	Action string
	Err    error
}

// ─── Buttons ─────────────────────────────────────────────────────────────────

var secButtons = []ui.ButtonDef{
	{Key: "a", Label: "add"},
	{Key: "d", Label: "delete", Danger: true},
	{Key: "R", Label: "refresh"},
}

// ─── Model ───────────────────────────────────────────────────────────────────

type CredentialsModel struct {
	client    *client.Client
	width     int
	height    int
	creds     []client.CredentialMeta
	cursor    int
	btnCursor int // -1 = table, >=0 = button bar
	loading   bool
	err       string
	success   string
	tick      int

	// Add form
	addMode    bool
	addName    string
	addValue   string
	addForm    *huh.Form
	delConfirm bool
}

func NewCredentials(c *client.Client) CredentialsModel {
	return CredentialsModel{
		client:    c,
		loading:   true,
		btnCursor: -1,
	}
}

func (m CredentialsModel) Init() tea.Cmd {
	return tea.Batch(m.loadAll(), ui.SpinnerTickCmd())
}

func (m CredentialsModel) Update(msg tea.Msg) (CredentialsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

	case SecretsLoadedMsg:
		m.loading = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.creds = msg.Creds
			m.cursor = 0
		}

	case SecretActionMsg:
		m.addMode = false
		m.delConfirm = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.success = msg.Action + " successfully"
			m.err = ""
			return m, m.loadAll()
		}

	case ui.SpinnerTickMsg:
		m.tick++
		return m, ui.SpinnerTickCmd()

	case tea.KeyPressMsg:
		// When add form is active, send ALL keys to the form
		if m.addMode && m.addForm != nil && m.addForm.State == huh.StateNormal {
			if msg.String() == "esc" {
				m.addMode = false
				m.addForm = nil
				return m, nil
			}
			form, cmd := m.addForm.Update(msg)
			if f, ok := form.(*huh.Form); ok {
				m.addForm = f
				if m.addForm.State == huh.StateCompleted {
					m.addName = m.addForm.GetString("name")
					m.addValue = m.addForm.GetString("value")
					return m, m.saveCredential()
				}
				if m.addForm.State == huh.StateAborted {
					m.addMode = false
					m.addForm = nil
				}
			}
			return m, cmd
		}

		if m.delConfirm {
			switch msg.String() {
			case "y", "Y", "enter":
				return m, m.deleteSelected()
			case "n", "N", "esc":
				m.delConfirm = false
			}
			return m, nil
		}

		return m.handleKey(msg.String())
	}

	if m.addMode && m.addForm != nil {
		form, cmd := m.addForm.Update(msg)
		if f, ok := form.(*huh.Form); ok {
			m.addForm = f
			if m.addForm.State == huh.StateCompleted {
				m.addName = m.addForm.GetString("name")
				m.addValue = m.addForm.GetString("value")
				return m, m.saveCredential()
			}
			if m.addForm.State == huh.StateAborted {
				m.addMode = false
				m.addForm = nil
				return m, nil
			}
		}
		return m, cmd
	}

	return m, nil
}

func (m CredentialsModel) handleKey(key string) (CredentialsModel, tea.Cmd) {
	switch key {
	case "up", "k":
		if m.btnCursor >= 0 {
			m.btnCursor = -1
		} else if m.cursor > 0 {
			m.cursor--
		}

	case "down", "j":
		if m.btnCursor >= 0 {
			// already on buttons
		} else if m.cursor < m.rowCount()-1 {
			m.cursor++
		} else {
			m.btnCursor = 0
		}

	case "left", "h":
		if m.btnCursor > 0 {
			m.btnCursor--
		}

	case "right", "l":
		if m.btnCursor >= 0 && m.btnCursor < len(secButtons)-1 {
			m.btnCursor++
		}

	case "enter", " ", "space":
		if m.btnCursor >= 0 {
			return m.activateButton(m.btnCursor)
		}

	case "a":
		m.addMode = true
		m.addName = ""
		m.addValue = ""
		m.addForm = m.buildAddForm()
		m.btnCursor = -1
		return m, m.addForm.Init()

	case "d":
		if m.rowCount() > 0 {
			m.delConfirm = true
		}

	case "R":
		m.loading = true
		m.err = ""
		m.success = ""
		return m, m.loadAll()

	case "esc":
		m.btnCursor = -1
		if m.addMode {
			m.addMode = false
			m.addForm = nil
		}
	}
	return m, nil
}

func (m CredentialsModel) activateButton(idx int) (CredentialsModel, tea.Cmd) {
	if idx < 0 || idx >= len(secButtons) {
		return m, nil
	}
	return m.handleKey(secButtons[idx].Key)
}

// ─── View ────────────────────────────────────────────────────────────────────

func (m CredentialsModel) View() string {
	cw := ui.ContentWidth(m.width)
	ch := ui.ContentHeight(m.height)
	innerW := cw - 4

	actionBar := ui.ButtonBar(secButtons, m.btnCursor)

	var banners string
	if m.err != "" {
		banners += "\n" + ui.ErrorBanner(innerW, m.err)
	}
	if m.success != "" {
		banners += "\n" + ui.SuccessBanner(innerW, m.success)
	}
	if m.delConfirm {
		banners += "\n" + lipgloss.NewStyle().Foreground(ui.ColorYellow).Bold(true).
			Render(fmt.Sprintf("  Delete '%s'? [y/N]", m.selectedName()))
	}

	var addFormStr string
	if m.addMode && m.addForm != nil {
		addFormStr = "\n" + m.addForm.View()
	}

	var tableContent string
	if m.addMode {
		tableContent = ""
	} else if m.loading {
		tableContent = "\n" + ui.DimStyle.Render(fmt.Sprintf("  %s  Loading...", ui.SpinnerFrame(m.tick)))
	} else {
		tableContent = "\n" + m.renderTable(innerW)
	}

	var navHint string
	if m.btnCursor >= 0 {
		navHint = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "←→", Label: "move"},
			ui.ButtonDef{Key: "enter", Label: "activate"},
			ui.ButtonDef{Key: "↑", Label: "back to list"},
		)
	} else if !m.addMode {
		navHint = "\n" + ui.HintBar(
			ui.ButtonDef{Key: "↑↓", Label: "navigate"},
			ui.ButtonDef{Key: "↓", Label: "focus buttons"},
		)
	}

	body := actionBar + banners + addFormStr + tableContent + navHint
	return ui.ContentPanel(cw, ch, "Secrets", body)
}

func (m CredentialsModel) renderTable(width int) string {
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width))

	if len(m.creds) == 0 {
		return ui.EmptyState("No credentials stored.\n\n  Press a to add one.")
	}
	headers := []string{"NAME", "PARTIAL", "LAST UPDATED"}
	colWidths := []int{24, 16, 20}
	headerLine := renderTableRow(headers, colWidths, true)
	var rows strings.Builder
	for i, c := range m.creds {
		cells := []string{c.Name, c.Partial, ui.Truncate(c.UpdatedAt, 19)}
		line := renderTableRow(cells, colWidths, false)
		cursor := "  "
		if i == m.cursor {
			cursor = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("▶ ")
			line = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render(line)
		}
		rows.WriteString(cursor + line + "\n")
	}
	count := ui.DimStyle.Render(fmt.Sprintf("\n  %d credential(s) stored.", len(m.creds)))
	return headerLine + "\n" + sep + "\n" + rows.String() + count
}

func (m CredentialsModel) buildAddForm() *huh.Form {
	return huh.NewForm(huh.NewGroup(
		huh.NewInput().Key("name").Title("Name (key)").
			Description("e.g. OPENAI_API_KEY").
			Value(&m.addName),
		huh.NewInput().Key("value").Title("Value").
			Description("Stored encrypted on the server").
			EchoMode(huh.EchoModePassword).
			Value(&m.addValue),
	)).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

// ─── Commands ────────────────────────────────────────────────────────────────

func (m CredentialsModel) loadAll() tea.Cmd {
	return func() tea.Msg {
		creds, err := m.client.ListCredentials()
		if err != nil {
			return SecretsLoadedMsg{Err: err}
		}
		return SecretsLoadedMsg{Creds: creds}
	}
}

func (m CredentialsModel) saveCredential() tea.Cmd {
	name := m.addName
	value := m.addValue
	if m.addForm != nil {
		name = m.addForm.GetString("name")
		value = m.addForm.GetString("value")
	}
	return func() tea.Msg {
		err := m.client.SetCredential(name, value)
		return SecretActionMsg{Action: "Credential stored", Err: err}
	}
}

func (m CredentialsModel) deleteSelected() tea.Cmd {
	name := m.selectedName()
	return func() tea.Msg {
		err := m.client.DeleteCredential(name)
		return SecretActionMsg{Action: "Credential deleted", Err: err}
	}
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func (m CredentialsModel) rowCount() int {
	return len(m.creds)
}

func (m CredentialsModel) selectedName() string {
	if m.cursor < len(m.creds) {
		return m.creds[m.cursor].Name
	}
	return ""
}

// FormActive returns true when the add form is open and being edited.
func (m CredentialsModel) FormActive() bool {
	return m.addMode && m.addForm != nil && m.addForm.State == huh.StateNormal
}

// FooterHints returns context-sensitive key hints.
func (m CredentialsModel) FooterHints() string {
	if m.addMode {
		return ui.KeyHint("tab", "next field") + "  " +
			ui.KeyHint("enter", "save") + "  " +
			ui.KeyHint("esc", "cancel")
	}
	if m.btnCursor >= 0 {
		return ui.KeyHint("←→", "move") + "  " +
			ui.KeyHint("enter", "activate") + "  " +
			ui.KeyHint("↑", "back")
	}
	return ui.KeyHint("↑↓", "navigate") + "  " +
		ui.KeyHint("a", "add") + "  " +
		ui.KeyHint("d", "delete") + "  " +
		ui.KeyHint("R", "refresh")
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m CredentialsModel) BtnCursor() int       { return m.btnCursor }
func (m CredentialsModel) AddMode() bool        { return m.addMode }
func (m CredentialsModel) DelConfirm() bool     { return m.delConfirm }
func (m CredentialsModel) Loading() bool        { return m.loading }
func (m CredentialsModel) Success() string      { return m.success }
func (m *CredentialsModel) SetSuccess(s string) { m.success = s }

func (m *CredentialsModel) InjectCred(name string) {
	m.creds = []client.CredentialMeta{{Name: name, Partial: "xx...xx"}}
}

// WantsEsc returns true when the add form is open.
func (m CredentialsModel) WantsEsc() bool {
	return m.addMode || m.delConfirm
}
