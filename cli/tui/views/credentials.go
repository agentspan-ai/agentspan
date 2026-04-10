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

type CredentialsLoadedMsg struct {
	Creds    []client.CredentialMeta
	Bindings []client.BindingMeta
	Err      error
}

type CredentialActionMsg struct {
	Action string
	Err    error
}

// ─── Tab ─────────────────────────────────────────────────────────────────────

type CredTab int

const (
	CredTabCreds CredTab = iota
	CredTabBindings
)

// ─── Buttons ─────────────────────────────────────────────────────────────────

var credButtons = []ui.ButtonDef{
	{Key: "tab", Label: "switch tab"},
	{Key: "a", Label: "add"},
	{Key: "d", Label: "delete", Danger: true},
	{Key: "R", Label: "refresh"},
}

// ─── Model ───────────────────────────────────────────────────────────────────

type CredentialsModel struct {
	client    *client.Client
	width     int
	height    int
	tab       CredTab
	creds     []client.CredentialMeta
	bindings  []client.BindingMeta
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

	case CredentialsLoadedMsg:
		m.loading = false
		if msg.Err != nil {
			m.err = msg.Err.Error()
		} else {
			m.creds = msg.Creds
			m.bindings = msg.Bindings
			m.cursor = 0
		}

	case CredentialActionMsg:
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
			form, cmd := m.addForm.Update(msg)
			if f, ok := form.(*huh.Form); ok {
				m.addForm = f
				if m.addForm.State == huh.StateCompleted {
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

	// Non-key form updates (resize etc.)
	if m.addMode && m.addForm != nil {
		form, cmd := m.addForm.Update(msg)
		if f, ok := form.(*huh.Form); ok {
			m.addForm = f
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
		if m.btnCursor >= 0 && m.btnCursor < len(credButtons)-1 {
			m.btnCursor++
		}

	case "enter", " ", "space":
		if m.btnCursor >= 0 {
			return m.activateButton(m.btnCursor)
		}

	case "tab":
		// Tab always switches tabs regardless of button focus
		if m.tab == CredTabCreds {
			m.tab = CredTabBindings
		} else {
			m.tab = CredTabCreds
		}
		m.cursor = 0
		m.btnCursor = -1

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
	if idx < 0 || idx >= len(credButtons) {
		return m, nil
	}
	return m.handleKey(credButtons[idx].Key)
}

// ─── View ────────────────────────────────────────────────────────────────────

func (m CredentialsModel) View() string {
	cw := ui.ContentWidth(m.width)
	ch := ui.ContentHeight(m.height)
	innerW := cw - 4

	// Tab indicator (not a button bar — just styled labels)
	tabActive := lipgloss.NewStyle().Bold(true).Foreground(ui.ColorLimeGreen).
		Border(lipgloss.RoundedBorder()).BorderForeground(ui.ColorLimeGreen).Padding(0, 1)
	tabInactive := lipgloss.NewStyle().Foreground(ui.ColorGrey).
		Border(lipgloss.RoundedBorder()).BorderForeground(ui.ColorGrey).Padding(0, 1)

	var credTabStr, bindTabStr string
	if m.tab == CredTabCreds {
		credTabStr = tabActive.Render("Credentials")
		bindTabStr = tabInactive.Render("Bindings")
	} else {
		credTabStr = tabInactive.Render("Credentials")
		bindTabStr = tabActive.Render("Bindings")
	}
	tabBar := credTabStr + " " + bindTabStr

	// Action button bar
	actionBar := ui.ButtonBar(credButtons, m.btnCursor)

	// Banners
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

	// Add form
	var addFormStr string
	if m.addMode && m.addForm != nil {
		addFormStr = "\n" + m.addForm.View()
	}

	// Table
	var tableContent string
	if m.addMode {
		tableContent = ""
	} else if m.loading {
		tableContent = "\n" + ui.DimStyle.Render(fmt.Sprintf("  %s  Loading...", ui.SpinnerFrame(m.tick)))
	} else {
		tableContent = "\n" + m.renderTable(innerW)
	}

	// Nav hint
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

	body := tabBar + "  " + actionBar + banners + addFormStr + tableContent + navHint
	return ui.ContentPanel(cw, ch, "Credentials", body)
}

func (m CredentialsModel) renderTable(width int) string {
	sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", width))

	if m.tab == CredTabCreds {
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

	// Bindings tab
	if len(m.bindings) == 0 {
		return ui.EmptyState("No bindings configured.\n\n  Press a to add one.")
	}
	headers := []string{"LOGICAL KEY", "STORE NAME"}
	colWidths := []int{28, 28}
	headerLine := renderTableRow(headers, colWidths, true)
	var rows strings.Builder
	for i, b := range m.bindings {
		cells := []string{b.LogicalKey, b.StoreName}
		line := renderTableRow(cells, colWidths, false)
		cursor := "  "
		if i == m.cursor {
			cursor = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render("▶ ")
			line = lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).Render(line)
		}
		rows.WriteString(cursor + line + "\n")
	}
	count := ui.DimStyle.Render(fmt.Sprintf("\n  %d binding(s) configured.", len(m.bindings)))
	return headerLine + "\n" + sep + "\n" + rows.String() + count
}

func (m CredentialsModel) buildAddForm() *huh.Form {
	title := "Add Credential"
	desc := "Stored encrypted on the server"
	if m.tab == CredTabBindings {
		title = "Add Binding"
		desc = "Map a logical key to a store name"
	}

	nameLabel := "Name (key)"
	valueLabel := "Value"
	if m.tab == CredTabBindings {
		nameLabel = "Logical Key"
		valueLabel = "Store Name"
	}

	_ = title
	_ = desc

	if m.tab == CredTabCreds {
		return huh.NewForm(huh.NewGroup(
			huh.NewInput().Title(nameLabel).
				Description("e.g. OPENAI_API_KEY").
				Value(&m.addName),
			huh.NewInput().Title(valueLabel).
				Description("Stored encrypted on the server").
				EchoMode(huh.EchoModePassword).
				Value(&m.addValue),
		)).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
	}
	return huh.NewForm(huh.NewGroup(
		huh.NewInput().Title(nameLabel).
			Description("e.g. OPENAI_API_KEY").
			Value(&m.addName),
		huh.NewInput().Title(valueLabel).
			Description("The storage key name").
			Value(&m.addValue),
	)).WithTheme(huh.ThemeFunc(agentspanHuhTheme))
}

// ─── Commands ────────────────────────────────────────────────────────────────

func (m CredentialsModel) loadAll() tea.Cmd {
	return func() tea.Msg {
		creds, err := m.client.ListCredentials()
		if err != nil {
			return CredentialsLoadedMsg{Err: err}
		}
		bindings, err := m.client.ListBindings()
		if err != nil {
			return CredentialsLoadedMsg{Creds: creds, Err: err}
		}
		return CredentialsLoadedMsg{Creds: creds, Bindings: bindings}
	}
}

func (m CredentialsModel) saveCredential() tea.Cmd {
	name := m.addName
	value := m.addValue
	tab := m.tab
	return func() tea.Msg {
		if tab == CredTabCreds {
			err := m.client.SetCredential(name, value)
			return CredentialActionMsg{Action: "Credential stored", Err: err}
		}
		err := m.client.SetBinding(name, value)
		return CredentialActionMsg{Action: "Binding created", Err: err}
	}
}

func (m CredentialsModel) deleteSelected() tea.Cmd {
	name := m.selectedName()
	tab := m.tab
	return func() tea.Msg {
		if tab == CredTabCreds {
			err := m.client.DeleteCredential(name)
			return CredentialActionMsg{Action: "Credential deleted", Err: err}
		}
		return CredentialActionMsg{Err: fmt.Errorf("binding deletion not supported via API")}
	}
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func (m CredentialsModel) rowCount() int {
	if m.tab == CredTabCreds {
		return len(m.creds)
	}
	return len(m.bindings)
}

func (m CredentialsModel) selectedName() string {
	if m.tab == CredTabCreds && m.cursor < len(m.creds) {
		return m.creds[m.cursor].Name
	}
	if m.tab == CredTabBindings && m.cursor < len(m.bindings) {
		return m.bindings[m.cursor].LogicalKey
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
		ui.KeyHint("tab", "switch tab") + "  " +
		ui.KeyHint("a", "add") + "  " +
		ui.KeyHint("d", "delete") + "  " +
		ui.KeyHint("R", "refresh")
}

// ─── Test accessors ───────────────────────────────────────────────────────────

func (m CredentialsModel) Tab() CredTab       { return m.tab }
func (m CredentialsModel) BtnCursor() int     { return m.btnCursor }
func (m CredentialsModel) AddMode() bool      { return m.addMode }
func (m CredentialsModel) DelConfirm() bool   { return m.delConfirm }
func (m CredentialsModel) Loading() bool      { return m.loading }
func (m CredentialsModel) Success() string    { return m.success }
func (m *CredentialsModel) SetSuccess(s string) { m.success = s }

func (m *CredentialsModel) InjectCred(name string) {
	m.creds = []client.CredentialMeta{{Name: name, Partial: "xx...xx"}}
}

// WantsEsc returns true when the add form is open.
func (m CredentialsModel) WantsEsc() bool {
	return m.addMode || m.delConfirm
}
