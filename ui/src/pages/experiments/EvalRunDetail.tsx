import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Chip,
  LinearProgress,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import { Helmet } from "react-helmet";
import { useNavigate, useParams } from "react-router";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import { EXPERIMENTS_URL } from "utils/constants/route";
import { type EvalCase, type EvalCheck, type EvalRun, useEvalRun } from "./useEvalApi";

function PassFailBadge({ passed }: { passed: boolean }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        px: 1.25,
        py: 0.35,
        borderRadius: 1,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 0.6,
        lineHeight: 1.6,
        bgcolor: passed ? "rgba(22,163,74,0.12)" : "rgba(220,38,38,0.1)",
        color: passed ? "#15803d" : "#dc2626",
        border: "1px solid",
        borderColor: passed ? "rgba(22,163,74,0.3)" : "rgba(220,38,38,0.25)",
        flexShrink: 0,
        minWidth: 42,
        textAlign: "center",
      }}
    >
      {passed ? "PASS" : "FAIL"}
    </Box>
  );
}

function SemanticBox({ check }: { check: EvalCheck }) {
  const passed = check.passed;
  return (
    <Box
      sx={{
        bgcolor: passed ? "rgba(91,106,240,0.08)" : "rgba(220,38,38,0.06)",
        border: "1px solid",
        borderColor: passed ? "rgba(124,58,237,0.25)" : "rgba(220,38,38,0.3)",
        borderRadius: 1.5,
        p: 1.5,
        mt: 1,
      }}
    >
      <Typography
        variant="caption"
        fontWeight={700}
        color={passed ? "secondary.main" : "error.main"}
        textTransform="uppercase"
        letterSpacing={0.5}
        display="block"
        mb={0.5}
      >
        ⬡ Semantic Score — LLM Judge{!passed ? " (FAIL)" : ""}
      </Typography>
      <Typography variant="h6" fontWeight={700} color={passed ? "primary.main" : "error.main"}>
        {check.score?.toFixed(2)}
      </Typography>
      {check.reasoning && (
        <Typography variant="body2" color="text.secondary" mt={0.5} sx={{ lineHeight: 1.55 }}>
          {check.reasoning}
        </Typography>
      )}
    </Box>
  );
}

function CheckRow({ check }: { check: EvalCheck }) {
  const icon = check.passed ? (
    <CheckCircleOutlineIcon color="success" fontSize="small" />
  ) : (
    <CancelOutlinedIcon color="error" fontSize="small" />
  );

  if (check.score != null) {
    return (
      <Box sx={{ py: 0.5 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          {icon}
          <Typography variant="body2" fontFamily="monospace">
            {check.check}
          </Typography>
        </Box>
        <SemanticBox check={check} />
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, py: 0.5 }}>
      {icon}
      <Box sx={{ flex: 1 }}>
        <Typography variant="body2" fontFamily="monospace">
          {check.check}
        </Typography>
        {!check.passed && check.message && (
          <Typography variant="caption" color="error.main" display="block">
            {check.message}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function CaseAccordion({ evalCase }: { evalCase: EvalCase }) {
  const checks = evalCase.checks ?? [];
  const totalChecks = checks.length;
  const passedChecks = checks.filter((c) => c.passed).length;
  const failedChecks = totalChecks - passedChecks;
  const highestScore = checks.reduce<number | null>((max, c) => {
    if (c.score == null) return max;
    return max == null || c.score > max ? c.score : max;
  }, null);

  const checkSummary = totalChecks > 0
    ? `${passedChecks}/${totalChecks} checks${failedChecks > 0 ? ` · ${failedChecks} failed` : ""}${highestScore != null ? ` · semantic ${highestScore.toFixed(2)}` : ""}`
    : "";

  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: !evalCase.passed ? "rgba(220,38,38,0.03)" : "transparent",
        "&:last-child": { borderBottom: 0 },
        "&::before": { display: "none" },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon fontSize="small" sx={{ color: "text.disabled" }} />}
        sx={{ px: 2, py: 1.25, minHeight: "unset", "& .MuiAccordionSummary-content": { my: 0 } }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flex: 1, minWidth: 0 }}>
          <PassFailBadge passed={evalCase.passed} />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="body2" fontWeight={600}>
              {evalCase.name}
            </Typography>
            {evalCase.prompt && (
              <Typography variant="caption" color="text.secondary" display="block" noWrap>
                "{evalCase.prompt}"
              </Typography>
            )}
          </Box>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, ml: 2, flexShrink: 0 }}>
          {checkSummary && (
            <Typography
              variant="caption"
              color={failedChecks > 0 ? "error.main" : "text.secondary"}
              fontWeight={failedChecks > 0 ? 600 : 400}
            >
              {checkSummary}
            </Typography>
          )}
          {evalCase.agentName && (
            <Chip label={evalCase.agentName} size="small" variant="outlined" sx={{ fontSize: 11 }} />
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0.5, px: 2, pb: 1.5 }}>
        {evalCase.error && (
          <Typography variant="caption" color="error.main" display="block" mb={1}>
            Error: {evalCase.error}
          </Typography>
        )}
        {checks.map((check, i) => (
          <CheckRow key={i} check={check} />
        ))}
        {evalCase.output && (
          <Box sx={{ bgcolor: "grey.50", borderRadius: 1, p: 1.5, mt: 1.5 }}>
            <Typography
              variant="caption"
              fontWeight={700}
              color="text.secondary"
              textTransform="uppercase"
              letterSpacing={0.5}
              display="block"
              mb={0.5}
            >
              Agent Output
            </Typography>
            <Typography variant="body2" sx={{ lineHeight: 1.55 }}>
              {evalCase.output}
            </Typography>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
}

function strategyValidSummary(run: EvalRun): string | null {
  if (!run.strategy || !run.cases?.length) return null;
  const total = run.cases.length;
  const validCount = run.cases.filter((c) =>
    c.checks?.some((ch) => ch.check === "strategy_validation" && ch.passed),
  ).length;
  if (validCount === total) return `✓ all ${validCount}`;
  return `${validCount}/${total} valid`;
}

export default function EvalRunDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading } = useEvalRun(id ?? "");

  const pct =
    run && run.totalCases > 0
      ? Math.round((run.passedCases / run.totalCases) * 100)
      : 0;

  const displayName = run?.name || run?.agentName || "Eval Run";
  const strategyValid = run ? strategyValidSummary(run) : null;

  return (
    <>
      <Helmet>
        <title>{run?.name ?? (run ? `Eval Run — ${run.agentName}` : "Eval Run")}</title>
      </Helmet>
      <SectionHeader _deprecate_marginTop={0} title="Eval Run Detail" />
      <SectionContainer>
        {isLoading && <LinearProgress />}
        {run && (
          <>
            {/* Back link */}
            <Typography
              variant="body2"
              onClick={() => navigate(EXPERIMENTS_URL.EVAL_RUNS)}
              sx={{
                color: "secondary.main",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 0.5,
                mb: 2,
                "&:hover": { textDecoration: "underline" },
              }}
            >
              ← Back to Eval Runs
            </Typography>

            {/* Run name heading */}
            <Typography variant="h5" fontWeight={700} mb={2}>
              {displayName}
            </Typography>

            {/* Compact metadata card — two rows */}
            <Box
              sx={{
                mb: 3,
                p: 2,
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1.5,
                bgcolor: "background.paper",
              }}
            >
              {/* Row 1 */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap", mb: run.strategy || strategyValid || run.ranBy ? 1 : 0 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="body2" color="text.secondary">Agent:</Typography>
                  <Chip label={run.agentName || "—"} size="small" variant="outlined" sx={{ fontFamily: "monospace" }} />
                </Box>
                {run.strategy && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                    <Typography variant="body2" color="text.secondary">Strategy:</Typography>
                    <Typography variant="body2" fontWeight={600}>{run.strategy}</Typography>
                  </Box>
                )}
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Typography variant="body2" color="text.secondary">Cases:</Typography>
                  <Typography variant="body2" fontWeight={600}>{run.totalCases}</Typography>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Typography variant="body2" color="text.secondary">Passed:</Typography>
                  <Typography variant="body2" fontWeight={600} color="success.main">{run.passedCases}</Typography>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Typography variant="body2" color="text.secondary">Failed:</Typography>
                  <Typography variant="body2" fontWeight={600} color={run.totalCases - run.passedCases > 0 ? "error.main" : "text.secondary"}>
                    {run.totalCases - run.passedCases}
                  </Typography>
                </Box>
                {/* Pass rate bar inline */}
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, ml: "auto" }}>
                  <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={pct === 100 ? "success" : pct >= 50 ? "warning" : "error"}
                    sx={{ width: 80, height: 6, borderRadius: 3 }}
                  />
                  <Typography variant="body2" color="text.secondary">{pct}%</Typography>
                </Box>
              </Box>

              {/* Row 2 — optional fields */}
              {(strategyValid || run.ranBy || run.createdBy || run.timestamp) && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
                  {strategyValid && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      <Typography variant="body2" color="text.secondary">Strategy valid:</Typography>
                      <Typography variant="body2" fontWeight={600} color="success.main">{strategyValid}</Typography>
                    </Box>
                  )}
                  {run.ranBy && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      <Typography variant="body2" color="text.secondary">Ran by:</Typography>
                      <Typography variant="body2" fontFamily="monospace">{run.ranBy}</Typography>
                    </Box>
                  )}
                  {run.createdBy && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      <Typography variant="body2" color="text.secondary">Created by:</Typography>
                      <Typography variant="body2">{run.createdBy}</Typography>
                    </Box>
                  )}
                  {run.timestamp && (
                    <Typography variant="body2" color="text.secondary" sx={{ ml: "auto" }}>
                      {new Date(run.timestamp).toLocaleString()}
                    </Typography>
                  )}
                </Box>
              )}
            </Box>

            {/* Cases section */}
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1.5,
                bgcolor: "background.paper",
                overflow: "hidden",
              }}
            >
              <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2, py: 1.25, borderBottom: "1px solid", borderColor: "divider" }}>
                {run.cases?.length ?? 0} Cases
              </Typography>

              {(run.cases ?? []).map((c, i) => (
                <CaseAccordion key={c.id ?? i} evalCase={c} />
              ))}

              {!run.cases?.length && (
                <Typography color="text.secondary" sx={{ p: 2 }}>
                  No cases in this run.
                </Typography>
              )}
            </Box>
          </>
        )}
      </SectionContainer>
    </>
  );
}
