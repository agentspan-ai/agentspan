package tui

import (
	"testing"

	tea "charm.land/bubbletea/v2"
)

func TestNavCursorMovesDown(t *testing.T) {
	n := NewNav()
	n, _ = n.Update(tea.KeyPressMsg(tea.Key{Text: "j"}))
	if n.cursor != 1 {
		t.Errorf("expected cursor=1 after j, got %d", n.cursor)
	}
}

func TestNavCursorMovesUp(t *testing.T) {
	n := NewNav()
	n.cursor = 3
	n, _ = n.Update(tea.KeyPressMsg(tea.Key{Text: "k"}))
	if n.cursor != 2 {
		t.Errorf("expected cursor=2 after k, got %d", n.cursor)
	}
}

func TestNavWrapAround(t *testing.T) {
	n := NewNav()
	n, _ = n.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyUp}))
	if n.cursor != len(navItems)-1 {
		t.Errorf("expected wrap to %d, got %d", len(navItems)-1, n.cursor)
	}
}

func TestNavWrapDown(t *testing.T) {
	n := NewNav()
	n.cursor = len(navItems) - 1
	n, _ = n.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyDown}))
	if n.cursor != 0 {
		t.Errorf("expected wrap to 0, got %d", n.cursor)
	}
}

func TestNavEnterEmitsSelectMsg(t *testing.T) {
	n := NewNav()
	n.cursor = 1 // Agents (index 1 in new nav)
	_, cmd := n.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyEnter}))
	if cmd == nil {
		t.Fatal("expected a cmd after enter, got nil")
	}
	msg := cmd()
	sel, ok := msg.(NavSelectMsg)
	if !ok {
		t.Fatalf("expected NavSelectMsg, got %T", msg)
	}
	if sel.View != ViewAgents {
		t.Errorf("expected ViewAgents, got %d", sel.View)
	}
}

func TestNavSetActive(t *testing.T) {
	n := NewNav()
	n.SetActive(ViewServer)
	if n.active != ViewServer {
		t.Errorf("expected active=ViewServer, got %d", n.active)
	}
	// ViewServer is now index 3 in the new 8-item nav
	expectedIdx := -1
	for i, item := range navItems {
		if item.ID == ViewServer {
			expectedIdx = i
			break
		}
	}
	if n.cursor != expectedIdx {
		t.Errorf("expected cursor=%d for ViewServer, got %d", expectedIdx, n.cursor)
	}
}

func TestNavTabEmitsFocusContent(t *testing.T) {
	n := NewNav()
	n.cursor = 1 // Agents
	_, cmd := n.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyTab}))
	if cmd == nil {
		t.Fatal("expected a cmd after tab, got nil")
	}
	msg := cmd()
	if _, ok := msg.(FocusContent); !ok {
		t.Fatalf("expected FocusContent, got %T", msg)
	}
}
