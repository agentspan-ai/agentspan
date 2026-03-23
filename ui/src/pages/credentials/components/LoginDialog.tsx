import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import { useLogin } from "../hooks/useCredentialsApi";

interface LoginDialogProps {
  /**
   * Called with the received JWT on successful login.
   * Caller is responsible for calling setToken(tok) and refetching credentials —
   * LoginDialog only signals success and does not touch localStorage directly.
   */
  onSuccess: (token: string) => void;
}

export function LoginDialog({ onSuccess }: LoginDialogProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const loginMutation = useLogin();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const resp = await loginMutation.mutateAsync({ username, password });
      onSuccess(resp.token);
    } catch (err: any) {
      if (err && err.status === 401) {
        setError("Invalid username or password.");
      } else {
        setError("Login failed — please try again.");
      }
    }
  }

  return (
    <Dialog open fullWidth maxWidth="xs" disableEscapeKeyDown>
      <DialogTitle>Sign in to manage credentials</DialogTitle>
      <DialogContent>
        <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Username"
              id="login-username"
              inputProps={{ "aria-label": "Username" }}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              fullWidth
              required
              autoFocus
            />
            <TextField
              label="Password"
              id="login-password"
              inputProps={{ "aria-label": "Password", type: "password" }}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
              required
            />
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={loginMutation.isLoading}
            >
              {loginMutation.isLoading ? "Signing in…" : "Log in"}
            </Button>
          </Stack>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
