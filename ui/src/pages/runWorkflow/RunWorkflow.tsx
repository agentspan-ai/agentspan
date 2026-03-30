import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Grid,
  Paper,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Button } from "components";
import MuiAlert from "components/MuiAlert";
import NavLink from "components/NavLink";
import { ConductorAutoComplete } from "components/v1";
import ConductorInput from "components/v1/ConductorInput";
import PlayIcon from "components/v1/icons/PlayIcon";
import ResetIcon from "components/v1/icons/ResetIcon";
import XCloseIcon from "components/v1/icons/XCloseIcon";
import { useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import { useNavigate, useLocation } from "react-router";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import { useAuth } from "shared/auth";
import { useFetchContext, fetchWithContext } from "plugins/fetch";
import { useAuthHeaders, useWorkflowDefsByVersions } from "utils/query";
import { MODEL_OPTIONS } from "utils/constants/models";

const GENERIC_ERROR_MESSAGE = "Error while running agent.";

export function RunWorkflow() {
  const { isTrialExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const fetchContext = useFetchContext();
  const authHeaders = useAuthHeaders();

  const workflowDefByVersions = useWorkflowDefsByVersions();
  const workflowNames = useMemo(
    (): string[] =>
      workflowDefByVersions
        ? Array.from(workflowDefByVersions.get("lookups").keys())
        : [],
    [workflowDefByVersions],
  );

  // Pre-select agent name if passed via navigation state (from Execute button)
  const preSelectedAgent = (location.state as any)?.agentName ?? null;
  const [agentName, setAgentName] = useState<string | null>(preSelectedAgent);
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [mediaUrls, setMediaUrls] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("");
  const [lastExecutionId, setLastExecutionId] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const runAgent = async () => {
    if (!agentName) {
      setErrorMessage("Please select an agent.");
      return;
    }
    if (!prompt.trim()) {
      setErrorMessage("Please enter a prompt.");
      return;
    }

    setIsRunning(true);
    setErrorMessage("");
    setLastExecutionId("");

    try {
      // Fetch the agent definition via the AgentSpan API (same as CLI)
      const agentDef = await fetchWithContext(
        `/agent/${encodeURIComponent(agentName)}`,
        fetchContext,
        {
          method: "GET",
          headers: { "Content-Type": "application/json", ...authHeaders },
        },
      );

      // Build the StartRequest payload (matches server's StartRequest.java)
      const payload: Record<string, unknown> = {
        agentConfig: agentDef,
        prompt: prompt.trim(),
      };

      // Optional: model override — merge into agentConfig
      if (model && model.trim()) {
        (payload.agentConfig as Record<string, unknown>).model = model.trim();
      }
      if (idempotencyKey.trim()) {
        payload.idempotencyKey = idempotencyKey.trim();
      }
      if (mediaUrls.trim()) {
        payload.media = mediaUrls
          .split("\n")
          .map((u) => u.trim())
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
      setLastExecutionId(
        typeof executionId === "string" ? executionId.trim() : executionId,
      );
      setErrorMessage("");
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

  const clearForm = () => {
    setAgentName(null);
    setPrompt("");
    setModel(null);
    setIdempotencyKey("");
    setMediaUrls("");
    setTimeoutSeconds("");
    setErrorMessage("");
    setLastExecutionId("");
  };

  return (
    <>
      <Helmet>
        <title>Run Agent</title>
      </Helmet>
      <Box style={{ width: "100%", visibility: "visible" }}>
        <SectionContainer
          header={
            <SectionHeader
              _deprecate_marginTop={0}
              title="Run Agent"
              actions={
                <>
                  <Button
                    variant="text"
                    onClick={() => navigate(-1)}
                    startIcon={<XCloseIcon />}
                  >
                    Close
                  </Button>
                  <Button
                    id="clear-info-btn"
                    variant="text"
                    onClick={clearForm}
                    startIcon={<ResetIcon />}
                  >
                    Reset
                  </Button>
                  <Button
                    id="run-workflow-btn"
                    variant="contained"
                    startIcon={<PlayIcon />}
                    onClick={runAgent}
                    disabled={isTrialExpired || isRunning}
                  >
                    {isRunning ? "Running..." : "Run agent"}
                  </Button>
                </>
              }
            />
          }
        >
          {errorMessage && (
            <Box mb={5}>
              <MuiAlert onClose={() => setErrorMessage("")} severity="error">
                {errorMessage}
              </MuiAlert>
            </Box>
          )}
          {lastExecutionId !== "" && (
            <Box mb={5}>
              <MuiAlert
                id="workflow-created-alert"
                onClose={() => setLastExecutionId("")}
                severity="success"
              >
                Agent started:&nbsp;
                <NavLink
                  id="workflow-execution-id"
                  path={`/execution/${lastExecutionId}`}
                >
                  {lastExecutionId}
                </NavLink>
              </MuiAlert>
            </Box>
          )}
          <Box sx={{ overflowY: "auto" }}>
            <Grid container sx={{ width: "100%" }} spacing={3}>
              <Grid sx={{ width: "100%" }} size={{ md: 8 }}>
                <Paper variant="outlined" sx={{ padding: 6, pb: 8 }}>
                  <Grid
                    container
                    sx={{ width: "100%" }}
                    spacing={3}
                    rowSpacing={6}
                  >
                    <Grid size={12}>
                      <ConductorAutoComplete
                        id="workflow-name-dropdown"
                        fullWidth
                        label="Agent name"
                        options={workflowNames}
                        onChange={(__, val) => setAgentName(val)}
                        value={agentName}
                        autoFocus
                        required
                      />
                    </Grid>
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
                  </Grid>
                </Paper>
              </Grid>
            </Grid>
          </Box>
        </SectionContainer>
      </Box>
    </>
  );
}
