package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"syscall"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Log in to the AgentSpan server and store an auth token",
	Long: `Prompts for username and password, authenticates against the server,
and stores the returned JWT in ~/.agentspan/config.json.

On localhost with auth disabled, this command is not required — the server
accepts all requests as anonymous admin automatically.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()

		if cfg.IsLocalhost() && cfg.APIKey == "" {
			color.Yellow("Server is localhost — auth is optional.")
			fmt.Println("Proceeding without login (anonymous admin mode).")
			return nil
		}

		fmt.Print("Username: ")
		reader := bufio.NewReader(os.Stdin)
		username, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("read username: %w", err)
		}
		username = strings.TrimSpace(username)

		fmt.Print("Password: ")
		passwordBytes, err := term.ReadPassword(int(syscall.Stdin))
		fmt.Println()
		if err != nil {
			return fmt.Errorf("read password: %w", err)
		}
		password := string(passwordBytes)

		if err := doLogin(cfg, username, password); err != nil {
			return err
		}

		color.Green("Logged in successfully.")
		fmt.Printf("Token stored in %s/config.json\n", config.ConfigDir())
		return nil
	},
}

var logoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Remove the stored auth token",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := config.Load()
		if cfg.APIKey == "" {
			color.Yellow("Not currently logged in.")
			return nil
		}
		cfg.APIKey = ""
		if err := config.Save(cfg); err != nil {
			return fmt.Errorf("save config: %w", err)
		}
		color.Green("Logged out.")
		return nil
	},
}

// doLogin calls the server auth endpoint and persists the returned token.
// Extracted so tests can call it directly without terminal I/O.
func doLogin(cfg *config.Config, username, password string) error {
	c := client.New(cfg)
	resp, err := c.Login(username, password)
	if err != nil {
		return fmt.Errorf("login failed: %w", err)
	}
	if resp.Token == "" {
		return fmt.Errorf("server returned empty token")
	}
	cfg.APIKey = resp.Token
	if err := config.Save(cfg); err != nil {
		return fmt.Errorf("save config: %w", err)
	}
	return nil
}

func init() {
	rootCmd.AddCommand(loginCmd)
	rootCmd.AddCommand(logoutCmd)
}
