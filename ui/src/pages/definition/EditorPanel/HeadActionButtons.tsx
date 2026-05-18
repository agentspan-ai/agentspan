import Stack from "@mui/material/Stack";
import _isEmpty from "lodash/isEmpty";
import { FunctionComponent } from "react";
import { useNavigate } from "react-router";
import { useSelector } from "@xstate/react";
import { ActorRef } from "xstate";
import { Key } from "ts-key-enum";
import { useHotkeys } from "react-hotkeys-hook";

import { ButtonTooltip, ButtonTooltipProps } from "components/ButtonTooltip";
import DownloadIcon from "components/v1/icons/DownloadIcon";

import { exportObjToFile } from "utils";
import {
  DefinitionMachineContext,
  WorkflowDefinitionEvents,
} from "../state/types";
import { useWorkflowChanges } from "../state/useMadeChanges";
import { HOT_KEYS_WORKFLOW_DEFINITION } from "utils/constants/common";
import { UnderlinedText } from "components/v1/UnderlinedText";
import { RunWorkflowButton } from "./RunWorkflowButton";
import { RUN_AGENT_URL } from "utils/constants/route";

export interface HeaderActionButtonsProps {
  definitionActor: ActorRef<WorkflowDefinitionEvents>;
}
export const HeadActionButtons: FunctionComponent<HeaderActionButtonsProps> = ({
  definitionActor: service,
}) => {
  const navigate = useNavigate();
  const { workflowChanges } = useWorkflowChanges(service);
  const workflowName = useSelector(
    service,
    (state) => (state.context as DefinitionMachineContext)?.workflowName,
  );

  const emptyTaskList = _isEmpty(workflowChanges?.tasks);

  const handleDownloadFile = () => {
    exportObjToFile({
      data: workflowChanges,
      fileName: `${workflowChanges.name || "new"}_${
        workflowChanges.version
      }.json`,
      type: `application/json`,
    });
  };

  const handleExecuteRequest = () => {
    navigate(RUN_AGENT_URL, { state: { agentName: workflowName } });
  };

  const buttons: ButtonTooltipProps[] = [
    {
      id: "head-action-download-btn",
      variant: "text",
      tooltip: "Download JSON as file  (Ctrl W)",
      disabled: false,
      onClick: handleDownloadFile,
      "data-testid": "workflow-definition-download-button",
      startIcon: <DownloadIcon />,
      children: <UnderlinedText text="Download" underlinedIndexes={[2]} />,
    },
  ];

  // Hotkeys: Execute (Ctrl+E) and Download (Ctrl+W)
  useHotkeys(
    [`${Key.Control} + E`, `${Key.Control} + W`],
    (keyboardEvent, { keys }) => {
      keyboardEvent.preventDefault();
      const joinedKeys = keys?.join();

      switch (joinedKeys) {
        case [Key.Control, "E"].join().toLowerCase(): {
          handleExecuteRequest();
          break;
        }
        case [Key.Control, "W"].join().toLowerCase(): {
          handleDownloadFile();
          break;
        }
      }
    },
    {
      scopes: HOT_KEYS_WORKFLOW_DEFINITION,
      enableOnFormTags: ["INPUT", "TEXTAREA", "SELECT"],
    },
  );

  return (
    <Stack flexDirection="row" gap={1} flexWrap="wrap">
      {buttons.map(({ id, ...props }) => (
        <ButtonTooltip key={id} id={id} {...props} />
      ))}

      <RunWorkflowButton definitionActor={service} disabled={emptyTaskList} />
    </Stack>
  );
};
