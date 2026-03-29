import { FunctionComponent } from "react";
import { useNavigate } from "react-router";
import { useSelector } from "@xstate/react";
import { ActorRef } from "xstate";
import {
  DefinitionMachineContext,
  WorkflowDefinitionEvents,
} from "../state/types";
import { ButtonTooltip } from "components/ButtonTooltip";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import { UnderlinedText } from "components/v1/UnderlinedText";
import { RUN_AGENT_URL } from "utils/constants/route";

export interface RunWorkflowButtonProps {
  definitionActor: ActorRef<WorkflowDefinitionEvents>;
  disabled: boolean;
}

export const RunWorkflowButton: FunctionComponent<RunWorkflowButtonProps> = ({
  definitionActor,
  disabled,
}) => {
  const navigate = useNavigate();
  const workflowName = useSelector(
    definitionActor,
    (state) => (state.context as DefinitionMachineContext)?.workflowName,
  );

  const executeAgent = () => {
    // Navigate to the Run Agent page with the agent name pre-selected
    navigate(RUN_AGENT_URL, { state: { agentName: workflowName } });
  };

  return (
    <ButtonTooltip
      id="head-action-run-btn"
      variant="contained"
      tooltip="Run agent (Ctrl E)"
      onClick={executeAgent}
      startIcon={<RocketLaunchIcon />}
      children={<UnderlinedText text="Execute" underlinedIndexes={[0]} />}
      disabled={disabled}
    />
  );
};
