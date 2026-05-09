// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

//go:build windows

package cmd

import (
	"os"
	"syscall"
)

func sysProcAttr() *syscall.SysProcAttr {
	// CREATE_NEW_PROCESS_GROUP prevents Ctrl+C / console-close events from the
	// parent terminal propagating to the server child process, so the server
	// stays alive after the CLI exits or the launch terminal is closed.
	const createNewProcessGroup = 0x00000200
	return &syscall.SysProcAttr{
		CreationFlags: createNewProcessGroup,
	}
}

func killProcess(process *os.Process) error {
	return process.Kill()
}

func processRunning(pid int) bool {
	// Signal(0) is not supported on Windows — it returns an error for both
	// running and dead processes, making it useless as a liveness check.
	// Use GetExitCodeProcess instead: STILL_ACTIVE (259) means the process
	// is still running; any other exit code means it has terminated.
	const processQueryLimitedInformation = 0x1000
	const stillActive = 259
	handle, err := syscall.OpenProcess(processQueryLimitedInformation, false, uint32(pid))
	if err != nil {
		return false
	}
	defer syscall.CloseHandle(handle)
	var exitCode uint32
	if err := syscall.GetExitCodeProcess(handle, &exitCode); err != nil {
		return false
	}
	return exitCode == stillActive
}

func getFreeDiskMB(path string) int64 {
	// Not easily available on Windows without unsafe; skip check
	return -1
}
