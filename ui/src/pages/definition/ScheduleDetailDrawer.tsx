import {
  Box,
  CircularProgress,
  Divider,
  Drawer,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  ArrowSquareOut as ExternalLinkIcon,
  Lightning as RunNowIcon,
  PauseCircle as PauseIcon,
  Trash as DeleteIcon,
  X as CloseIcon,
} from "@phosphor-icons/react";
import { Button, IconButton, NavLink } from "components";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import { SnackbarMessage } from "components/SnackbarMessage";
import cronstrue from "cronstrue";
import PlayIcon from "components/v1/icons/PlayIcon";
import { useCallback, useState } from "react";
import { SCHEDULER_DEFINITION_URL, SCHEDULER_EXECUTION_URL } from "utils/constants/route";
import { useActionWithPath, useFetch } from "utils/query";
import { useSchedule } from "pages/scheduler/schedulerHooks";

type Toast = { message: string; severity: "success" | "error" | "warning" };

interface ScheduleDetailDrawerProps {
  scheduleName: string | null;
  agentName: string;
  onClose: () => void;
  onMutated: () => void;
}

function formatEpoch(epoch: number | undefined | null): string {
  if (!epoch) return "—";
  return new Date(epoch).toLocaleString();
}

export default function ScheduleDetailDrawer({
  scheduleName,
  agentName,
  onClose,
  onMutated,
}: ScheduleDetailDrawerProps) {
  const [tab, setTab] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  const { data: schedule, isLoading } = useSchedule(scheduleName ?? undefined);

  const { data: execData, isFetching: execLoading } = useFetch<any>(
    scheduleName
      ? `/scheduler/search/executions?scheduleName=${encodeURIComponent(scheduleName)}&size=15`
      : "",
    { enabled: !!scheduleName && tab === 0 },
  );
  const executions: any[] = execData?.results ?? execData ?? [];

  const pauseAction = useActionWithPath({
    onSuccess: () => { onMutated(); },
    onError: () => setToast({ message: "Action failed", severity: "error" }),
  });

  const deleteAction = useActionWithPath({
    onSuccess: () => { onMutated(); onClose(); },
    onError: () => setToast({ message: "Delete failed", severity: "error" }),
  });

  const runNowAction = useActionWithPath({
    onSuccess: () => setToast({ message: "Execution started", severity: "success" }),
    onError: () => setToast({ message: "Failed to start execution", severity: "error" }),
  });

  const handlePause = useCallback(() => {
    if (!scheduleName) return;
    // @ts-ignore
    pauseAction.mutate({ method: "get", path: `/scheduler/schedules/${scheduleName}/pause` });
    setToast({ message: `Paused`, severity: "warning" });
  }, [scheduleName, pauseAction]);

  const handleResume = useCallback(() => {
    if (!scheduleName) return;
    // @ts-ignore
    pauseAction.mutate({ method: "get", path: `/scheduler/schedules/${scheduleName}/resume` });
    setToast({ message: `Resumed`, severity: "success" });
  }, [scheduleName, pauseAction]);

  const handleRunNow = useCallback(() => {
    if (!scheduleName) return;
    const input = schedule?.startWorkflowRequest?.input ?? {};
    // @ts-ignore
    runNowAction.mutate({
      method: "post",
      path: `/workflow/${agentName}`,
      body: JSON.stringify(input),
    });
  }, [scheduleName, schedule, agentName, runNowAction]);

  const handleDeleteConfirm = (confirmed: boolean) => {
    setDeleteConfirm(false);
    if (confirmed && scheduleName) {
      // @ts-ignore
      deleteAction.mutate({ method: "delete", path: `/scheduler/schedules/${scheduleName}` });
    }
  };

  const isActive = schedule ? !schedule.paused : false;

  return (
    <Drawer
      anchor="right"
      open={!!scheduleName}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 520 }, display: "flex", flexDirection: "column" } }}
    >
      {toast && (
        <SnackbarMessage
          autoHideDuration={3000}
          message={toast.message}
          severity={toast.severity}
          onDismiss={() => setToast(null)}
        />
      )}

      {deleteConfirm && scheduleName && (
        <ConfirmChoiceDialog
          handleConfirmationValue={handleDeleteConfirm}
          message={
            <>
              Delete schedule <strong style={{ color: "red" }}>{scheduleName}</strong>? This cannot be undone.
              <div style={{ marginTop: 15 }}>Type <strong>{scheduleName}</strong> to confirm.</div>
            </>
          }
          header="Delete confirmation"
          isInputConfirmation
          valueToBeDeleted={scheduleName}
        />
      )}

      {/* Header */}
      <Box sx={{ px: 3, pt: 2.5, pb: 1.5, display: "flex", alignItems: "flex-start", gap: 1, borderBottom: "1px solid rgba(0,0,0,.1)" }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle1" fontWeight={600} noWrap>
            {scheduleName ?? ""}
          </Typography>
          {schedule && (
            <Typography variant="caption" color="text.secondary">
              {schedule.cronExpression
                ? cronstrue.toString(schedule.cronExpression, { throwExceptionOnParseError: false })
                : ""}
              {schedule.zoneId ? ` · ${schedule.zoneId}` : ""}
              {" · "}
              <span style={{ color: isActive ? "#4caf50" : "#9e9e9e" }}>
                {isActive ? "Active" : "Paused"}
              </span>
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0, alignItems: "center" }}>
          {isActive ? (
            <Tooltip title="Pause">
              <IconButton size="small" onClick={handlePause}>
                <PauseIcon size={18} />
              </IconButton>
            </Tooltip>
          ) : (
            <Tooltip title="Resume">
              <IconButton size="small" onClick={handleResume}>
                <PlayIcon size={18} />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Run now">
            <IconButton size="small" onClick={handleRunNow}>
              <RunNowIcon size={18} />
            </IconButton>
          </Tooltip>
          {scheduleName && (
            <Tooltip title="Open full editor">
              <NavLink path={`${SCHEDULER_DEFINITION_URL.BASE}/${scheduleName}`}>
                <IconButton size="small">
                  <ExternalLinkIcon size={18} />
                </IconButton>
              </NavLink>
            </Tooltip>
          )}
          <Tooltip title="Delete">
            <IconButton size="small" onClick={() => setDeleteConfirm(true)}>
              <DeleteIcon size={18} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Close">
            <IconButton size="small" onClick={onClose}>
              <CloseIcon size={18} />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: "1px solid rgba(0,0,0,.08)", flexShrink: 0 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{ minHeight: 38, "& .MuiTab-root": { minHeight: 38, fontSize: "0.8rem", textTransform: "none" } }}
        >
          <Tab label="Executions" />
          <Tab label="Definition" />
        </Tabs>
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", pt: 4 }}>
            <CircularProgress size={24} />
          </Box>
        )}

        {/* Executions tab */}
        {tab === 0 && !isLoading && (
          <Box sx={{ p: 2 }}>
            {scheduleName && (
              <Box sx={{ mb: 1.5 }}>
                <NavLink path={`${SCHEDULER_EXECUTION_URL}?scheduleName=${encodeURIComponent(scheduleName)}`}>
                  <Button variant="text" size="small" endIcon={<ExternalLinkIcon size={14} />}>
                    View all in Scheduler Executions
                  </Button>
                </NavLink>
              </Box>
            )}
            {execLoading && <CircularProgress size={18} />}
            {!execLoading && executions.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                No executions recorded yet.
              </Typography>
            )}
            {executions.map((exec: any, i: number) => (
              <Box
                key={exec.executionId ?? exec.workflowId ?? i}
                sx={{ py: 1, borderBottom: "1px solid rgba(0,0,0,.06)", "&:last-child": { borderBottom: "none" } }}
              >
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Typography variant="caption" fontFamily="monospace">
                    {exec.workflowId ?? exec.executionId ?? "—"}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: exec.status === "COMPLETED" ? "#4caf50" : exec.status === "FAILED" ? "#f44336" : "text.secondary" }}
                  >
                    {exec.status ?? "—"}
                  </Typography>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {exec.startTime ? formatEpoch(exec.startTime) : ""}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        {/* Definition tab */}
        {tab === 1 && !isLoading && schedule && (
          <Box sx={{ p: 2 }}>
            <Box
              component="pre"
              sx={{
                m: 0,
                p: 2,
                borderRadius: 1,
                bgcolor: "rgba(0,0,0,.04)",
                fontSize: "0.75rem",
                fontFamily: "monospace",
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {JSON.stringify(schedule, null, 2)}
            </Box>
          </Box>
        )}
      </Box>
    </Drawer>
  );
}
