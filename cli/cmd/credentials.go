package cmd

import (
	"bytes"
	"fmt"
	"text/tabwriter"

	"github.com/agentspan/agentspan/cli/client"
	"github.com/agentspan/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var credentialsCmd = &cobra.Command{
	Use:     "credentials",
	Aliases: []string{"creds"},
	Short:   "Manage credentials stored on the AgentSpan server",
}

// ─── credentials set ──────────────────────────────────────────────────────────

var credentialsSetStoreName string

var credentialsSetCmd = &cobra.Command{
	Use:   "set <NAME> <VALUE>",
	Short: "Store a credential on the server",
	Long: `Store a credential value.

Simple form (logical name = store name, server auto-binds):
  agentspan credentials set GITHUB_TOKEN ghp_xxx

Advanced form (custom store name, explicit binding needed):
  agentspan credentials set --name github-prod ghp_xxx
  agentspan credentials bind GITHUB_TOKEN github-prod`,
	RunE: func(cmd *cobra.Command, args []string) error {
		storeName, _ := cmd.Flags().GetString("name")
		var name, value string
		if storeName != "" {
			if len(args) != 1 {
				return fmt.Errorf("with --name, provide exactly one argument: the credential value")
			}
			name = storeName
			value = args[0]
		} else {
			if len(args) != 2 {
				return fmt.Errorf("usage: credentials set <NAME> <VALUE>  or  credentials set --name <STORE> <VALUE>")
			}
			name = args[0]
			value = args[1]
		}
		if err := runCredentialsSet(name, value, storeName); err != nil {
			return err
		}
		color.Green("Credential %q stored.", name)
		return nil
	},
}

func runCredentialsSet(nameOrValue, value, storeName string) error {
	cfg := config.Load()
	c := client.New(cfg)
	credName := nameOrValue
	credValue := value
	if storeName != "" {
		credName = storeName
		credValue = nameOrValue
	}
	return c.SetCredential(credName, credValue)
}

// ─── credentials list ─────────────────────────────────────────────────────────

var credentialsListCmd = &cobra.Command{
	Use:   "list",
	Short: "List stored credentials (name, partial value, last updated)",
	RunE: func(cmd *cobra.Command, args []string) error {
		output, err := runCredentialsList()
		if err != nil {
			return err
		}
		fmt.Print(output)
		return nil
	},
}

func runCredentialsList() (string, error) {
	cfg := config.Load()
	c := client.New(cfg)
	creds, err := c.ListCredentials()
	if err != nil {
		return "", fmt.Errorf("list credentials: %w", err)
	}
	if len(creds) == 0 {
		return "No credentials stored.\n", nil
	}
	var buf bytes.Buffer
	w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "NAME\tPARTIAL\tUPDATED")
	fmt.Fprintln(w, "----\t-------\t-------")
	for _, cr := range creds {
		fmt.Fprintf(w, "%s\t%s\t%s\n", cr.Name, cr.Partial, cr.UpdatedAt)
	}
	w.Flush()
	return buf.String(), nil
}

// ─── credentials delete ───────────────────────────────────────────────────────

var credentialsDeleteCmd = &cobra.Command{
	Use:   "delete <NAME>",
	Short: "Delete a stored credential",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := runCredentialsDelete(args[0]); err != nil {
			return err
		}
		color.Green("Credential %q deleted.", args[0])
		return nil
	},
}

func runCredentialsDelete(name string) error {
	cfg := config.Load()
	return client.New(cfg).DeleteCredential(name)
}

// ─── credentials bind ─────────────────────────────────────────────────────────

var credentialsBindCmd = &cobra.Command{
	Use:   "bind <LOGICAL_KEY> <STORE_NAME>",
	Short: "Bind a logical credential key to a stored secret",
	Args:  cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := runCredentialsBind(args[0], args[1]); err != nil {
			return err
		}
		color.Green("Bound %q -> %q.", args[0], args[1])
		return nil
	},
}

func runCredentialsBind(logicalKey, storeName string) error {
	cfg := config.Load()
	return client.New(cfg).SetBinding(logicalKey, storeName)
}

// ─── credentials bindings ─────────────────────────────────────────────────────

var credentialsBindingsCmd = &cobra.Command{
	Use:   "bindings",
	Short: "List logical key → store name bindings",
	RunE: func(cmd *cobra.Command, args []string) error {
		output, err := runCredentialsBindings()
		if err != nil {
			return err
		}
		fmt.Print(output)
		return nil
	},
}

func runCredentialsBindings() (string, error) {
	cfg := config.Load()
	c := client.New(cfg)
	bindings, err := c.ListBindings()
	if err != nil {
		return "", fmt.Errorf("list bindings: %w", err)
	}
	if len(bindings) == 0 {
		return "No bindings configured.\n", nil
	}
	var buf bytes.Buffer
	w := tabwriter.NewWriter(&buf, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "LOGICAL KEY\tSTORE NAME")
	fmt.Fprintln(w, "-----------\t----------")
	for _, b := range bindings {
		fmt.Fprintf(w, "%s\t%s\n", b.LogicalKey, b.StoreName)
	}
	w.Flush()
	return buf.String(), nil
}

// ─── init ─────────────────────────────────────────────────────────────────────

func init() {
	credentialsSetCmd.Flags().StringVar(&credentialsSetStoreName, "name", "",
		"Store name (overrides logical key as the storage key)")

	credentialsCmd.AddCommand(credentialsSetCmd)
	credentialsCmd.AddCommand(credentialsListCmd)
	credentialsCmd.AddCommand(credentialsDeleteCmd)
	credentialsCmd.AddCommand(credentialsBindCmd)
	credentialsCmd.AddCommand(credentialsBindingsCmd)

	// Default action: show credentials list
	credentialsCmd.RunE = func(cmd *cobra.Command, args []string) error {
		output, err := runCredentialsList()
		if err != nil {
			return err
		}
		fmt.Print(output)
		return nil
	}

	rootCmd.AddCommand(credentialsCmd)
}
