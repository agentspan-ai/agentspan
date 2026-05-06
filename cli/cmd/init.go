// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	_ "embed"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

//go:embed templates/agentspan.yaml
var agentspanYAMLTemplate string

var (
	initForce   bool
	agentNameRe = regexp.MustCompile(`^[a-z][a-z0-9-]*$`)
)

var initCmd = &cobra.Command{
	Use:   "init <name>",
	Short: "Create a starter agentspan.yaml for a new agent project",
	Long: `Write agentspan.yaml into ./<name>/ (or the current directory when passed '.').

Pass '.' to scaffold into the current directory; uses the directory basename as the agent name.`,
	Args: cobra.ExactArgs(1),
	RunE: runInitCmd,
}

func init() {
	initCmd.Flags().BoolVar(&initForce, "force", false, "Overwrite if target directory already exists")
	agentCmd.AddCommand(initCmd)
}

func runInitCmd(_ *cobra.Command, args []string) error {
	arg := args[0]

	var projectDir, agentName string
	if arg == "." {
		abs, err := filepath.Abs(".")
		if err != nil {
			return err
		}
		projectDir = abs
		agentName = filepath.Base(abs)
	} else {
		agentName = arg
		projectDir = filepath.Join(".", agentName)
	}

	if !agentNameRe.MatchString(agentName) {
		return fmt.Errorf("name %q is invalid — must match ^[a-z][a-z0-9-]*$ (lowercase, digits, hyphens; must start with a letter)", agentName)
	}

	if arg != "." {
		if info, err := os.Stat(projectDir); err == nil && info.IsDir() {
			if !initForce {
				return fmt.Errorf("directory %q already exists — pass --force to overwrite", projectDir)
			}
		} else if err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("stat %s: %w", projectDir, err)
		}
		if err := os.MkdirAll(projectDir, 0o755); err != nil {
			return fmt.Errorf("create directory: %w", err)
		}
	}

	content := strings.ReplaceAll(agentspanYAMLTemplate, "{{name}}", agentName)
	path := filepath.Join(projectDir, "agentspan.yaml")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return fmt.Errorf("write agentspan.yaml: %w", err)
	}

	color.New(color.FgGreen).Printf("  created  %s\n", filepath.Join(arg, "agentspan.yaml"))
	fmt.Println()
	if arg == "." {
		fmt.Println("Next:")
		fmt.Println("  agentspan agent build")
	} else {
		fmt.Printf("Next:\n  cd %s\n  agentspan agent build\n", agentName)
	}
	return nil
}
