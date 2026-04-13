package ui

import (
	"reflect"
	"testing"

	"charm.land/lipgloss/v2"
)

func TestSetThemeUsesTerminalBackground(t *testing.T) {
	prevDark := IsDarkBackground
	prevBg := ColorBg
	prevHasBg := hasBg
	t.Cleanup(func() {
		IsDarkBackground = prevDark
		ColorBg = prevBg
		hasBg = prevHasBg
		rebuildStyles()
	})

	SetTheme(true)
	if hasBg {
		t.Fatal("dark theme should use the terminal background instead of painting a fixed one")
	}
	if !reflect.DeepEqual(ColorBg, lipgloss.NoColor{}) {
		t.Fatalf("unexpected dark background color: %#v", ColorBg)
	}

	SetTheme(false)
	if hasBg {
		t.Fatal("light theme should use the terminal background instead of painting a fixed one")
	}
	if !reflect.DeepEqual(ColorBg, lipgloss.NoColor{}) {
		t.Fatalf("unexpected light background color: %#v", ColorBg)
	}
}

func TestSetThemeUsesTerminalNativeANSIAccents(t *testing.T) {
	prevDark := IsDarkBackground
	prevBg := ColorBg
	prevHasBg := hasBg
	t.Cleanup(func() {
		IsDarkBackground = prevDark
		ColorBg = prevBg
		hasBg = prevHasBg
		rebuildStyles()
	})

	SetTheme(false)
	if !reflect.DeepEqual(ColorLimeGreen, lipgloss.Green) {
		t.Fatalf("unexpected light accent color: %#v", ColorLimeGreen)
	}
	if !reflect.DeepEqual(ColorRed, lipgloss.Red) {
		t.Fatalf("unexpected light error color: %#v", ColorRed)
	}
	if !reflect.DeepEqual(ColorWhite, lipgloss.NoColor{}) {
		t.Fatalf("light theme should inherit terminal foreground: %#v", ColorWhite)
	}

	SetTheme(true)
	if !reflect.DeepEqual(ColorLimeGreen, lipgloss.BrightGreen) {
		t.Fatalf("unexpected dark accent color: %#v", ColorLimeGreen)
	}
	if !reflect.DeepEqual(ColorRed, lipgloss.BrightRed) {
		t.Fatalf("unexpected dark error color: %#v", ColorRed)
	}
	if !reflect.DeepEqual(ColorWhite, lipgloss.NoColor{}) {
		t.Fatalf("dark theme should inherit terminal foreground: %#v", ColorWhite)
	}
}
