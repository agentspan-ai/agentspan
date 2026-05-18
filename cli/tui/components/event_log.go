package components

import (
	"encoding/json"
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

// EventLine converts a raw SSE event into a styled terminal line.
// eventType is the "event:" field; data is the raw JSON "data:" payload.
func EventLine(eventType, data string) string {
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(data), &payload); err != nil {
		// Fallback: render raw
		return ui.DimStyle.Render(fmt.Sprintf("  [%s] %s", eventType, ui.Truncate(data, 150)))
	}

	// If type is embedded in the data (some servers send it this way)
	if t, ok := payload["type"].(string); ok && t != "" {
		eventType = t
	}

	switch eventType {
	case "thinking":
		msg := dataStr(payload, "message", "content")
		return lipgloss.NewStyle().Foreground(ui.ColorGrey).Faint(true).
			Render(fmt.Sprintf("  [thinking]  %s", ui.Truncate(msg, 120)))

	case "tool_call":
		name := dataStr(payload, "toolName", "tool_name", "name")
		input := dataStr(payload, "input", "arguments")
		return lipgloss.NewStyle().Foreground(ui.ColorBlue).
			Render(fmt.Sprintf("  [tool]      %s(%s)", name, ui.Truncate(input, 100)))

	case "tool_result":
		name := dataStr(payload, "toolName", "tool_name", "name")
		result := dataStr(payload, "result", "output", "content")
		return lipgloss.NewStyle().Foreground(ui.ColorLimeGreen).
			Render(fmt.Sprintf("  [result]    %s → %s", name, ui.Truncate(result, 200)))

	case "handoff":
		agent := dataStr(payload, "agentName", "agent_name", "agent")
		return lipgloss.NewStyle().Foreground(ui.ColorYellow).
			Render(fmt.Sprintf("  [handoff]   → %s", agent))

	case "message":
		content := dataStr(payload, "content", "message", "output")
		return lipgloss.NewStyle().Foreground(ui.ColorWhite).Render(content)

	case "waiting":
		execID := dataStr(payload, "executionId", "execution_id")
		msg := fmt.Sprintf("  [waiting]   Human input required")
		if execID != "" {
			msg += fmt.Sprintf(" (execution: %s)", TruncateID(execID))
		}
		return lipgloss.NewStyle().Foreground(ui.ColorYellow).Bold(true).Render(msg)

	case "guardrail_pass":
		name := dataStr(payload, "guardrailName", "name")
		return lipgloss.NewStyle().Foreground(ui.ColorGreen).
			Render(fmt.Sprintf("  [guardrail] PASS %s", name))

	case "guardrail_fail":
		name := dataStr(payload, "guardrailName", "name")
		reason := dataStr(payload, "reason")
		line := fmt.Sprintf("  [guardrail] FAIL %s", name)
		if reason != "" {
			line += ": " + reason
		}
		return lipgloss.NewStyle().Foreground(ui.ColorRed).Render(line)

	case "error":
		msg := dataStr(payload, "message", "error")
		return lipgloss.NewStyle().Foreground(ui.ColorRed).Bold(true).
			Render(fmt.Sprintf("  [error]     %s", msg))

	case "done":
		output := dataStr(payload, "output", "result", "content")
		sep := lipgloss.NewStyle().Foreground(ui.ColorDarkGreen).Render(strings.Repeat("─", 60))
		out := lipgloss.NewStyle().Foreground(ui.ColorWhite).Bold(true).Render(output)
		return "\n" + sep + "\n" + out

	default:
		if data == "" || data == "{}" {
			return ""
		}
		raw := ui.Truncate(data, 150)
		return ui.DimStyle.Render(fmt.Sprintf("  [%s] %s", eventType, raw))
	}
}

// dataStr extracts a string from a map trying multiple key names.
func dataStr(m map[string]interface{}, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			switch s := v.(type) {
			case string:
				return s
			default:
				b, _ := json.Marshal(v)
				return string(b)
			}
		}
	}
	return ""
}
