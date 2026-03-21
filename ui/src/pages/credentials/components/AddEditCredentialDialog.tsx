import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import {
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
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

interface KnownCredential {
  name: string;
  provider: string;
}

const KNOWN_LLM_CREDENTIALS: KnownCredential[] = [
  { name: "ANTHROPIC_API_KEY", provider: "Anthropic (Claude)" },
  { name: "OPENAI_API_KEY", provider: "OpenAI (GPT-4, GPT-4o, etc.)" },
  { name: "GEMINI_API_KEY", provider: "Google Gemini" },
  { name: "GOOGLE_API_KEY", provider: "Google AI Studio" },
  { name: "AZURE_OPENAI_API_KEY", provider: "Azure OpenAI" },
  { name: "AZURE_OPENAI_ENDPOINT", provider: "Azure OpenAI endpoint" },
  { name: "MISTRAL_API_KEY", provider: "Mistral AI" },
  { name: "GROQ_API_KEY", provider: "Groq" },
  { name: "COHERE_API_KEY", provider: "Cohere" },
  { name: "TOGETHER_API_KEY", provider: "Together AI" },
  { name: "PERPLEXITY_API_KEY", provider: "Perplexity" },
  { name: "HUGGINGFACE_API_TOKEN", provider: "HuggingFace" },
  { name: "REPLICATE_API_TOKEN", provider: "Replicate" },
  { name: "AWS_ACCESS_KEY_ID", provider: "AWS Bedrock" },
  { name: "AWS_SECRET_ACCESS_KEY", provider: "AWS Bedrock" },
  { name: "BEDROCK_API_KEY", provider: "AWS Bedrock (custom)" },
  { name: "VERTEX_AI_PROJECT_ID", provider: "Google Vertex AI" },
  { name: "DEEPSEEK_API_KEY", provider: "DeepSeek" },
  { name: "XAI_API_KEY", provider: "xAI (Grok)" },
];

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
    setValue,
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
          <Stack spacing={4} sx={{ mt: 1 }}>
            {mode === "add" && (
              <>
                <Autocomplete
                  options={KNOWN_LLM_CREDENTIALS}
                  getOptionLabel={(opt) =>
                    typeof opt === "string" ? opt : `${opt.name}`
                  }
                  renderOption={(props, opt) => (
                    <li {...props} key={opt.name}>
                      <Stack>
                        <Typography variant="body2" fontFamily="monospace" fontWeight={500}>
                          {opt.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {opt.provider}
                        </Typography>
                      </Stack>
                    </li>
                  )}
                  onChange={(_, option) => {
                    if (option && typeof option !== "string") {
                      setValue("name", option.name, { shouldValidate: true });
                    }
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Quick select a well-known LLM key"
                      placeholder="Search by provider or key name…"
                      size="small"
                    />
                  )}
                />
                <Divider />
              </>
            )}

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
