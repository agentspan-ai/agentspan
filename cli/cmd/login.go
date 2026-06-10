// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package cmd

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/agentspan-ai/agentspan/cli/auth"
	"github.com/agentspan-ai/agentspan/cli/config"
	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var (
	loginDomain      string
	loginClientID    string
	loginScope       string
	loginNoOpen      bool
	loginKeyID       string
	loginKeySecret   string
	loginDevice      bool
	loginRedirectURI string
)

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Log in via your browser (Auth0) and store the token",
	Long: `Logs in through your browser using the same Auth0 application the orkes-conductor
UI uses (Authorization Code + PKCE with a loopback redirect): your browser opens the
hosted login page (username/password, Google, SSO — whatever the tenant allows), the
redirect is captured locally, and the resulting token is stored in ~/.agentspan/token
and sent to the server as the X-Authorization header on every request.

The Auth0 domain and client id are auto-discovered from the server's /context.js (the
same runtime config the UI consumes). Override with --auth0-domain / --auth0-client-id.

Alternative grants:
  --device                  OAuth Device Authorization flow (headless/SSH machines;
                            requires the Device Code grant enabled on the Auth0 app)
  --key-id / --key-secret   orkes application access key (service accounts / CI)

On a localhost server with auth disabled, login is not required — requests are accepted
as anonymous admin automatically.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := getConfig()

		// No --server flag and no env override: ask which instance to log into
		// (pre-filled with the current default; plain Enter keeps it). TTY only.
		if serverURL == "" &&
			os.Getenv("AGENTSPAN_SERVER_URL") == "" && os.Getenv("AGENT_SERVER_URL") == "" &&
			term.IsTerminal(int(os.Stdin.Fd())) {
			if entered := promptServerURL(os.Stdin, cfg.ServerURL); entered != "" {
				cfg.ServerURL = entered
			}
		}

		keyID := loginKeyID
		if keyID == "" {
			keyID = os.Getenv("AGENTSPAN_AUTH_KEY")
		}
		keySecret := loginKeySecret
		if keySecret == "" {
			keySecret = os.Getenv("AGENTSPAN_AUTH_SECRET")
		}

		var err error
		if keyID != "" && keySecret != "" {
			err = loginWithKey(cfg, keyID, keySecret)
		} else {
			err = loginWithAuth0(cfg)
		}
		if err != nil {
			return err
		}

		// A successful login pins this server as the default for subsequent commands.
		if config.FileServerURL() != cfg.ServerURL {
			if serr := config.SaveDefaultServer(cfg.ServerURL); serr == nil {
				color.Green("Default server set to %s", cfg.ServerURL)
			}
		}
		return nil
	},
}

// promptServerURL asks for the server URL, showing the current default. Returns the
// entered URL ("" = keep current). A missing scheme defaults to http:// (local instances).
func promptServerURL(r io.Reader, current string) string {
	fmt.Printf("Server URL [%s]: ", current)
	line, _ := bufio.NewReader(r).ReadString('\n')
	s := strings.TrimSpace(line)
	if s == "" {
		return ""
	}
	if !strings.Contains(s, "://") {
		s = "http://" + s
	}
	return strings.TrimRight(s, "/")
}

// loginWithKey authenticates via an orkes application access key (keyId/keySecret) —
// the internal / service-account path: POST /api/token -> JWT. The key/secret are stored
// (0600) so the client can re-mint the token when it expires.
func loginWithKey(cfg *config.Config, keyID, keySecret string) error {
	token, exp, err := auth.MintOrkesToken(cfg.ServerURL, keyID, keySecret)
	if err != nil {
		return err
	}
	if err := config.SaveToken(&config.TokenInfo{
		AccessToken: token,
		ExpiresAt:   exp,
		KeyID:       keyID,
		KeySecret:   keySecret,
		ServerURL:   cfg.ServerURL,
	}); err != nil {
		return fmt.Errorf("store token: %w", err)
	}
	color.Green("Logged in with access key. Token stored in %s", config.TokenPath())
	return nil
}

// loginWithAuth0 runs the Auth0 device authorization grant (browser-based, matching the UI).
func loginWithAuth0(cfg *config.Config) error {
	domain, clientID, useIDToken := loginDomain, loginClientID, false
	if domain == "" || clientID == "" {
		discovered, err := auth.DiscoverConfig(cfg.ServerURL)
		if err != nil {
			return fmt.Errorf(
				"could not discover Auth0 config from %s (%w).\n"+
					"Pass --auth0-domain/--auth0-client-id, use --key-id/--key-secret, or confirm the server has auth enabled",
				cfg.ServerURL, err)
		}
		if domain == "" {
			domain = discovered.Domain
		}
		if clientID == "" {
			clientID = discovered.ClientID
		}
		useIDToken = discovered.UseIDToken
	}

	if loginDevice {
		return loginWithDeviceFlow(domain, clientID, useIDToken)
	}
	// Default: browser Authorization Code + PKCE — the same grant the UI uses, so it
	// works with the stock UI clientId (device flow requires a tenant-side grant toggle).
	return loginWithBrowserPKCE(domain, clientID, useIDToken)
}

// loginWithDeviceFlow runs the OAuth Device Authorization grant (for headless machines).
// Requires the Device Code grant to be enabled on the Auth0 application.
func loginWithDeviceFlow(domain, clientID string, useIDToken bool) error {
	dc, err := auth.RequestDeviceCode(domain, clientID, loginScope)
	if err != nil {
		if strings.Contains(err.Error(), "unauthorized_client") {
			return fmt.Errorf(
				"the Device Authorization grant is not enabled on this Auth0 client.\n"+
					"Run without --device to use the browser login, or enable the Device Code grant "+
					"on the application in the Auth0 dashboard (%w)", err)
		}
		return err
	}

	verifyURL := dc.VerificationURIComplete
	if verifyURL == "" {
		verifyURL = dc.VerificationURI
	}
	fmt.Println()
	color.Cyan("To log in, open this URL in your browser:")
	fmt.Printf("  %s\n", verifyURL)
	color.Cyan("Confirm this code is shown: %s", dc.UserCode)
	fmt.Println()
	if !loginNoOpen {
		_ = openBrowser(verifyURL) // best-effort; URL is printed regardless
	}
	fmt.Println("Waiting for you to complete login in the browser...")

	tok, err := auth.PollForToken(domain, clientID, dc)
	if err != nil {
		return err
	}
	return saveAuth0Token(tok, useIDToken, domain, clientID)
}

// loginWithBrowserPKCE runs the Authorization Code + PKCE flow with a loopback redirect
// (RFC 8252): bind the redirect URI locally, open the hosted login in the browser, capture
// the ?code= from the redirect, and exchange it with the PKCE verifier. Works with the same
// public clientId the UI uses — the redirect URI must exactly match one of the Auth0 app's
// Allowed Callback URLs (the local UI origin, e.g. http://localhost:5001, is whitelisted).
func loginWithBrowserPKCE(domain, clientID string, useIDToken bool) error {
	verifier, challenge, err := auth.GeneratePKCE()
	if err != nil {
		return err
	}
	state, err := auth.RandomState()
	if err != nil {
		return err
	}
	authorizeURL := auth.BuildAuthorizeURL(domain, clientID, loginRedirectURI, loginScope, state, challenge)

	// Bind the loopback port BEFORE printing anything or opening the browser —
	// fail fast if it's busy (e.g. the UI dev server holds it).
	capture, err := auth.StartCodeCapture(loginRedirectURI, state)
	if err != nil {
		return err
	}

	fmt.Println()
	color.Cyan("To log in, open this URL in your browser:")
	fmt.Printf("  %s\n", authorizeURL)
	fmt.Println()
	if !loginNoOpen {
		_ = openBrowser(authorizeURL)
	}
	fmt.Printf("Waiting for the browser login (redirect captured on %s)...\n", loginRedirectURI)

	code, err := capture.Wait(5 * time.Minute)
	if err != nil {
		return err
	}

	tok, err := auth.ExchangeCode(domain, clientID, code, verifier, loginRedirectURI)
	if err != nil {
		return err
	}
	return saveAuth0Token(tok, useIDToken, domain, clientID)
}

func saveAuth0Token(tok *auth.Token, useIDToken bool, domain, clientID string) error {
	if err := config.SaveToken(&config.TokenInfo{
		AccessToken:  tok.AccessToken,
		IDToken:      tok.IDToken,
		RefreshToken: tok.RefreshToken,
		ExpiresAt:    time.Now().Add(time.Duration(tok.ExpiresIn) * time.Second).Unix(),
		UseIDToken:   useIDToken,
		Auth0Domain:  domain,
		ClientID:     clientID,
	}); err != nil {
		return fmt.Errorf("store token: %w", err)
	}
	color.Green("Logged in. Token stored in %s", config.TokenPath())
	return nil
}

var logoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Remove the stored auth token",
	RunE: func(cmd *cobra.Command, args []string) error {
		cleared := false
		if t, _ := config.LoadToken(); t != nil {
			if err := config.ClearToken(); err != nil {
				return fmt.Errorf("clear token: %w", err)
			}
			cleared = true
		}
		// Also clear any legacy API key stored in config.json.
		if c := config.Load(); c.APIKey != "" {
			c.APIKey = ""
			if err := config.Save(c); err != nil {
				return fmt.Errorf("save config: %w", err)
			}
			cleared = true
		}
		if cleared {
			color.Green("Logged out.")
		} else {
			color.Yellow("Not currently logged in.")
		}
		return nil
	},
}

// openBrowser best-effort opens a URL in the default browser.
func openBrowser(url string) error {
	var name string
	var args []string
	switch runtime.GOOS {
	case "darwin":
		name, args = "open", []string{url}
	case "windows":
		name, args = "rundll32", []string{"url.dll,FileProtocolHandler", url}
	default:
		name, args = "xdg-open", []string{url}
	}
	return exec.Command(name, args...).Start()
}

func init() {
	loginCmd.Flags().StringVar(&loginKeyID, "key-id", "", "orkes access key id (service-account auth; env AGENTSPAN_AUTH_KEY)")
	loginCmd.Flags().StringVar(&loginKeySecret, "key-secret", "", "orkes access key secret (service-account auth; env AGENTSPAN_AUTH_SECRET)")
	loginCmd.Flags().StringVar(&loginDomain, "auth0-domain", "", "Auth0 domain (default: discovered from server /context.js)")
	loginCmd.Flags().StringVar(&loginClientID, "auth0-client-id", "", "Auth0 client id (default: discovered from server /context.js)")
	loginCmd.Flags().StringVar(&loginScope, "scope", auth.DefaultScope, "OAuth scope to request")
	loginCmd.Flags().BoolVar(&loginNoOpen, "no-open", false, "Do not auto-open the browser")
	loginCmd.Flags().BoolVar(&loginDevice, "device", false, "Use the OAuth Device Authorization flow instead of the browser login (headless machines)")
	loginCmd.Flags().StringVar(&loginRedirectURI, "redirect-uri", "http://localhost:5001", "Loopback redirect URI for the browser login; must exactly match an Allowed Callback URL of the Auth0 app (default: the local orkes UI origin)")
	rootCmd.AddCommand(loginCmd)
	rootCmd.AddCommand(logoutCmd)
}
