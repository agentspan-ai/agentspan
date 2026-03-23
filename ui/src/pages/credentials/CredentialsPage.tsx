import { Box, Tooltip, Typography } from "@mui/material";
import {
  CaretRight as ExpandIcon,
  CaretDown as CollapseIcon,
  PencilSimple as EditIcon,
  Trash as DeleteIcon,
} from "@phosphor-icons/react";
import { Button, DataTable, IconButton, Paper } from "components";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import Header from "components/Header";
import NoDataComponent from "components/NoDataComponent";
import { SnackbarMessage } from "components/SnackbarMessage";
import AddIcon from "components/v1/icons/AddIcon";
import { Fragment, useMemo, useState } from "react";
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

  const [expandedNames, setExpandedNames] = useState<Set<string>>(new Set());
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editCredential, setEditCredential] =
    useState<CredentialListItem | null>(null);
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(
    null,
  );
  const [addBindingFor, setAddBindingFor] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);

  const deleteCredential = useDeleteCredential(apiOpts);
  const deleteBinding = useDeleteBinding(apiOpts);

  const credentials = credentialsQuery.data ?? [];
  const bindings = bindingsQuery.data ?? [];

  // Show LoginDialog only on 401, not on every page load with no token.
  // In OSS mode (auth.enabled=false) the server returns 200 with no token, so
  // isAuthenticated=false but credentialsQuery.error is null → dialog stays hidden.
  // This matches the spec: "LoginDialog only appears in response to a 401."
  const needs401Login =
    !isAuthenticated &&
    ((credentialsQuery.error as any)?.status === 401 ||
      (bindingsQuery.error as any)?.status === 401);

  const toggleExpanded = (name: string) => {
    setExpandedNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const columns = useMemo(
    () => [
      {
        id: "expand",
        name: "name",
        label: "",
        sortable: false,
        searchable: false,
        grow: 0,
        width: "48px",
        renderer: (name: string) => (
          <IconButton
            size="small"
            data-testid={`expand-${name}`}
            onClick={() => toggleExpanded(name)}
          >
            {expandedNames.has(name) ? (
              <CollapseIcon size={16} />
            ) : (
              <ExpandIcon size={16} />
            )}
          </IconButton>
        ),
      },
      {
        id: "name",
        name: "name",
        label: "Name",
        searchable: true,
        renderer: (name: string) => (
          <Typography variant="body2" fontFamily="monospace" fontWeight={500}>
            {name}
          </Typography>
        ),
      },
      {
        id: "partial",
        name: "partial",
        label: "Value",
        searchable: false,
        renderer: (partial: string) => (
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
            {partial}
          </Typography>
        ),
      },
      {
        id: "updated_at",
        name: "updated_at",
        label: "Last updated",
        searchable: false,
        renderer: (updated_at: string) => (
          <Typography variant="body2" color="text.secondary">
            {new Date(updated_at).toLocaleString()}
          </Typography>
        ),
      },
      {
        id: "actions",
        name: "name",
        label: "Actions",
        sortable: false,
        searchable: false,
        grow: 0.5,
        renderer: (name: string, cred: CredentialListItem) => (
          <Box sx={{ display: "flex", gap: 2 }}>
            <Tooltip title="Edit credential">
              <IconButton
                size="small"
                onClick={() => setEditCredential(cred)}
                data-testid={`edit-${name}`}
              >
                <EditIcon size={20} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete credential">
              <IconButton
                size="small"
                color="error"
                onClick={() => setConfirmDeleteName(name)}
                data-testid={`delete-${name}`}
              >
                <DeleteIcon size={20} />
              </IconButton>
            </Tooltip>
          </Box>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [expandedNames],
  );

  const ExpandedBindings = ({ data }: { data: CredentialListItem }) => {
    const rowBindings = bindings.filter((b) => b.store_name === data.name);
    return (
      <Box
        sx={{
          py: 1.5,
          px: 3,
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
            <code style={{ fontSize: "inherit" }}>{data.name}</code>
          </Typography>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setAddBindingFor(data.name)}
          >
            + Add binding
          </Button>
        </Box>
        <BindingChips
          bindings={rowBindings}
          onDelete={async (logicalKey) => {
            try {
              await deleteBinding.mutateAsync(logicalKey);
              setToastMessage({ text: "Binding removed.", severity: "success" });
            } catch {
              setToastMessage({
                text: "Failed to remove binding.",
                severity: "error",
              });
            }
          }}
        />
      </Box>
    );
  };

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
          onSuccess={() =>
            setToastMessage({ text: "Credential added.", severity: "success" })
          }
          onClose={() => setAddDialogOpen(false)}
        />
      )}

      {editCredential && (
        <AddEditCredentialDialog
          mode="edit"
          initialName={editCredential.name}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() =>
            setToastMessage({
              text: "Credential updated.",
              severity: "success",
            })
          }
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
                setToastMessage({
                  text: "Credential deleted.",
                  severity: "success",
                });
              } catch {
                setToastMessage({
                  text: "Failed to delete credential.",
                  severity: "error",
                });
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
          onSuccess={() =>
            setToastMessage({ text: "Binding added.", severity: "success" })
          }
          onError={() =>
            setToastMessage({
              text: "Failed to add binding.",
              severity: "error",
            })
          }
          onClose={() => setAddBindingFor(null)}
        />
      )}

      <SectionHeader
        title="Credentials"
        _deprecate_marginTop={0}
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

      <SectionContainer>
        {/*@ts-ignore*/}
        <Paper variant="outlined">
          <Header loading={credentialsQuery.isFetching} />
          {/* @ts-ignore */}
          <DataTable
            localStorageKey="credentialsTable"
            quickSearchEnabled
            quickSearchPlaceholder="Search credentials"
            keyField="name"
            data={credentials}
            columns={columns}
            expandableRows
            expandableRowExpanded={(row: CredentialListItem) =>
              expandedNames.has(row.name)
            }
            expandableRowsHideExpander
            expandableRowsComponent={ExpandedBindings}
            noDataComponent={
              <NoDataComponent
                title="Credentials"
                description="Store API keys and secrets securely. Values are encrypted at rest and never shown after creation."
                buttonText="Add Credential"
                buttonHandler={() => setAddDialogOpen(true)}
              />
            }
          />
        </Paper>
      </SectionContainer>

      {toastMessage && (
        <SnackbarMessage
          autoHideDuration={3000}
          message={toastMessage.text}
          severity={toastMessage.severity}
          onDismiss={() => setToastMessage(null)}
        />
      )}
    </>
  );
}
