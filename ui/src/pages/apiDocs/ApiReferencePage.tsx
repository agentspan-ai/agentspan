/**
 * API Reference Page
 *
 * Redirects to the static API docs page.
 */

import { useEffect } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";

export default function ApiReferencePage() {
  useEffect(() => {
    window.location.href = "/docs/";
  }, []);

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: 2,
      }}
    >
      <CircularProgress />
      <Typography variant="body1" color="text.secondary">
        Redirecting to API Documentation...
      </Typography>
    </Box>
  );
}
