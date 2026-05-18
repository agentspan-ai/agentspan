import PlayIcon from "@mui/icons-material/PlayArrowOutlined";
import { Box } from "@mui/material";

import MuiButton from "components/MuiButton";
import MuiIconButton from "components/MuiIconButton";
import { usePushHistory } from "utils/hooks/usePushHistory";
import { RUN_AGENT_URL } from "utils/constants/route";
import { useAuth } from "shared/auth";

const RunAgentButton = ({ open }: { open: boolean }) => {
  const pushHistory = usePushHistory();
  const { isTrialExpired } = useAuth();

  if (!open) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          height: "28px",
          ":hover": {
            background: "#0D94DB",
            borderRadius: "0 20px 20px 0px",
            height: "28px",
          },
        }}
      >
        <MuiIconButton
          onClick={() => pushHistory(RUN_AGENT_URL)}
          sx={{
            opacity: "0.7",
            fontSize: "18px",
            ":hover": {
              color: "white",
              backgroundColor: "transparent",
              opacity: 1,
            },
          }}
        >
          <PlayIcon />
        </MuiIconButton>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", justifyContent: "center", my: 2 }}>
      <MuiButton
        startIcon={<PlayIcon />}
        onClick={() => pushHistory(RUN_AGENT_URL)}
        disabled={isTrialExpired}
      >
        Run Agent
      </MuiButton>
    </Box>
  );
};

export default RunAgentButton;
