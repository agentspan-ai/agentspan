// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package progress

import (
	"fmt"
	"sync"
	"time"
)

var spinnerFrames = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

// Spinner renders an animated spinner to stdout while a task is in progress.
type Spinner struct {
	msg    string
	stop   chan struct{}
	done   chan struct{}
	mu     sync.Mutex
	active bool
}

// NewSpinner creates a spinner with the given message.
func NewSpinner(msg string) *Spinner {
	return &Spinner{msg: msg, stop: make(chan struct{}), done: make(chan struct{})}
}

// Start begins rendering the spinner in a background goroutine.
func (s *Spinner) Start() {
	s.mu.Lock()
	s.active = true
	s.mu.Unlock()

	go func() {
		defer close(s.done)
		for i := 0; ; i++ {
			select {
			case <-s.stop:
				fmt.Printf("\r\033[K")
				return
			default:
				fmt.Printf("\r%s %s", spinnerFrames[i%len(spinnerFrames)], s.msg)
				time.Sleep(80 * time.Millisecond)
			}
		}
	}()
}

// Stop halts the spinner and clears the line.
func (s *Spinner) Stop() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.active {
		s.active = false
		close(s.stop)
		<-s.done
	}
}
