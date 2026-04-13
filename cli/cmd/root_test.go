package cmd

import (
	"errors"
	"strings"
	"testing"
)

func TestTUICmdRequiresInteractiveTerminal(t *testing.T) {
	prevIsTerminal := isTerminal
	prevStartTUI := startTUI
	t.Cleanup(func() {
		isTerminal = prevIsTerminal
		startTUI = prevStartTUI
	})

	isTerminal = func(int) bool { return false }

	started := false
	startTUI = func(string) error {
		started = true
		return nil
	}

	err := tuiCmd.RunE(tuiCmd, nil)
	if err == nil {
		t.Fatal("expected tui command to reject non-interactive execution")
	}
	if !strings.Contains(err.Error(), "interactive terminal") {
		t.Fatalf("unexpected error: %v", err)
	}
	if started {
		t.Fatal("tui launcher should not be invoked when no TTY is available")
	}
}

func TestTUICmdLaunchesWhenInteractiveTerminalIsAvailable(t *testing.T) {
	prevIsTerminal := isTerminal
	prevStartTUI := startTUI
	t.Cleanup(func() {
		isTerminal = prevIsTerminal
		startTUI = prevStartTUI
	})

	isTerminal = func(int) bool { return true }

	sentinel := errors.New("launch failed")
	started := false
	startTUI = func(version string) error {
		started = true
		if version != Version {
			t.Fatalf("expected version %q, got %q", Version, version)
		}
		return sentinel
	}

	err := tuiCmd.RunE(tuiCmd, nil)
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected launcher error %v, got %v", sentinel, err)
	}
	if !started {
		t.Fatal("expected tui launcher to run when a TTY is available")
	}
}
