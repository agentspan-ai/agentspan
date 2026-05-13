// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/internal/progress"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

const cliS3Bucket = "https://agentspan.s3.us-east-2.amazonaws.com"

var updateCmd = &cobra.Command{
	Use:   "update",
	Short: "Update the CLI and server JAR to the latest versions",
	RunE:  runUpdate,
}

func runUpdate(cmd *cobra.Command, args []string) error {
	bold := color.New(color.Bold)
	green := color.New(color.FgGreen)
	yellow := color.New(color.FgYellow)

	anyUpdated := false

	// ── 1. CLI binary ────────────────────────────────────────────────────────
	bold.Println("Checking CLI version...")

	latestCLI, err := fetchLatestCLIVersion()
	if err != nil {
		yellow.Printf("  Warning: could not check latest CLI version (%v)\n", err)
		latestCLI = ""
	}

	currentCLI := Version // injected via -ldflags at build time, "dev" otherwise

	switch {
	case currentCLI == "dev":
		yellow.Println("  Development build — version comparison skipped.")
		if confirmYN("Download and install latest CLI binary anyway?") {
			if err := downloadCLIBinary(); err != nil {
				return fmt.Errorf("CLI update failed: %w", err)
			}
			green.Println("  CLI updated ✓")
			anyUpdated = true
		} else {
			fmt.Println("  Skipped.")
		}

	case latestCLI == "":
		// Could not fetch version — ask user
		yellow.Println("  Could not determine latest version.")
		if confirmYN("Download and install latest CLI binary anyway?") {
			if err := downloadCLIBinary(); err != nil {
				return fmt.Errorf("CLI update failed: %w", err)
			}
			green.Println("  CLI updated ✓")
			anyUpdated = true
		} else {
			fmt.Println("  Skipped.")
		}

	case currentCLI == latestCLI:
		green.Printf("  Already up to date (%s) ✓\n", currentCLI)

	default:
		// New version available
		fmt.Printf("  Current:  %s\n", currentCLI)
		fmt.Printf("  Latest:   %s\n", latestCLI)
		fmt.Println()
		if confirmYN(fmt.Sprintf("Update CLI to %s?", latestCLI)) {
			if err := downloadCLIBinary(); err != nil {
				return fmt.Errorf("CLI update failed: %w", err)
			}
			green.Printf("  CLI updated to %s ✓\n", latestCLI)
			anyUpdated = true
		} else {
			fmt.Println("  Skipped.")
		}
	}

	fmt.Println()

	// ── 2. Server JAR ────────────────────────────────────────────────────────
	bold.Println("Checking server JAR...")

	home, _ := os.UserHomeDir()
	jarPath := filepath.Join(home, ".agentspan", "server", "agentspan-runtime.jar")

	remoteSize, remoteDate, err := fetchRemoteJARInfo()
	if err != nil {
		yellow.Printf("  Warning: could not check remote JAR info (%v)\n", err)
		fmt.Println()
	} else {
		localInfo, localErr := os.Stat(jarPath)

		if localErr != nil {
			// No cached JAR at all
			fmt.Printf("  Remote:  %.0f MB  (updated %s)\n",
				float64(remoteSize)/1024/1024, formatDate(remoteDate))
			fmt.Printf("  Local:   not cached\n\n")
			if confirmYN("Download server JAR?") {
				if err := downloadServerJAR(jarPath); err != nil {
					return fmt.Errorf("server JAR download failed: %w", err)
				}
				green.Println("  Server JAR downloaded ✓")
				anyUpdated = true
			} else {
				fmt.Println("  Skipped.")
			}
		} else {
			localSize := localInfo.Size()
			localDate := localInfo.ModTime()

			fmt.Printf("  Local:   %.0f MB  (downloaded %s)\n",
				float64(localSize)/1024/1024, formatDate(localDate))
			fmt.Printf("  Remote:  %.0f MB  (updated %s)\n",
				float64(remoteSize)/1024/1024, formatDate(remoteDate))

			// Outdated if remote is newer by >1 min or size differs by >100 KB
			remoteNewer := remoteDate.After(localDate.Add(time.Minute))
			sizeDiff := remoteSize - localSize
			if sizeDiff < 0 {
				sizeDiff = -sizeDiff
			}
			remoteDifferent := sizeDiff > 100*1024

			if !remoteNewer && !remoteDifferent {
				green.Println("  Server JAR is up to date ✓")
			} else {
				fmt.Println()
				if confirmYN("Download updated server JAR?") {
					if err := downloadServerJAR(jarPath); err != nil {
						return fmt.Errorf("server JAR update failed: %w", err)
					}
					green.Println("  Server JAR updated ✓")
					anyUpdated = true
				} else {
					fmt.Println("  Skipped.")
				}
			}
		}
		fmt.Println()
	}

	// ── Summary ───────────────────────────────────────────────────────────────
	if anyUpdated {
		green.Println("Update complete!")
		// Remind user to restart server if it was running
		pidFile := filepath.Join(home, ".agentspan", "server", "server.pid")
		if _, pidErr := os.Stat(pidFile); pidErr == nil {
			yellow.Println("Note: restart the server to use the new JAR:")
			yellow.Println("  agentspan server stop && agentspan server start")
		}
	} else {
		fmt.Println("Everything is up to date.")
	}

	return nil
}

// fetchLatestCLIVersion fetches the latest CLI version string from S3.
// Returns the trimmed version string, e.g. "0.1.3".
func fetchLatestCLIVersion() (string, error) {
	url := fmt.Sprintf("%s/cli/latest/version.txt", cliS3Bucket)
	c := &http.Client{Timeout: 10 * time.Second}
	resp, err := c.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(body)), nil
}

// fetchRemoteJARInfo does a HEAD request on the latest server JAR and returns
// its Content-Length (bytes) and Last-Modified time.
func fetchRemoteJARInfo() (size int64, modified time.Time, err error) {
	url := fmt.Sprintf("%s/agentspan-server-latest.jar", s3Bucket)
	c := &http.Client{Timeout: 10 * time.Second}
	resp, err := c.Head(url)
	if err != nil {
		return 0, time.Time{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 0, time.Time{}, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	size = resp.ContentLength
	if lm := resp.Header.Get("Last-Modified"); lm != "" {
		modified, _ = http.ParseTime(lm)
	}
	return size, modified, nil
}

// downloadCLIBinary downloads the latest CLI binary and atomically replaces
// the currently running executable.
func downloadCLIBinary() error {
	goos := runtime.GOOS
	goarch := runtime.GOARCH

	binaryName := fmt.Sprintf("agentspan_%s_%s", goos, goarch)
	if goos == "windows" {
		binaryName += ".exe"
	}

	downloadURL := fmt.Sprintf("%s/cli/latest/%s", cliS3Bucket, binaryName)
	fmt.Printf("  Downloading %s\n", downloadURL)

	httpClient := &http.Client{Timeout: 5 * time.Minute}
	resp, err := httpClient.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("download failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed: HTTP %d", resp.StatusCode)
	}

	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("find executable path: %w", err)
	}

	tmpPath := execPath + ".new"
	f, err := os.Create(tmpPath)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	pr, bar := progress.NewReader(resp.Body, resp.ContentLength, "  Downloading")
	_, err = io.Copy(f, pr)
	f.Close()
	bar.Finish()
	if err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("write binary: %w", err)
	}

	if err := os.Chmod(tmpPath, 0o755); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("chmod: %w", err)
	}

	if err := os.Rename(tmpPath, execPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("replace binary: %w", err)
	}

	return nil
}

// downloadServerJAR downloads the latest server JAR to jarPath, using a
// temporary file + rename for atomicity.
func downloadServerJAR(jarPath string) error {
	if err := os.MkdirAll(filepath.Dir(jarPath), 0o755); err != nil {
		return err
	}

	url := fmt.Sprintf("%s/agentspan-server-latest.jar", s3Bucket)

	httpClient := &http.Client{Timeout: 10 * time.Minute}
	resp, err := httpClient.Get(url)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed: HTTP %d", resp.StatusCode)
	}

	tmpPath := jarPath + ".tmp"
	f, err := os.Create(tmpPath)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}

	pr, bar := progress.NewReader(resp.Body, resp.ContentLength, "  Downloading")
	_, err = io.Copy(f, pr)
	f.Close()
	bar.Finish()
	if err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("write JAR: %w", err)
	}

	if err := os.Rename(tmpPath, jarPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("rename JAR: %w", err)
	}

	return nil
}

// confirmYN prints a [y/N] prompt and returns true if the user answers yes.
func confirmYN(question string) bool {
	fmt.Printf("  %s [y/N]: ", question)
	scanner := bufio.NewScanner(os.Stdin)
	if scanner.Scan() {
		answer := strings.TrimSpace(strings.ToLower(scanner.Text()))
		return answer == "y" || answer == "yes"
	}
	return false
}

// formatDate formats a time.Time as a short human-readable date.
func formatDate(t time.Time) string {
	if t.IsZero() {
		return "unknown"
	}
	return t.Local().Format("Mon Jan  2 2006")
}

func init() {
	rootCmd.AddCommand(updateCmd)
}
