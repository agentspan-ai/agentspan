package views

import (
	"reflect"
	"testing"

	"charm.land/huh/v2"
	"github.com/agentspan-ai/agentspan/cli/tui/ui"
)

func TestAgentspanHuhThemeUsesGlobalThemeState(t *testing.T) {
	prev := ui.IsDarkBackground
	t.Cleanup(func() { ui.SetTheme(prev) })

	darkReference := huh.ThemeCharm(true)
	lightReference := huh.ThemeCharm(false)

	ui.SetTheme(true)
	gotDark := agentspanHuhTheme(false)
	if !reflect.DeepEqual(
		gotDark.Focused.TextInput.Placeholder.GetForeground(),
		darkReference.Focused.TextInput.Placeholder.GetForeground(),
	) {
		t.Fatal("expected Huh form theme to follow the app's dark theme")
	}
	if reflect.DeepEqual(
		gotDark.Focused.TextInput.Placeholder.GetForeground(),
		lightReference.Focused.TextInput.Placeholder.GetForeground(),
	) {
		t.Fatal("dark app theme should not render with Huh's light palette")
	}

	ui.SetTheme(false)
	gotLight := agentspanHuhTheme(true)
	if !reflect.DeepEqual(
		gotLight.Focused.TextInput.Placeholder.GetForeground(),
		lightReference.Focused.TextInput.Placeholder.GetForeground(),
	) {
		t.Fatal("expected Huh form theme to follow the app's light theme")
	}
}
