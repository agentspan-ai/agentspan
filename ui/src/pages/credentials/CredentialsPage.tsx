import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Box,
  Button,
  Collapse,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import { SnackbarMessage } from "components/SnackbarMessage";
import { Fragment, useState, useMemo } from "react";
import { Helmet } from "react-helmet";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { PopoverMessage } from "types/Messages";
import { AddBindingDialog } from "./components/AddBindingDialog";
import { AddEditCredentialDialog } from "./components/AddEditCredentialDialog";
import { BindingChips } from "./components/BindingChips";
import { LoginDialog } from "./components/LoginDialog";
import { useCredentialAuth } from "./hooks/useCredentialAuth";
import {
  useDeleteBinding,
  useDeleteCredential,
  useListBindings,
  useListCredentials,
} from "./hooks/useCredentialsApi";
import { CredentialListItem } from "./types";

export function CredentialsPage() {
  const { token, isAuthenticated, setToken, clearToken } = useCredentialAuth();
  const apiOpts = { token, onUnauthorized: clearToken };

  const credentialsQuery = useListCredentials(apiOpts);
  const bindingsQuery = useListBindings(apiOpts);

  const [expandedName, setExpandedName] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editCredential, setEditCredential] = useState<CredentialListItem | null>(null);
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(null);
  const [addBindingFor, setAddBindingFor] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);

  const deleteCredential = useDeleteCredential(apiOpts);
  const deleteBinding = useDeleteBinding(apiOpts);

  const credentials = credentialsQuery.data ?? [];
  const bindings = bindingsQuery.data ?? [];

  const filtered = useMemo(
    () =>
      search.trim()
        ? credentials.filter((c) =>
            c.name.toLowerCase().includes(search.toLowerCase()),
          )
        : credentials,
    [credentials, search],
  );

  function bindingsFor(storeName: string) {
    return bindings.filter((b) => b.store_name === storeName);
  }

  // Show LoginDialog only on 401, not on every page load with no token.
  // In OSS mode (auth.enabled=false) the server returns 200 with no token, so
  // isAuthenticated=false but credentialsQuery.error is null → dialog stays hidden.
  // This matches the spec: "LoginDialog only appears in response to a 401."
  const needs401Login =
    !isAuthenticated &&
    (credentialsQuery.error as any)?.status === 401;

  return (
    <>
      <Helmet>
        <title>Credentials</title>
      </Helmet>

      {/* Dialogs */}
      {needs401Login && (
        <LoginDialog
          onSuccess={(tok) => {
            setToken(tok);
            credentialsQuery.refetch();
            bindingsQuery.refetch();
          }}
        />
      )}

      {addDialogOpen && (
        <AddEditCredentialDialog
          mode="add"
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Credential added.", severity: "success" })}
          onClose={() => setAddDialogOpen(false)}
        />
      )}

      {editCredential && (
        <AddEditCredentialDialog
          mode="edit"
          initialName={editCredential.name}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Credential updated.", severity: "success" })}
          onClose={() => setEditCredential(null)}
        />
      )}

      {confirmDeleteName && (
        <ConfirmChoiceDialog
          header="Delete Credential"
          message={
            <>
              Are you sure you want to delete{" "}
              <strong style={{ color: "red" }}>{confirmDeleteName}</strong>?
              This cannot be undone.
              <div style={{ marginTop: 12 }}>
                Type <strong>{confirmDeleteName}</strong> to confirm.
              </div>
            </>
          }
          isInputConfirmation
          valueToBeDeleted={confirmDeleteName}
          isConfirmLoading={deleteCredential.isLoading}
          handleConfirmationValue={async (confirmed) => {
            if (confirmed && confirmDeleteName) {
              try {
                await deleteCredential.mutateAsync(confirmDeleteName);
                setToastMessage({ text: "Credential deleted.", severity: "success" });
              } catch {
                setToastMessage({ text: "Failed to delete credential.", severity: "error" });
              }
            }
            setConfirmDeleteName(null);
          }}
        />
      )}

      {addBindingFor && (
        <AddBindingDialog
          credentialName={addBindingFor}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() => setToastMessage({ text: "Binding added.", severity: "success" })}
          onClose={() => setAddBindingFor(null)}
        />
      )}

      {/* Header */}
      <SectionHeader
        title="Credentials"
        actions={
          <SectionHeaderActions
            buttons={[
              ...(isAuthenticated
                ? [
                    {
                      label: "Logout",
                      onClick: clearToken,
                      variant: "text" as const,
                    },
                  ]
                : []),
              {
                label: "Add Credential",
                onClick: () => setAddDialogOpen(true),
                startIcon: <AddIcon />,
              },
            ]}
          />
        }
      />

      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ px: 3, pb: 1 }}
      >
        Per-user API keys and secrets. Values are encrypted at rest and never
        shown after creation.
      </Typography>

      <SectionContainer>
        {/* Search */}
        <Box sx={{ mb: 2 }}>
          <TextField
            size="small"
            placeholder="Search credentials…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ width: 280 }}
          />
        </Box>

        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 32 }} /> {/* chevron — 5 columns total */}
                <TableCell>Name</TableCell>
                <TableCell>Value (partial)</TableCell>
                <TableCell>Last updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((cred) => {
                const expanded = expandedName === cred.name;
                const rowBindings = bindingsFor(cred.name);
                return (
                  <Fragment key={cred.name}>
                    <TableRow
                      hover
                      sx={{ "& > *": { borderBottom: expanded ? 0 : undefined } }}
                    >
                      <TableCell padding="checkbox">
                        <IconButton
                          size="small"
                          data-testid={`expand-${cred.name}`}
                          onClick={() =>
                            setExpandedName(expanded ? null : cred.name)
                          }
                        >
                          {expanded ? (
                            <ExpandMoreIcon fontSize="small" />
                          ) : (
                            <ChevronRightIcon fontSize="small" />
                          )}
                        </IconButton>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          fontFamily="monospace"
                          fontWeight={500}
                        >
                          {cred.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          fontFamily="monospace"
                          sx={{
                            bgcolor: "action.hover",
                            px: 0.75,
                            py: 0.25,
                            borderRadius: 1,
                            display: "inline",
                          }}
                        >
                          {cred.partial}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {cred.updated_at}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="Edit">
                          <IconButton
                            size="small"
                            onClick={() => setEditCredential(cred)}
                            data-testid={`edit-${cred.name}`}
                          >
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => setConfirmDeleteName(cred.name)}
                            data-testid={`delete-${cred.name}`}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>

                    {/* Bindings expansion row */}
                    <TableRow>
                      <TableCell
                        colSpan={5}
                        sx={{ py: 0, borderBottom: expanded ? undefined : 0 }}
                      >
                        <Collapse in={expanded} timeout="auto" unmountOnExit>
                          <Box
                            sx={{
                              py: 1.5,
                              px: 2,
                              bgcolor: "action.hover",
                              borderTop: "1px solid",
                              borderColor: "divider",
                            }}
                          >
                            <Box
                              sx={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                mb: 1,
                              }}
                            >
                              <Typography
                                variant="caption"
                                fontWeight={600}
                                color="text.secondary"
                                textTransform="uppercase"
                                letterSpacing={0.5}
                              >
                                Bindings — logical keys that resolve to{" "}
                                <code style={{ fontSize: "inherit" }}>
                                  {cred.name}
                                </code>
                              </Typography>
                              <Button
                                size="small"
                                variant="outlined"
                                onClick={() => setAddBindingFor(cred.name)}
                              >
                                + Add binding
                              </Button>
                            </Box>
                            <BindingChips
                              bindings={rowBindings}
                              onDelete={async (logicalKey) => {
                                try {
                                  await deleteBinding.mutateAsync(logicalKey);
                                  setToastMessage({
                                    text: "Binding removed.",
                                    severity: "success",
                                  });
                                } catch {
                                  setToastMessage({
                                    text: "Failed to remove binding.",
                                    severity: "error",
                                  });
                                }
                              }}
                            />
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </Fragment>
                );
              })}

              {filtered.length === 0 && !credentialsQuery.isLoading && (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                    <Typography color="text.secondary">
                      {search
                        ? `No credentials match "${search}"`
                        : "No credentials yet — click Add Credential to get started."}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionContainer>

      {toastMessage && (
        <SnackbarMessage
          message={toastMessage.text}
          severity={toastMessage.severity}
          autoHideDuration={3000}
          onDismiss={() => setToastMessage(null)}
        />
      )}
    </>
  );
}
