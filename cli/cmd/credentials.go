package cmd

import (
	"bytes"
	"fmt"
	"text/tabwriter"

	"github.com/agentspan-ai/agentspan/cli/client"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var secretsCmd = &cobra.Command{
	// User-facing command name stays `credentials` — the rename to "secrets"
	// is a server/internal-only change. `secrets`/`secret` are kept as
	// aliases so anything that started using the new name still works.
	Use:     "credentials",
	Aliases: []string{"credential", "secrets", "secret"},
	Short:   "Manage credentials stored on the AgentSpan server",
}

// ─── secrets set ──────────────────────────────────────────────────────────────

var secretsSetCmd = &cobra.Command{
	Use:   "set <NAME> <VALUE>",
	Short: "Store a secret on the server",
	Args:  cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		name, value := args[0], args[1]
		if err := runSecretsSet(name, value); err != nil {
			return err
		}
		color.Green("Secret %q stored.", name)
		return nil
	},
}

func runSecretsSet(name, value string) error {
	cfg := config.Load()
	c := client.New(cfg)
	return c.SetCredential(name, value)
}

// ─── secrets list ─────────────────────────────────────────────────────────────

var secretsListCmd = &cobra.Command{
	Use:   "list",
	Short: "List stored secrets (name, partial value, last updated)",
	RunE: func(cmd *cobra.Command, args []string) error {
		output, err := runSecretsList()
		if err != nil {
			return err
		}
		fmt.Print(output)
		return nil
	},
}

func runSecretsList() (string, error) {
	cfg := config.Load()
	c := client.New(cfg)
	secrets, err := c.ListCredentials()
	if err != nil {
		return "", fmt.Errorf("list secrets: %w", err)
	}
	if len(secrets) == 0 {
		return "No secrets stored.\n", nil
	}
	var buf bytes.Buffer
	w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "NAME\tPARTIAL\tUPDATED")
	fmt.Fprintln(w, "----\t-------\t-------")
	for _, s := range secrets {
		fmt.Fprintf(w, "%s\t%s\t%s\n", s.Name, s.Partial, s.UpdatedAt)
	}
	w.Flush()
	return buf.String(), nil
}

// ─── secrets delete ───────────────────────────────────────────────────────────

var secretsDeleteCmd = &cobra.Command{
	Use:   "delete <NAME>",
	Short: "Delete a stored secret",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := runSecretsDelete(args[0]); err != nil {
			return err
		}
		color.Green("Secret %q deleted.", args[0])
		return nil
	},
}

func runSecretsDelete(name string) error {
	cfg := config.Load()
	return client.New(cfg).DeleteCredential(name)
}

// ─── init ─────────────────────────────────────────────────────────────────────

func init() {
	secretsCmd.AddCommand(secretsSetCmd)
	secretsCmd.AddCommand(secretsListCmd)
	secretsCmd.AddCommand(secretsDeleteCmd)

	// Default action: show secrets list
	secretsCmd.RunE = func(cmd *cobra.Command, args []string) error {
		output, err := runSecretsList()
		if err != nil {
			return err
		}
		fmt.Print(output)
		return nil
	}

	rootCmd.AddCommand(secretsCmd)
}
