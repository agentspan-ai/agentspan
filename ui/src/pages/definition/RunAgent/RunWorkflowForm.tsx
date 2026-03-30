import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Grid,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Button } from "components";
import Paper from "components/Paper";
import MuiAlert from "components/MuiAlert";
import { ConductorAutoComplete } from "components/v1";
import ConductorInput from "components/v1/ConductorInput";
import PlayIcon from "components/v1/icons/PlayIcon";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ActorRef } from "xstate";
import { useSelector } from "@xstate/react";
import { State } from "xstate";
import { WorkflowDefinitionEvents } from "../state";
import { RunMachineContext, RunMachineEvents } from "./state";
import { useFetchContext, fetchWithContext } from "plugins/fetch";
import { useAuthHeaders } from "utils/query";
import { MODEL_OPTIONS } from "utils/constants/models";

const GENERIC_ERROR_MESSAGE = "Error while running agent.";

interface RunWorkFlowFormProps {
  runTabActor: ActorRef<RunMachineEvents>;
  workflowDefinitionActor: ActorRef<WorkflowDefinitionEvents>;
}

export const RunWorkFlowForm = ({
  runTabActor,
}: RunWorkFlowFormProps) => {
  const currentWf = useSelector(
    runTabActor,
    (state: State<RunMachineContext>) => state.context.currentWf,
  );

  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [mediaUrls, setMediaUrls] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const navigate = useNavigate();
  const fetchContext = useFetchContext();
  const authHeaders = useAuthHeaders();

  const runAgent = async () => {
    if (!prompt.trim()) {
      setErrorMessage("Please enter a prompt.");
      return;
    }

    setIsRunning(true);
    setErrorMessage("");

    try {
      // Build the StartRequest payload (matches server's StartRequest.java)
      const agentConfig = { ...currentWf };

      // Override model if user specified one
      if (model && model.trim()) {
        agentConfig.model = model.trim();
      }

      const payload: Record<string, unknown> = {
        agentConfig,
        prompt: prompt.trim(),
      };
      if (idempotencyKey.trim()) {
        payload.idempotencyKey = idempotencyKey.trim();
      }
      if (mediaUrls.trim()) {
        payload.media = mediaUrls
          .split("\n")
          .map((u: string) => u.trim())
          .filter(Boolean);
      }
      if (timeoutSeconds.trim()) {
        const parsed = parseInt(timeoutSeconds.trim(), 10);
        if (!isNaN(parsed) && parsed > 0) {
          payload.timeoutSeconds = parsed;
        }
      }

      // Start the agent — response is JSON { executionId, agentName }
      const result = await fetchWithContext(
        "/agent/start",
        fetchContext,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify(payload),
        },
      );

      const executionId = result?.executionId || result;
      navigate(
        `/execution/${typeof executionId === "string" ? executionId.trim() : executionId}`,
      );
    } catch (err: any) {
      try {
        if (err?.json) {
          const json = await err.json();
          setErrorMessage(json?.message || GENERIC_ERROR_MESSAGE);
        } else {
          setErrorMessage(err?.message || GENERIC_ERROR_MESSAGE);
        }
      } catch {
        setErrorMessage(GENERIC_ERROR_MESSAGE);
      }
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100%", p: 6 }}>
      <Paper variant="outlined" sx={{ padding: 6 }}>
        {errorMessage && (
          <Box mb={3}>
            <MuiAlert onClose={() => setErrorMessage("")} severity="error">
              {errorMessage}
            </MuiAlert>
          </Box>
        )}
        <Grid container sx={{ width: "100%" }} spacing={3}>
          <Grid size={12}>
            <ConductorInput
              id="prompt-input"
              label="Prompt"
              placeholder="What would you like the agent to do?"
              multiline
              minRows={6}
              fullWidth
              value={prompt}
              onTextInputChange={setPrompt}
              required
              autoFocus
            />
          </Grid>

          {/* Advanced options */}
          <Grid size={12}>
            <Accordion
              disableGutters
              elevation={0}
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                "&:before": { display: "none" },
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="body2" color="text.secondary">
                  Advanced options
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0 }}>
                <Grid container spacing={3}>
                  <Grid size={12}>
                    <ConductorAutoComplete
                      id="model-input"
                      freeSolo
                      fullWidth
                      label="Model (overrides agent default)"
                      placeholder="Select or type a model..."
                      options={MODEL_OPTIONS}
                      onChange={(_e, v) => setModel(v)}
                      value={model}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <ConductorInput
                      id="timeout-input"
                      label="Timeout (seconds)"
                      placeholder="e.g. 300"
                      fullWidth
                      value={timeoutSeconds}
                      onTextInputChange={setTimeoutSeconds}
                      type="number"
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <ConductorInput
                      id="idempotency-input"
                      label="Idempotency key"
                      placeholder="Optional unique key"
                      fullWidth
                      value={idempotencyKey}
                      onTextInputChange={setIdempotencyKey}
                    />
                  </Grid>
                  <Grid size={12}>
                    <ConductorInput
                      id="media-input"
                      label="Media URLs (one per line)"
                      placeholder="https://example.com/image.png"
                      multiline
                      minRows={2}
                      fullWidth
                      value={mediaUrls}
                      onTextInputChange={setMediaUrls}
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          </Grid>

          <Grid display="flex" justifyContent="flex-end" size={12}>
            <Button
              id="run-agent-btn"
              variant="contained"
              startIcon={<PlayIcon />}
              onClick={runAgent}
              disabled={isRunning}
            >
              {isRunning ? "Running..." : "Run"}
            </Button>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
};
