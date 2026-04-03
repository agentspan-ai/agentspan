import { Box } from "@mui/material";
import { FEATURES, featureFlags } from "utils";
import { ActorRef, EventObject } from "xstate";
import {
  CODE_TAB,
  DEPENDENCIES_TAB,
} from "../state/constants";
import { WorkflowDefinitionEvents } from "../state/types";
import { CodeTab } from "./CodeEditorTab";
import DependenciesTab from "./DependenciesTab/DependenciesTab";

const isPlayground = featureFlags.isEnabled(FEATURES.PLAYGROUND);

// Type helper for ActorRef with children property
type ActorRefWithChildren<T extends EventObject> = ActorRef<T> & {
  children?: {
    get: <E extends EventObject = EventObject>(
      id: string,
    ) => ActorRef<E> | undefined;
  };
};

interface TabContentProps {
  openedTab: number;
  isReady: boolean;
  isRunWorkflow: boolean;
  isInTaskFormState: boolean;
  definitionActor: ActorRef<WorkflowDefinitionEvents>;
  getTabContentHeight: () => string;
}

export const TabContent = ({
  openedTab,
  isReady,
  isRunWorkflow,
  isInTaskFormState,
  definitionActor,
  getTabContentHeight,
}: TabContentProps) => {
  return (
    <Box
      id="editor-panel-tab-content"
      sx={{
        overflow: "hidden",
        flexGrow: 1,
        display: "flex",
        flexDirection: "column",
        scrollbarGutter: "stable",
      }}
    >
      {openedTab === CODE_TAB ? (
        <Box
          id="code-tab"
          data-cy="workflow-definition-editor"
          sx={{
            display: "flex",
            flexFlow: "column",
            height: getTabContentHeight(),
            width: "100%",
          }}
        >
          <CodeTab
            codeTabActor={(
              definitionActor as ActorRefWithChildren<WorkflowDefinitionEvents>
            ).children?.get("codeMachine")}
            saveChangesActor={(
              definitionActor as ActorRefWithChildren<WorkflowDefinitionEvents>
            ).children?.get("saveChangesMachine")}
          />
        </Box>
      ) : null}
      {openedTab === DEPENDENCIES_TAB && isPlayground && (
        <Box
          sx={{
            height: getTabContentHeight(),
            overflow: "auto",
          }}
        >
          <DependenciesTab />
        </Box>
      )}
    </Box>
  );
};
