import { Box, Chip, Tooltip } from "@mui/material";
import {
  CopySimple as CopyIcon,
  Trash as DeleteIcon,
  ArrowClockwise as RefreshIcon,
} from "@phosphor-icons/react";
import { Button, DataTable, IconButton, NavLink, Paper } from "components";
import { FilterObjectItem } from "components/DataTable/state";
import { ColumnCustomType, LegacyColumn } from "components/DataTable/types";
import Header from "components/Header";
import NoDataComponent from "components/NoDataComponent";
import { SnackbarMessage } from "components/SnackbarMessage";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import PlayIcon from "components/v1/icons/PlayIcon";
import { MessageContext } from "components/v1/layout/MessageContext";
import { removeDeletedWorkflow } from "pages/runWorkflow/runWorkflowUtils";
import { useCallback, useContext, useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { useAuth } from "shared/auth";
import { colors } from "theme/tokens/variables";
import { PopoverMessage } from "types/Messages";
import { AgentSummary } from "types/AgentSummary";
import {
  RUN_AGENT_URL,
  AGENT_DEFINITION_URL,
} from "utils/constants/route";
import useCustomPagination from "utils/hooks/useCustomPagination";
import { usePushHistory } from "utils/hooks/usePushHistory";
import { logger } from "utils/logger";
import { useActionWithPath, useAgentList } from "utils/query";
import { tryToJson } from "utils/utils";
import CloneAgentDialog from "./dialog/CloneAgentDialog";

// External provider types that cannot be cloned (they live in Azure/AWS, not as workflow defs).
const EXTERNAL_TYPES = new Set(["azure-foundry", "bedrock", "bedrock-agentcore"]);

function providerLabel(type?: string | null): string {
  switch (type) {
    case "azure-foundry":
      return "Azure Foundry";
    case "bedrock":
      return "Bedrock";
    case "bedrock-agentcore":
      return "Bedrock AgentCore";
    default:
      return "Conductor";
  }
}

// Chip color per provider — maps to MUI Chip color prop.
function providerChipColor(
  type?: string | null,
): "primary" | "warning" | "default" {
  switch (type) {
    case "azure-foundry":
      return "primary"; // blue
    case "bedrock":
    case "bedrock-agentcore":
      return "warning"; // amber
    default:
      return "default";
  }
}

export default function AgentDefinitions() {
  const { isTrialExpired } = useAuth();

  const { data, isFetching, refetch } = useAgentList();

  const [selectedWorkflowWithAction, setSelectedWorkflowWithAction] = useState<{
    selectedWorkflow: AgentSummary | null;
    action: string;
  }>({
    selectedWorkflow: null,
    action: "",
  });
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);

  const { setMessage } = useContext(MessageContext);
  const pushHistory = usePushHistory();
  const [
    { filterParam, pageParam, searchParam },
    { setFilterParam, setSearchParam, handlePageChange },
  ] = useCustomPagination();
  const [confirmDelete, setConfirmDelete] = useState<{
    confirmDelete: boolean;
    agentName: string;
    agentVersion: number;
  } | null>(null);
  const filterObj =
    filterParam === "" ? undefined : tryToJson<FilterObjectItem>(filterParam);

  const deleteAgentAction = useActionWithPath({
    onSuccess: () => {
      if (confirmDelete?.agentName) {
        removeDeletedWorkflow(
          encodeURIComponent(confirmDelete.agentName),
          confirmDelete.agentVersion,
        );
      }
      refetch();
    },
    onError: (err: Error) => {
      setMessage({ severity: "error", text: "Failed to delete agent" });
      logger.error(err);
      refetch();
    },
  });

  // Unique provider types present in the current data, sorted.
  const providerTypes = useMemo<string[]>(() => {
    if (!data) return [];
    const types = new Set<string>();
    data.forEach((a) => types.add(a.type ?? "conductor"));
    return [...types].sort();
  }, [data]);

  // Agents filtered to the selected provider chip.
  const filteredAgents = useMemo<AgentSummary[]>(() => {
    if (!data) return [];
    if (selectedType === null) return data;
    return data.filter((a) =>
      selectedType === "conductor"
        ? !a.type || !EXTERNAL_TYPES.has(a.type)
        : a.type === selectedType,
    );
  }, [data, selectedType]);

  const columns = useMemo<LegacyColumn[]>(
    () => [
      {
        id: "workflow_name",
        name: "name",
        label: "Agent name",
        renderer: (name: string, row: AgentSummary) => (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <NavLink
              data-cy="workflow-link"
              path={`${AGENT_DEFINITION_URL.BASE}/${encodeURIComponent(name.trim())}`}
              id={`${name.trim()}-link-btn`}
            >
              {name.trim()}
            </NavLink>
            {row.type && (
              <Chip
                label={providerLabel(row.type)}
                color={providerChipColor(row.type)}
                size="small"
                variant="outlined"
                sx={{ fontSize: 10, height: 18, px: 0.25 }}
              />
            )}
          </Box>
        ),
        tooltip: "The name of the agent",
      },
      {
        id: "workflow_description",
        name: "description",
        label: "Description",
        grow: 2,
        tooltip: "The description of the agent",
      },
      {
        id: "create_time",
        name: "createTime",
        label: "Created time",
        type: ColumnCustomType.DATE,
        tooltip: "The time the agent was created",
      },
      {
        id: "latest_version",
        name: "version",
        label: "Latest version",
        grow: 0.5,
        tooltip: "The latest version of the agent",
      },
      {
        id: "schema_version",
        name: "schemaVersion",
        label: "Schema version",
        grow: 0.5,
        tooltip: "The schema version of the agent",
      },
      {
        id: "restartable",
        name: "restartable",
        label: "Restartable",
        grow: 0.5,
        tooltip: "Whether the agent is restartable",
      },
      {
        id: "status_listener_enabled",
        name: "workflowStatusListenerEnabled",
        label: "Status listener enabled",
        grow: 0.5,
        tooltip: "Whether the status listener is enabled",
      },
      {
        id: "owner_email",
        name: "ownerEmail",
        label: "Owner email",
        tooltip: "The email of the owner of the agent",
      },
      {
        id: "input_params",
        name: "inputParameters",
        label: "Input params",
        type: ColumnCustomType.JSON,
        sortable: false,
        tooltip: "The input parameters of the agent",
      },
      {
        id: "output_params",
        name: "outputParameters",
        label: "Output params",
        type: ColumnCustomType.JSON,
        sortable: false,
        tooltip: "The output parameters of the agent",
      },
      {
        id: "timeout_policy",
        name: "timeoutPolicy",
        label: "Timeout policy",
        grow: 0.5,
        tooltip: "The timeout policy of the agent",
      },
      {
        id: "timeout_seconds",
        name: "timeoutSeconds",
        label: "Timeout seconds",
        grow: 0.5,
        tooltip: "The timeout seconds of the agent",
      },
      {
        id: "failure_workflow",
        name: "failureWorkflow",
        label: "Failure agent",
        grow: 1,
        tooltip: "The agent to run on failure",
      },
      {
        id: "executions_link",
        name: "name",
        label: "Executions",
        sortable: false,
        searchable: false,
        grow: 0.5,
        renderer: (name: string) => (
          <NavLink
            path={`/executions?workflowType=${encodeURIComponent(name.trim())}`}
            newTab
          >
            Query
          </NavLink>
        ),
        tooltip: "The executions of the agent",
      },
      {
        id: "actions",
        name: "name",
        label: "Actions",
        sortable: false,
        searchable: false,
        grow: 0.5,
        minWidth: "140px",
        tooltip: "Actions you can perform on the agent",
        renderer: (name: string, row: AgentSummary) => {
          const isExternal = row.type && EXTERNAL_TYPES.has(row.type);
          return (
            <Box style={{ display: "flex", justifyContent: "flex-start", gap: 4 }}>
              {!isExternal && (
                <Tooltip title="Clone agent">
                  <IconButton
                    onClick={() =>
                      setSelectedWorkflowWithAction({
                        selectedWorkflow: row,
                        action: "clone",
                      })
                    }
                    disabled={isTrialExpired}
                    size="small"
                  >
                    <CopyIcon size={20} />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title="Delete agent">
                <IconButton
                  id={`delete-${name}-btn`}
                  disabled={isTrialExpired}
                  onClick={() => {
                    const selected = data?.find((x) => x.name === name);
                    if (selected) {
                      setConfirmDelete({
                        confirmDelete: true,
                        agentName: selected.name,
                        agentVersion: selected.version,
                      });
                    }
                  }}
                  size="small"
                >
                  <DeleteIcon size={20} />
                </IconButton>
              </Tooltip>
            </Box>
          );
        },
      },
    ],
    [data, isTrialExpired],
  );

  const handleFilterChange = useCallback(
    (obj?: FilterObjectItem) => {
      setFilterParam(obj ? JSON.stringify(obj) : "");
    },
    [setFilterParam],
  );

  // Count agents per type for chip labels.
  const countForType = useCallback(
    (type: string) => {
      if (!data) return 0;
      return type === "conductor"
        ? data.filter((a) => !a.type || !EXTERNAL_TYPES.has(a.type)).length
        : data.filter((a) => a.type === type).length;
    },
    [data],
  );

  return (
    <>
      <Helmet>
        <title>Agent Definitions</title>
      </Helmet>

      {selectedWorkflowWithAction.selectedWorkflow &&
        selectedWorkflowWithAction.action === "clone" && (
          <CloneAgentDialog
            onClose={() =>
              setSelectedWorkflowWithAction({ selectedWorkflow: null, action: "" })
            }
            onSuccess={() => {
              setSelectedWorkflowWithAction({ selectedWorkflow: null, action: "" });
              refetch();
              setToastMessage({
                text: "Agent cloned successfully",
                severity: "success",
              });
            }}
            selectedWorkflow={selectedWorkflowWithAction.selectedWorkflow}
            workflowList={data ?? []}
          />
        )}

      {confirmDelete && (
        <ConfirmChoiceDialog
          handleConfirmationValue={(confirmed) => {
            if (confirmed) {
              // @ts-ignore
              deleteAgentAction.mutate({
                method: "delete",
                path: `/agent/${encodeURIComponent(confirmDelete.agentName)}?version=${confirmDelete.agentVersion}`,
              });
            }
            setConfirmDelete(null);
          }}
          message={
            <>
              Are you sure you want to delete{" "}
              <strong style={{ color: "red" }}>{confirmDelete.agentName}</strong>{" "}
              agent definition? This cannot be undone.
              <div style={{ marginTop: "15px" }}>
                Please type <strong>{confirmDelete.agentName}</strong> to confirm.
              </div>
            </>
          }
          header="Deletion confirmation"
          isInputConfirmation
          valueToBeDeleted={confirmDelete.agentName}
        />
      )}

      <SectionHeader
        _deprecate_marginTop={0}
        title="Agent Definitions"
        actions={
          <SectionHeaderActions
            buttons={[
              {
                label: "Run agent",
                color: "secondary",
                onClick: () => pushHistory(RUN_AGENT_URL),
                startIcon: <PlayIcon />,
              },
            ]}
          />
        }
      />

      <SectionContainer>
        {/* Provider filter chips */}
        {providerTypes.length > 1 && (
          <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
            <Chip
              label={`All (${data?.length ?? 0})`}
              onClick={() => setSelectedType(null)}
              color={selectedType === null ? "primary" : "default"}
              variant={selectedType === null ? "filled" : "outlined"}
              clickable
            />
            {providerTypes.map((type) => (
              <Chip
                key={type}
                label={`${providerLabel(type)} (${countForType(type)})`}
                onClick={() =>
                  setSelectedType(selectedType === type ? null : type)
                }
                color={
                  selectedType === type ? providerChipColor(type) : "default"
                }
                variant={selectedType === type ? "filled" : "outlined"}
                clickable
              />
            ))}
          </Box>
        )}

        <Paper id="workflow-definitions-table-wrapper" variant="outlined">
          <Header loading={isFetching} />
          {filteredAgents && (
            <DataTable
              localStorageKey="workflowsTable"
              quickSearchEnabled
              quickSearchPlaceholder="Search agent definitions"
              searchTerm={searchParam}
              onSearchTermChange={setSearchParam}
              defaultShowColumns={[
                "workflow_name",
                "workflow_description",
                "latest_version",
                "create_time",
                "owner_email",
                "executions_link",
                "actions",
              ]}
              keyField="name"
              onFilterChange={handleFilterChange}
              initialFilterObj={filterObj}
              data={filteredAgents}
              columns={columns}
              customActions={[
                <Tooltip title="Refresh agent definitions" key="rfrshWdefs">
                  <Button
                    variant="text"
                    color="inherit"
                    size="small"
                    startIcon={<RefreshIcon />}
                    onClick={refetch as () => void}
                  >
                    Refresh
                  </Button>
                </Tooltip>,
              ]}
              onChangePage={handlePageChange}
              paginationDefaultPage={pageParam ? Number(pageParam) : 1}
              noDataComponent={
                searchParam === "" && selectedType === null ? (
                  <NoDataComponent
                    title="Agent Definition"
                    description="No agents deployed yet. Use the CLI to deploy agents."
                  />
                ) : (
                  <NoDataComponent
                    title="Empty"
                    titleBg={colors.warningTag}
                    description="No agents match the current filters."
                    buttonText="Clear filters"
                    buttonHandler={() => {
                      setSearchParam("");
                      setSelectedType(null);
                    }}
                  />
                )
              }
            />
          )}
        </Paper>
      </SectionContainer>

      {toastMessage && (
        <SnackbarMessage
          autoHideDuration={3000}
          id="workflow-definitions-toast-message"
          message={toastMessage.text}
          severity={toastMessage.severity}
          onDismiss={() => setToastMessage(null)}
        />
      )}
    </>
  );
}
