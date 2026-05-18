package views

import (
	"strings"

	tea "charm.land/bubbletea/v2"
	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// DeployModel is a placeholder for the deploy view.
// Full implementation: discover agents from project, deploy with confirmation.
type DeployModel struct {
	client *client.Client
	width  int
	height int
}

func NewDeploy(c *client.Client) DeployModel {
	return DeployModel{client: c}
}

func (m DeployModel) Init() tea.Cmd { return nil }

func (m DeployModel) Update(msg tea.Msg) (DeployModel, tea.Cmd) {
	if msg, ok := msg.(tea.WindowSizeMsg); ok {
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}

func (m DeployModel) View() string {
	cw := ui.ContentWidth(m.width)
	body := ui.EmptyState("Deploy management coming soon.\n\n" +
		"Use 'agentspan deploy' to deploy agents from a Python or TypeScript project.\n\n" +
		"Example:\n  agentspan deploy --language python")
	return ui.ContentPanel(cw, ui.ContentHeight(m.height), "Deploy", body)
}

func (m DeployModel) FooterHints() string {
	return strings.Join([]string{
		ui.KeyHint("esc", "back"),
		ui.KeyHint("q", "quit"),
	}, "  ")
}
