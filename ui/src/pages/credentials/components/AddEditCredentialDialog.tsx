import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  useCreateCredential,
  useUpdateCredential,
} from "../hooks/useCredentialsApi";

interface FormValues {
  name: string;
  value: string;
}

interface Props {
  mode: "add" | "edit";
  initialName?: string;
  token: string | null;
  onUnauthorized: () => void;
  onSuccess: () => void;
  onClose: () => void;
}

export function AddEditCredentialDialog({
  mode,
  initialName = "",
  token,
  onUnauthorized,
  onSuccess,
  onClose,
}: Props) {
  const [showValue, setShowValue] = useState(false);
  const apiOpts = { token, onUnauthorized };
  const createMutation = useCreateCredential(apiOpts);
  const updateMutation = useUpdateCredential(apiOpts);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<FormValues>({
    defaultValues: { name: initialName, value: "" },
  });

  async function onSubmit(data: FormValues) {
    try {
      if (mode === "add") {
        await createMutation.mutateAsync({ name: data.name, value: data.value });
      } else {
        await updateMutation.mutateAsync({ name: data.name, value: data.value });
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      if (err?.status === 409) {
        setError("name", { message: "A credential with this name already exists." });
      }
    }
  }

  const isLoading = isSubmitting || createMutation.isLoading || updateMutation.isLoading;

  return (
    <Dialog open fullWidth maxWidth="sm" onClose={onClose}>
      <DialogTitle>{mode === "add" ? "Add Credential" : "Edit Credential"}</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              inputProps={{
                "aria-label": "Name",
                readOnly: mode === "edit",
                style: { fontFamily: "monospace" },
              }}
              {...register("name", { required: "Name is required." })}
              error={!!errors.name}
              helperText={
                errors.name?.message ??
                "Convention: UPPER_SNAKE_CASE e.g. GITHUB_TOKEN"
              }
              fullWidth
              required
              autoFocus={mode === "add"}
            />
            <TextField
              label="Value"
              type={showValue ? "text" : "password"}
              inputProps={{ "aria-label": "Value" }}
              {...register("value", { required: "Value is required." })}
              error={!!errors.value}
              helperText={
                errors.value?.message ??
                (mode === "add"
                  ? "Encrypted at rest. Value shown only now — never displayed again."
                  : "Enter the full new value to update the stored secret.")
              }
              fullWidth
              required
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label={showValue ? "Hide" : "Show"}
                      onClick={() => setShowValue((v) => !v)}
                      edge="end"
                    >
                      {showValue ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="text" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={isLoading}>
            {isLoading ? "Saving…" : "Save"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
