import {
  Box,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  ArrowClockwise as RefreshIcon,
  Lightning as RunNowIcon,
  PauseCircle as PauseIcon,
  Trash as DeleteIcon,
} from "@phosphor-icons/react";
import { Button, IconButton } from "components";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import { SnackbarMessage } from "components/SnackbarMessage";
import cronstrue from "cronstrue";
import AddIcon from "components/v1/icons/AddIcon";
import PlayIcon from "components/v1/icons/PlayIcon";
import { useCallback, useMemo, useState } from "react";
import { IScheduleDto } from "types/Schedulers";
import { SCHEDULER_DEFINITION_URL } from "utils/constants/route";
import { useGetSchedulerDefinitionsWithPagination } from "utils/hooks/useGetSchedulerDefinitions";
import { usePushHistory } from "utils/hooks/usePushHistory";
import { useActionWithPath } from "utils/query";
import ScheduleDetailDrawer from "./ScheduleDetailDrawer";

function formatEpoch(epoch: number | undefined): string {
  if (!epoch) return "—";
  return new Date(epoch).toLocaleString();
}

function StatusGlyph({ active }: { active: boolean }) {
  return (
    <Tooltip title={active ? "Active" : "Paused"}>
      <span style={{ fontSize: 16, color: active ? "#4caf50" : "#9e9e9e", lineHeight: 1 }}>
        {active ? "●" : "◐"}
      </span>
    </Tooltip>
  );
}

interface AgentSchedulesTabProps {
  agentName: string;
}

type Toast = { message: string; severity: "success" | "error" | "warning" };

export default function AgentSchedulesTab({ agentName }: AgentSchedulesTabProps) {
  const pushHistory = usePushHistory();
  const [toast, setToast] = useState<Toast | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [pauseTarget, setPauseTarget] = useState<string | null>(null);
  const [pauseReason, setPauseReason] = useState("");
  const [drawerSchedule, setDrawerSchedule] = useState<string | null>(null);

  const searchParams = useMemo(
    () => ({ workflowName: agentName, size: 100 }),
    [agentName],
  );

  const { data, isFetching, refetch } = useGetSchedulerDefinitionsWithPagination(searchParams);

  const schedules = useMemo(
    () => (data?.results ?? []).map((s) => ({ ...s, active: !s.paused })),
    [data],
  );

  const pauseAction = useActionWithPath({
    onSuccess: () => refetch(),
    onError: () => setToast({ message: "Action failed", severity: "error" }),
  });

  const deleteAction = useActionWithPath({
    onSuccess: () => {
      refetch();
      setToast({ message: "Schedule deleted", severity: "success" });
    },
    onError: () => setToast({ message: "Delete failed", severity: "error" }),
  });

  const runNowAction = useActionWithPath({
    onSuccess: () => setToast({ message: "Execution started", severity: "success" }),
    onError: () => setToast({ message: "Failed to start execution", severity: "error" }),
  });

  const handlePauseConfirm = useCallback(() => {
    if (!pauseTarget) return;
    const reasonParam = pauseReason.trim()
      ? `?reason=${encodeURIComponent(pauseReason.trim())}`
      : "";
    // @ts-ignore
    pauseAction.mutate({ method: "get", path: `/scheduler/schedules/${pauseTarget}/pause${reasonParam}` });
    setToast({ message: `${pauseTarget} paused`, severity: "warning" });
    setPauseTarget(null);
    setPauseReason("");
  }, [pauseTarget, pauseReason, pauseAction]);

  const handleResume = useCallback(
    (name: string) => {
      // @ts-ignore
      pauseAction.mutate({ method: "get", path: `/scheduler/schedules/${name}/resume` });
      setToast({ message: `${name} resumed`, severity: "success" });
    },
    [pauseAction],
  );

  const handleRunNow = useCallback(
    (schedule: IScheduleDto) => {
      const input = schedule.startWorkflowRequest?.input ?? {};
      // @ts-ignore
      runNowAction.mutate({
        method: "post",
        path: `/workflow/${agentName}`,
        body: JSON.stringify(input),
      });
    },
    [runNowAction, agentName],
  );

  const handleDeleteConfirm = (confirmed: boolean) => {
    if (confirmed && deleteTarget) {
      // @ts-ignore
      deleteAction.mutate({ method: "delete", path: `/scheduler/schedules/${deleteTarget}` });
    }
    setDeleteTarget(null);
  };

  const handleNewSchedule = () => {
    pushHistory(`${SCHEDULER_DEFINITION_URL.NEW}?workflowName=${encodeURIComponent(agentName)}`);
  };

  return (
    <Box sx={{ p: 3, height: "100%", overflowY: "auto" }}>
      {toast && (
        <SnackbarMessage
          autoHideDuration={3000}
          message={toast.message}
          severity={toast.severity}
          onDismiss={() => setToast(null)}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmChoiceDialog
          handleConfirmationValue={handleDeleteConfirm}
          message={
            <>
              Delete schedule{" "}
              <strong style={{ color: "red" }}>{deleteTarget}</strong>? This cannot be undone.
              <div style={{ marginTop: 15 }}>
                Type <strong>{deleteTarget}</strong> to confirm.
              </div>
            </>
          }
          header="Delete confirmation"
          isInputConfirmation
          valueToBeDeleted={deleteTarget}
        />
      )}

      {/* Pause-with-reason dialog */}
      <Dialog
        open={!!pauseTarget}
        onClose={() => { setPauseTarget(null); setPauseReason(""); }}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Pause schedule</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Pause <strong>{pauseTarget}</strong>?
          </Typography>
          <TextField
            label="Reason (optional)"
            value={pauseReason}
            onChange={(e) => setPauseReason(e.target.value)}
            fullWidth
            size="small"
            placeholder="e.g. rate limit cooldown"
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") handlePauseConfirm(); }}
          />
        </DialogContent>
        <DialogActions>
          <Button variant="text" onClick={() => { setPauseTarget(null); setPauseReason(""); }}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handlePauseConfirm}>
            Pause
          </Button>
        </DialogActions>
      </Dialog>

      {/* Schedule detail drawer */}
      <ScheduleDetailDrawer
        scheduleName={drawerSchedule}
        agentName={agentName}
        onClose={() => setDrawerSchedule(null)}
        onMutated={refetch}
      />

      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 2,
        }}
      >
        <Typography variant="subtitle1" fontWeight={500}>
          Schedules
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => refetch()}>
              <RefreshIcon size={18} />
            </IconButton>
          </Tooltip>
          <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={handleNewSchedule}>
            New schedule
          </Button>
        </Box>
      </Box>

      {isFetching && <CircularProgress size={20} />}

      {!isFetching && schedules.length === 0 && (
        <Typography color="text.secondary" variant="body2">
          No schedules for this agent.{" "}
          <span
            style={{ cursor: "pointer", textDecoration: "underline" }}
            onClick={handleNewSchedule}
          >
            Create one
          </span>
        </Typography>
      )}

      {schedules.map((schedule) => (
        <Box
          key={schedule.name}
          sx={{
            display: "flex",
            alignItems: "flex-start",
            gap: 2,
            py: 1.5,
            borderBottom: "1px solid rgba(0,0,0,.08)",
            "&:last-child": { borderBottom: "none" },
          }}
        >
          <Box sx={{ mt: 0.4, flexShrink: 0 }}>
            <StatusGlyph active={!!schedule.active} />
          </Box>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
              {/* Click name to open detail drawer */}
              <Typography
                variant="body2"
                fontWeight={500}
                sx={{ cursor: "pointer", color: "primary.main", "&:hover": { textDecoration: "underline" } }}
                onClick={() => setDrawerSchedule(schedule.name)}
              >
                {schedule.name}
              </Typography>
              <Tooltip title={schedule.cronExpression ?? ""}>
                <Typography variant="body2" color="text.secondary">
                  {schedule.cronExpression
                    ? cronstrue.toString(schedule.cronExpression, {
                        throwExceptionOnParseError: false,
                      })
                    : ""}
                </Typography>
              </Tooltip>
              {schedule.paused && schedule.pausedReason && (
                <Chip
                  label={`Paused: ${schedule.pausedReason}`}
                  size="small"
                  color="warning"
                  variant="outlined"
                />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary">
              Next: {formatEpoch(schedule.nextRunTime)} · Last:{" "}
              {formatEpoch(schedule.lastRunTimeInEpoch)}
            </Typography>
          </Box>

          <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
            {schedule.active ? (
              <Tooltip title="Pause">
                <IconButton size="small" onClick={() => { setPauseTarget(schedule.name); setPauseReason(""); }}>
                  <PauseIcon size={18} />
                </IconButton>
              </Tooltip>
            ) : (
              <Tooltip title="Resume">
                <IconButton size="small" onClick={() => handleResume(schedule.name)}>
                  <PlayIcon size={18} />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title="Run now">
              <IconButton size="small" onClick={() => handleRunNow(schedule)}>
                <RunNowIcon size={18} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" onClick={() => setDeleteTarget(schedule.name)}>
                <DeleteIcon size={18} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      ))}
    </Box>
  );
}
