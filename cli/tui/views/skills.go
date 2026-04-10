package views

import (
	"strings"

	tea "charm.land/bubbletea/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// SkillsModel is a placeholder for the skills view.
// Full implementation: discover skill directories, run/load skills.
type SkillsModel struct {
	client *client.Client
	width  int
	height int
}

func NewSkills(c *client.Client) SkillsModel {
	return SkillsModel{client: c}
}

func (m SkillsModel) Init() tea.Cmd { return nil }

func (m SkillsModel) Update(msg tea.Msg) (SkillsModel, tea.Cmd) {
	if msg, ok := msg.(tea.WindowSizeMsg); ok {
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}

func (m SkillsModel) View() string {
	cw := ui.ContentWidth(m.width)
	body := ui.EmptyState("Skills management coming soon.\n\n" +
		"Use 'agentspan skill run <path> <prompt>' to run skills from the CLI.")
	return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Skills", body)
}

func (m SkillsModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("esc", "back"),
		ui.KeyHint("q", "quit"),
	}, "  ")
}
