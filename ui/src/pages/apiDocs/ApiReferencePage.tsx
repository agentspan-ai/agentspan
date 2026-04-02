/**
 * API Reference Page
 *
 * Renders the API docs inline inside the main app shell — no redirect,
 * no iframe. The ApiDocsPage component detects whether it is running inside
 * the main app or the standalone /docs/ page and adjusts its layout
 * accordingly (sidebar vs. horizontal category chips).
 */

import { Box } from "@mui/material";
import { ApiDocsPage } from "../../docs/api-docs-page";

export default function ApiReferencePage() {
  return (
    <Box sx={{ height: "100%", overflow: "hidden" }}>
      <ApiDocsPage />
    </Box>
  );
}
