import { Box, Tooltip } from "@mui/material";
import {
  CopySimple as CopyIcon,
  Trash as DeleteIcon,
  ArrowClockwise as RefreshIcon,
  Tag as TagIcon,
} from "@phosphor-icons/react";
import { Button, DataTable, IconButton, NavLink, Paper } from "components";
import { FilterObjectItem } from "components/DataTable/state";
import { ColumnCustomType, LegacyColumn } from "components/DataTable/types";
import Header from "components/Header";
import NoDataComponent from "components/NoDataComponent";
import { SnackbarMessage } from "components/SnackbarMessage";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import AddTagDialog, { TagDialogProps } from "components/tags/AddTagDialog";
import TagList from "components/v1/TagList";
import PlayIcon from "components/v1/icons/PlayIcon";
import { MessageContext } from "components/v1/layout/MessageContext";
import { removeDeletedWorkflow } from "pages/runWorkflow/runWorkflowUtils";
import { useCallback, useContext, useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import { UseQueryResult } from "react-query";
import { useNavigate } from "react-router";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { useAuth } from "shared/auth";
import { colors } from "theme/tokens/variables";
import { PopoverMessage } from "types/Messages";
import { TagDto } from "types/Tag";
import { WorkflowDef } from "types/WorkflowDef";
import {
  RUN_AGENT_URL,
  AGENT_DEFINITION_URL,
} from "utils/constants/route";
import useCustomPagination from "utils/hooks/useCustomPagination";
import { usePushHistory } from "utils/hooks/usePushHistory";
import { logger } from "utils/logger";
import { useActionWithPath, useWorkflowDefs } from "utils/query";
import { createSearchableTags, tryToJson } from "utils/utils";
import { getUniqueWorkflows } from "utils/workflow";
import CloneAgentDialog from "./dialog/CloneAgentDialog";

export default function AgentDefinitions() {
  const navigate = useNavigate();
  const { isTrialExpired } = useAuth();

  const { data, isFetching, refetch }: UseQueryResult<WorkflowDef[]> =
    useWorkflowDefs();
  const [showAddTagDialog, setShowAddTagDialog] = useState(false);
  const [addTagDialogData, setAddTagDialogData] =
    useState<TagDialogProps | null>(null);

  const [selectedWorkflowWithAction, setSelectedWorkflowWithAction] = useState<{
    selectedWorkflow: WorkflowDef | null;
    action: string;
  }>({
    selectedWorkflow: null,
    action: "",
  });
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);

  const { setMessage } = useContext(MessageContext);
  const pushHistory = usePushHistory();
  const [
    { filterParam, pageParam, searchParam },
    { setFilterParam, setSearchParam, handlePageChange },
  ] = useCustomPagination();
  const [confirmDelete, setConfirmDelete] = useState<{
    confirmDelete: boolean;
    workflowName: string;
    workflowVersion: number;
  } | null>(null);
  const filterObj =
    filterParam === "" ? undefined : tryToJson<FilterObjectItem>(filterParam);

  const deleteWorkflowVersionAction = useActionWithPath({
    onSuccess: () => {
      if (confirmDelete?.workflowName) {
        removeDeletedWorkflow(
          encodeURIComponent(confirmDelete?.workflowName),
          confirmDelete?.workflowVersion,
        );
      }

      refetch();
    },
    onError: (err: Error) => {
      setMessage({
        severity: "error",
        text: "Failed to delete workflow",
      });
      logger.error(err);
      refetch();
    },
  });

  const columns = useMemo<LegacyColumn[]>(
    () => [
      {
        id: "workflow_name",
        name: "name",
        label: "Agent name",
        renderer: (val: string) => {
          return (
            <NavLink
              data-cy="workflow-link"
              path={`${AGENT_DEFINITION_URL.BASE}/${encodeURIComponent(
                val.trim(),
              )}`}
              id={`${val.trim()}-link-btn`}
            >
              {val.trim()}
            </NavLink>
          );
        },
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
        id: "workflow_tags",
        name: "tags",
        label: "Tags",
        searchable: true,
        searchableFunc: (tags: TagDto[]) => createSearchableTags(tags),
        renderer: (tags: TagDto[], row: WorkflowDef) => (
          <TagList tags={tags} name={row?.name} />
        ),
        grow: 2,
        tooltip: "The tags associated with the agent",
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
        label: "Failure workflow",
        grow: 1,
        tooltip: "The compensation workflow",
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
        minWidth: "180px",
        tooltip: "Actions you can perform on the agent",
        renderer: (name: string, workflowRowData: WorkflowDef) => {
          return (
            <Box style={{ display: "flex", justifyContent: "space-evenly" }}>
              <Tooltip title={"Run agent"}>
                <IconButton
                  id={`run-${workflowRowData.name}-btn`}
                  disabled={isTrialExpired}
                  onClick={() => {
                    navigate("/runWorkflow", {
                      state: {
                        execution: {
                          workflowName: workflowRowData.name,
                          workflowVersion: workflowRowData.version,
                          input: workflowRowData?.inputParameters
                            ? Object.fromEntries(
                                workflowRowData.inputParameters.map((key) => [
                                  key,
                                  "",
                                ]),
                              )
                            : {},
                        },
                      },
                    });
                  }}
                  size="small"
                  sx={{
                    whiteSpace: "nowrap",
                  }}
                >
                  <PlayIcon size={22} />
                </IconButton>
              </Tooltip>

              <Tooltip title={"Clone agent"}>
                <IconButton
                  onClick={() =>
                    setSelectedWorkflowWithAction({
                      selectedWorkflow: workflowRowData,
                      action: "clone",
                    })
                  }
                  disabled={isTrialExpired}
                  size="small"
                  sx={{
                    whiteSpace: "nowrap",
                  }}
                >
                  <CopyIcon size={20} />
                </IconButton>
              </Tooltip>
              <Tooltip title={"Add/Edit tags"}>
                <IconButton
                  id={`add-tags-${workflowRowData.name}-btn`}
                  disabled={isTrialExpired}
                  onClick={() => {
                    setAddTagDialogData({
                      tags: workflowRowData.tags || [],
                      itemName: workflowRowData.name,
                      itemType: "workflow",
                    } as TagDialogProps);
                    setShowAddTagDialog(true);
                  }}
                  size="small"
                >
                  <TagIcon size={20} />
                </IconButton>
              </Tooltip>

              <Tooltip title={"Delete agent"}>
                <IconButton
                  id={`delete-${workflowRowData.name}-btn`}
                  disabled={isTrialExpired}
                  onClick={() => {
                    const selectedData = data?.find((x) => x.name === name);
                    if (selectedData) {
                      setConfirmDelete({
                        confirmDelete: true,
                        workflowName: selectedData.name,
                        workflowVersion: selectedData.version,
                      });
                    }
                  }}
                  size="small"
                  sx={{
                    whiteSpace: "nowrap",
                  }}
                >
                  <DeleteIcon size={20} />
                </IconButton>
              </Tooltip>
            </Box>
          );
        },
      },
    ],
    [data, navigate, isTrialExpired],
  );

  const handleFilterChange = useCallback(
    (obj?: FilterObjectItem) => {
      if (obj) {
        setFilterParam(JSON.stringify(obj));
      } else {
        setFilterParam("");
      }
    },
    [setFilterParam],
  );

  const workflows = useMemo(() => {
    // Extract latest versions only
    if (data) {
      return getUniqueWorkflows(data);
    }
  }, [data]);

  return (
    <>
      <Helmet>
        <title>Agent Definitions</title>
      </Helmet>

      {selectedWorkflowWithAction &&
        selectedWorkflowWithAction?.selectedWorkflow &&
        selectedWorkflowWithAction?.action === "clone" && (
          <CloneAgentDialog
            onClose={() =>
              setSelectedWorkflowWithAction({
                selectedWorkflow: null,
                action: "",
              })
            }
            onSuccess={() => {
              setSelectedWorkflowWithAction({
                selectedWorkflow: null,
                action: "",
              });
              refetch();
              setToastMessage({
                text: "Agent cloned successfully",
                severity: "success",
              });
            }}
            selectedWorkflow={selectedWorkflowWithAction?.selectedWorkflow}
            workflowList={data ?? []}
          />
        )}

      <AddTagDialog
        open={showAddTagDialog && !!addTagDialogData}
        tags={addTagDialogData?.tags || []}
        itemType={addTagDialogData?.itemType}
        itemName={addTagDialogData?.itemName}
        onClose={() => {
          setShowAddTagDialog(false);
          setAddTagDialogData(null);
        }}
        onSuccess={() => {
          setShowAddTagDialog(false);
          setAddTagDialogData(null);
          refetch();
        }}
      />

      {confirmDelete && (
        <ConfirmChoiceDialog
          handleConfirmationValue={(selectedChoice) => {
            if (selectedChoice) {
              // @ts-ignore
              deleteWorkflowVersionAction.mutate({
                method: "delete",
                path: `agent/definitions/${encodeURIComponent(
                  confirmDelete.workflowName,
                )}?version=${confirmDelete.workflowVersion}`,
              });
            }
            setConfirmDelete(null);
          }}
          message={
            <>
              Are you sure you want to delete{" "}
              <strong style={{ color: "red" }}>
                {confirmDelete.workflowName}
              </strong>{" "}
              workflow definition? This cannot be undone.
              <div style={{ marginTop: "15px" }}>
                Please type <strong>{confirmDelete.workflowName}</strong> to
                confirm.
              </div>
            </>
          }
          header={"Deletion confirmation"}
          isInputConfirmation
          valueToBeDeleted={confirmDelete.workflowName}
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
        <Paper id="workflow-definitions-table-wrapper" variant="outlined">
          <Header loading={isFetching} />
          {workflows && (
            <DataTable
              localStorageKey="workflowsTable"
              quickSearchEnabled
              quickSearchPlaceholder="Search agent definitions"
              searchTerm={searchParam}
              onSearchTermChange={setSearchParam}
              defaultShowColumns={[
                "workflow_name",
                "workflow_description",
                "workflow_tags",
                "latest_version",
                "create_time",
                "owner_email",
                "executions_link",
                "actions",
              ]}
              keyField="name"
              onFilterChange={handleFilterChange}
              initialFilterObj={filterObj}
              data={workflows}
              columns={columns}
              filterByTags
              customActions={[
                <Tooltip
                  title="Refresh agent definitions"
                  key={"rfrshWdefs"}
                >
                  <Button
                    variant="text"
                    color="inherit"
                    size="small"
                    startIcon={<RefreshIcon />}
                    key="refresh"
                    onClick={refetch as () => void}
                  >
                    Refresh
                  </Button>
                </Tooltip>,
              ]}
              onChangePage={handlePageChange}
              paginationDefaultPage={pageParam ? Number(pageParam) : 1}
              noDataComponent={
                searchParam === "" ? (
                  <NoDataComponent
                    title="Agent Definition"
                    description="No agents deployed yet. Use the CLI to deploy agents."
                  />
                ) : (
                  <NoDataComponent
                    title="Empty"
                    titleBg={colors.warningTag}
                    description="I'm sorry that search didn't find any matches. Please try different filters."
                    buttonText="Clear search"
                    buttonHandler={() => setSearchParam("")}
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
          onDismiss={() => {
            setToastMessage(null);
          }}
        />
      )}
    </>
  );
}
