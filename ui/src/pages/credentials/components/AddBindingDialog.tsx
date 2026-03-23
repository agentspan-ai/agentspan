import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useForm } from "react-hook-form";
import { useCreateBinding } from "../hooks/useCredentialsApi";

interface FormValues {
  logical_key: string;
  store_name: string;
}

interface Props {
  credentialName: string;
  token: string | null;
  onUnauthorized: () => void;
  onSuccess: () => void;
  onError?: () => void;
  onClose: () => void;
}

export function AddBindingDialog({
  credentialName,
  token,
  onUnauthorized,
  onSuccess,
  onError,
  onClose,
}: Props) {
  const createBinding = useCreateBinding({ token, onUnauthorized });
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: { logical_key: "", store_name: credentialName },
  });

  async function onSubmit(data: FormValues) {
    try {
      await createBinding.mutateAsync(data);
      onSuccess();
      onClose();
    } catch {
      onError?.();
    }
  }

  const isLoading = isSubmitting || createBinding.isLoading;

  return (
    <Dialog open fullWidth maxWidth="sm" onClose={onClose}>
      <DialogTitle>Add Binding</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Logical Key"
              inputProps={{
                "aria-label": "Logical Key",
                style: { fontFamily: "monospace" },
              }}
              {...register("logical_key", { required: "Logical key is required." })}
              error={!!errors.logical_key}
              helperText={
                errors.logical_key?.message ??
                "The name your code declares, e.g. GH_TOKEN"
              }
              fullWidth
              required
              autoFocus
            />
            <TextField
              label="Store Name"
              inputProps={{
                "aria-label": "Store Name",
                style: { fontFamily: "monospace" },
              }}
              {...register("store_name", { required: "Store name is required." })}
              error={!!errors.store_name}
              helperText={
                errors.store_name?.message ??
                "The credential this key resolves to, e.g. GITHUB_TOKEN"
              }
              fullWidth
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="text" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={isLoading}>
            {isLoading ? "Adding…" : "Add binding"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
