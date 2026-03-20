import { AlertColor, Box, Tab, Tabs } from "@mui/material";
import { useSelector } from "@xstate/react";
import { SnackbarMessage } from "components/SnackbarMessage";
import TwoPanesDivider from "components/TwoPanesDivider";
import {
  DefinitionMachineContext,
  FlowEditContextProvider,
  WorkflowDefinitionEvents,
} from "pages/definition/state";
import { AgentDefinitionDiagram } from "pages/execution/AgentDefinitionView";
import { Helmet } from "react-helmet";
import { useAuth } from "shared/auth";
import { useState } from "react";
import { ActorRef, State } from "xstate";
import sharedStyles from "../styles";
import EditorPanel from "./EditorPanel/EditorPanel";
import GraphPanel from "./GraphPanel";
import { PromptIfChanges } from "./PromptIfChanges";
import { useWorkflowDefinition } from "./state/hook";
import { WorkflowMetaBar } from "./WorkflowMetadata";

export default function Workflow() {
  const { conductorUser } = useAuth();
  const [
    { handleResetMessage, setLeftPanelExpanded },
    { workflowName, message, definitionActor, leftPanelExpanded },
  ] = useWorkflowDefinition(conductorUser!);

  const [activeView, setActiveView] = useState<"agentDef" | "conductorWorkflow">("agentDef");

  const agentDef = useSelector(
    definitionActor,
    (state: State<DefinitionMachineContext>) =>
      (state.context?.workflowChanges as any)?.metadata?.agentDef as Record<string, unknown> | undefined,
  );

  const graphPanel = <GraphPanel definitionActor={definitionActor} readOnly />;

  const editorPanel = definitionActor && (
    <EditorPanel definitionActor={definitionActor} readOnly />
  );

  const isReady = useSelector(
    definitionActor,
    (state: State<DefinitionMachineContext>) => state.matches("ready"),
  );

  return (
    <>
      {isReady && definitionActor && (
        <WorkflowMetaBar
          {...{
            definitionActor: definitionActor,
            leftPanelExpanded,
            setLeftPanelExpanded,
            readOnly: activeView === "conductorWorkflow",
          }}
        />
      )}
      <Box sx={sharedStyles.wrapper}>
        <Helmet>
          <title>Workflow Definition - {workflowName || "NEW"}</title>
        </Helmet>
        <SnackbarMessage
          message={message?.text as string}
          severity={message?.severity as AlertColor}
          onDismiss={handleResetMessage}
        />

        <Box
          sx={{
            height: "100%",
            flex: "1 1 0%",
            position: "relative",
            display: "flex",
            flexDirection: "column",
          }}
          data-testid="workflow-definition-container"
        >
          {/* View switcher tabs */}
          <Box sx={{ borderBottom: "1px solid rgba(0,0,0,.12)", backgroundColor: "#fff", flexShrink: 0 }}>
            <Tabs
              value={activeView}
              onChange={(_, v) => setActiveView(v)}
              sx={{ minHeight: 40, "& .MuiTab-root": { minHeight: 40, fontSize: "0.8125rem", textTransform: "none" } }}
            >
              <Tab label="Agent Definition" value="agentDef" />
              <Tab label="Conductor Workflow" value="conductorWorkflow" />
            </Tabs>
          </Box>

          <Box sx={{ flex: 1, position: "relative", overflow: "hidden" }}>
            {/* Agent Definition view */}
            {activeView === "agentDef" && (
              <Box sx={{ height: "100%", width: "100%" }}>
                {agentDef ? (
                  <AgentDefinitionDiagram agentDef={agentDef} />
                ) : (
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary", fontSize: "0.875rem" }}>
                    No agent definition found in workflow metadata
                  </Box>
                )}
              </Box>
            )}

            {/* Conductor Workflow view (read-only) */}
            {activeView === "conductorWorkflow" && (
              <Box
                sx={{
                  height: "100%",
                  width: "100%",
                  overflow: "visible",
                  display: "flex",
                  flexDirection: "column",
                  backgroundColor: "transparent",
                  fontSize: "13px",
                  position: "absolute",
                  inset: 0,
                  zIndex: 1,
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    height: "100%",
                    position: "absolute",
                    overflow: "visible",
                    userSelect: "text",
                    flexDirection: "row",
                    left: "0px",
                    right: "0px",
                  }}
                >
                  <PromptIfChanges
                    definitionActor={
                      definitionActor as ActorRef<WorkflowDefinitionEvents>
                    }
                  />
                  <FlowEditContextProvider
                    workflowDefinitionActor={definitionActor}
                  >
                    {definitionActor?.children.get("flowMachine") && (
                      <TwoPanesDivider
                        leftPanelContent={graphPanel}
                        rightPanelContent={editorPanel}
                        leftPanelExpanded={leftPanelExpanded}
                        setLeftPanelExpanded={setLeftPanelExpanded}
                      />
                    )}
                  </FlowEditContextProvider>
                </Box>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    </>
  );
}
