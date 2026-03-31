import { useState, useEffect, useMemo, useCallback } from "react";
import { useSearchParams } from "react-router";
import { usePushHistory } from "utils/hooks/usePushHistory";
import {
  Box,
  Breadcrumbs,
  Link,
  MenuItem,
  Select,
  SelectChangeEvent,
  Typography,
  CircularProgress,
  Alert,
} from "@mui/material";
import { AgentExecutionHeader } from "./AgentExecutionHeader";
import { AgentRunView } from "./AgentRunView";
import {
  computeMetrics,
  transformWorkflowExecutionToAgentRun,
  transformSubWorkflowToAgentRun,
} from "./agentExecutionUtils";
import {
  DEFAULT_MOCK_SCENARIO,
  MOCK_SCENARIOS,
  MockScenarioKey,
} from "./mockData";
import { AgentRunData, AgentStatus, NavigationEntry } from "./types";
import { WorkflowExecution } from "types/Execution";

interface AgentExecutionTabProps {
  execution?: WorkflowExecution;
}

async function fetchSubWorkflow(subWorkflowId: string): Promise<WorkflowExecution> {
  const res = await fetch(`/api/agent/executions/${subWorkflowId}/full`);
  if (!res.ok) throw new Error(`Failed to fetch sub-workflow ${subWorkflowId}`);
  return res.json();
}

/**
 * Detect wrapper workflows — thin shells created by the SDK around an actual agent
 * (e.g. engineering_lead_swarm_wf wraps engineering_lead_inner).
 * Heuristic: ≤5 tasks, one of which is a SUB_WORKFLOW named *_inner.
 */
function findInnerSubWorkflowId(execution: WorkflowExecution): string | null {
  const tasks = execution.tasks ?? [];
  if (tasks.length > 6) return null;
  const innerTask = tasks.find(
    (t) =>
      t.taskType === "SUB_WORKFLOW" &&
      t.referenceTaskName.includes("_inner"),
  );
  return (innerTask?.outputData?.subWorkflowId as string | undefined) ?? null;
}

export function AgentExecutionTab({ execution }: AgentExecutionTabProps) {
  // Only show scenario selector when no real execution is provided
  const [scenario, setScenario] = useState<MockScenarioKey>(DEFAULT_MOCK_SCENARIO);

  const { rootRun, transformError } = useMemo(() => {
    if (execution?.workflowId) {
      try {
        return { rootRun: transformWorkflowExecutionToAgentRun(execution), transformError: null };
      } catch (err) {
        const msg = err instanceof Error ? `${err.message}\n\n${err.stack ?? ""}` : String(err);
        console.error("[AgentExecution] Transform failed:", err);
        return {
          rootRun: {
            id: execution.workflowId,
            agentName: (execution as any).workflowName ?? execution.workflowType ?? "agent",
            turns: [],
            status: AgentStatus.FAILED,
            totalTokens: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
            totalDurationMs: 0,
          } as AgentRunData,
          transformError: msg,
        };
      }
    }
    return { rootRun: MOCK_SCENARIOS[scenario], transformError: null };
  }, [execution?.workflowId, execution?.tasks, scenario]);

  const [searchParams, setSearchParams] = useSearchParams();

  const [navStack, setNavStack] = useState<NavigationEntry[]>(() => [
    { agentRun: rootRun, selectedTurn: rootRun.turns[0]?.turnNumber ?? 1, label: rootRun.agentName },
  ]);

  // Reset nav stack when root run changes; restore from URL agentPath if present
  useEffect(() => {
    const root: NavigationEntry = { agentRun: rootRun, selectedTurn: rootRun.turns[0]?.turnNumber ?? 1, label: rootRun.agentName };
    setNavStack([root]);

    const pathStr = execution?.workflowId ? searchParams.get("agentPath") : null;
    if (!pathStr) return;
    const ids = pathStr.split(",").filter(Boolean);
    if (ids.length === 0) return;

    let cancelled = false;
    setDrillLoading(true);
    (async () => {
      try {
        const stack: NavigationEntry[] = [root];
        for (const id of ids) {
          let subExecution = await fetchSubWorkflow(id);
          const innerId = findInnerSubWorkflowId(subExecution);
          if (innerId) subExecution = await fetchSubWorkflow(innerId);
          const detailed = transformSubWorkflowToAgentRun(subExecution, subExecution.workflowType ?? id);
          stack.push({ agentRun: detailed, selectedTurn: detailed.turns[0]?.turnNumber ?? 1, label: detailed.agentName });
        }
        if (!cancelled) setNavStack(stack);
      } catch {
        // Stay at root if restoration fails; clear stale URL param
        if (!cancelled) setSearchParams(p => { p.delete("agentPath"); return p; }, { replace: true });
      } finally {
        if (!cancelled) setDrillLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [rootRun]); // eslint-disable-line react-hooks/exhaustive-deps

  const [drillLoading, setDrillLoading] = useState(false);

  // Helper: recompute agentPath from a nav stack (positions 1+ have workflow IDs)
  const stackToPath = (stack: NavigationEntry[]) =>
    stack.slice(1).map(e => e.agentRun.id).filter(Boolean).join(",");

  const onDrillIn = useCallback(async (sub: AgentRunData) => {
    if (sub.subWorkflowId && !sub.model) {
      setDrillLoading(true);
      try {
        let subExecution = await fetchSubWorkflow(sub.subWorkflowId);
        const innerId = findInnerSubWorkflowId(subExecution);
        if (innerId) subExecution = await fetchSubWorkflow(innerId);
        const detailed = transformSubWorkflowToAgentRun(subExecution, sub.agentName);
        setNavStack(prev => {
          const next = [...prev, { agentRun: detailed, selectedTurn: detailed.turns[0]?.turnNumber ?? 1, label: detailed.agentName }];
          setSearchParams(p => { p.set("agentPath", stackToPath(next)); return p; }, { replace: false });
          return next;
        });
      } catch {
        setNavStack(prev => {
          const next = [...prev, { agentRun: sub, selectedTurn: sub.turns[0]?.turnNumber ?? 1, label: sub.agentName }];
          setSearchParams(p => { p.set("agentPath", stackToPath(next)); return p; }, { replace: false });
          return next;
        });
      } finally {
        setDrillLoading(false);
      }
    } else {
      setNavStack(prev => {
        const next = [...prev, { agentRun: sub, selectedTurn: sub.turns[0]?.turnNumber ?? 1, label: sub.agentName }];
        setSearchParams(p => { p.set("agentPath", stackToPath(next)); return p; }, { replace: false });
        return next;
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onBreadcrumbClick = useCallback((index: number) => {
    setNavStack(prev => {
      const next = prev.slice(0, index + 1);
      const path = stackToPath(next);
      if (path) {
        setSearchParams(p => { p.set("agentPath", path); return p; }, { replace: false });
      } else {
        setSearchParams(p => { p.delete("agentPath"); return p; }, { replace: false });
      }
      return next;
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const navigate = usePushHistory();

  const currentEntry = navStack[navStack.length - 1];
  const metrics = computeMetrics(rootRun);
  const isUsingMockData = !execution?.workflowId;

  // When drilling in-page, the back button pops the stack.
  // When at root and the execution has a parent workflow (direct URL open of a sub-workflow),
  // the back button navigates to the parent execution page.
  const onBack =
    navStack.length > 1
      ? () => onBreadcrumbClick(navStack.length - 2)
      : execution?.parentWorkflowId
        ? () => navigate(`/execution/${execution.parentWorkflowId}`)
        : undefined;

  const handleScenarioChange = (event: SelectChangeEvent<MockScenarioKey>) => {
    setScenario(event.target.value as MockScenarioKey);
  };

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {transformError && (
        <Alert severity="error" sx={{ mx: 2, mt: 1, flexShrink: 0, fontSize: "0.75rem" }}>
          <strong>Failed to parse execution data.</strong> Check the browser console for details.
          <Box component="pre" sx={{ mt: 0.5, fontSize: "0.7rem", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 120, overflowY: "auto" }}>
            {transformError}
          </Box>
        </Alert>
      )}
      {/* Header row: metrics + scenario selector (mock only) */}
      <Box sx={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <AgentExecutionHeader metrics={metrics} rootRun={rootRun} />
        </Box>
        {isUsingMockData && (
          <Box sx={{ px: 1.5, py: 1, flexShrink: 0 }}>
            <Select<MockScenarioKey>
              value={scenario}
              onChange={handleScenarioChange}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.75rem", "& .MuiSelect-select": { py: 0.5, px: 1 } }}
            >
              {(Object.keys(MOCK_SCENARIOS) as MockScenarioKey[]).map((key) => (
                <MenuItem key={key} value={key} sx={{ fontSize: "0.75rem" }}>
                  {key}
                </MenuItem>
              ))}
            </Select>
          </Box>
        )}
      </Box>

      {/* Breadcrumb — only visible when drilling in */}
      {navStack.length > 1 && (
        <Box
          sx={{
            px: 2,
            py: 0.75,
            borderBottom: "1px solid",
            borderColor: "divider",
            flexShrink: 0,
            backgroundColor: "grey.50",
          }}
        >
          <Breadcrumbs separator=">" aria-label="agent navigation breadcrumb">
            {navStack.map((entry, index) => {
              const isLast = index === navStack.length - 1;
              return isLast ? (
                <Typography
                  key={entry.agentRun.id}
                  variant="caption"
                  fontWeight={600}
                  sx={{ fontFamily: "monospace" }}
                >
                  {entry.label}
                </Typography>
              ) : (
                <Link
                  key={entry.agentRun.id}
                  component="button"
                  variant="caption"
                  underline="hover"
                  onClick={() => onBreadcrumbClick(index)}
                  sx={{ fontFamily: "monospace", cursor: "pointer", color: "primary.main" }}
                >
                  {entry.label}
                </Link>
              );
            })}
          </Breadcrumbs>
        </Box>
      )}

      {/* Main content */}
      <Box sx={{
        flex: 1, overflow: "hidden", minHeight: 0, position: "relative",
      }}>
        {drillLoading && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 10, backgroundColor: "rgba(255,255,255,0.7)" }}>
            <CircularProgress size={32} />
          </Box>
        )}
        <AgentRunView
          agentRun={currentEntry.agentRun}
          onDrillIn={onDrillIn}
          onBack={onBack}
          isRoot={navStack.length === 1}
        />
      </Box>
    </Box>
  );
}

export default AgentExecutionTab;
