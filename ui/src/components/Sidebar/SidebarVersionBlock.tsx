import { Box, Typography, useTheme } from "@mui/material";

import ClipboardCopy from "components/ClipboardCopy";
import { FEATURES, featureFlags } from "utils";

const isPlayground = featureFlags.isEnabled(FEATURES.PLAYGROUND);

interface SidebarVersionBlockProps {
  open: boolean;
  conductorVersion: string;
  uiVersion: string;
}

/**
 * Shared version block for the sidebar footer (logo, version copy, copyright).
 * Used by SidebarFooter and by SidebarMenu when rendering a custom userFooter.
 */
export function SidebarVersionBlock({
  open,
  conductorVersion,
  uiVersion,
}: SidebarVersionBlockProps) {
  const theme = useTheme();

  return (
    <Box
      sx={{
        borderRadius: 1,
        p: 2,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          mb: open ? 1 : 0,
        }}
      >
        <img
          src={
            open
              ? theme.palette.mode === "dark" ? "/agentspan-logo-dark.svg" : "/agentspan-logo-light.svg"
              : "/agentspan-icon.svg"
          }
          alt="agentspan"
          style={{ width: open ? "60%" : "32px", height: open ? undefined : "32px" }}
        />
      </Box>

      {!isPlayground && open && (
        <ClipboardCopy
          buttonId="copy-version-btn"
          value={`${conductorVersion} | ${uiVersion}`}
          sx={{
            justifyContent: "center",
          }}
        >
          <Typography fontSize="12px" color={theme.palette.text.secondary}>
            {`${conductorVersion} | ${uiVersion}`}
          </Typography>
        </ClipboardCopy>
      )}
    </Box>
  );
}
