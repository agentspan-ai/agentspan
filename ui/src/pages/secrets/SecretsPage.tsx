import { Box, Tooltip, Typography } from "@mui/material";
import {
  PencilSimple as EditIcon,
  Trash as DeleteIcon,
} from "@phosphor-icons/react";
import { DataTable, IconButton, Paper } from "components";
import ConfirmChoiceDialog from "components/ConfirmChoiceDialog";
import Header from "components/Header";
import NoDataComponent from "components/NoDataComponent";
import { SnackbarMessage } from "components/SnackbarMessage";
import AddIcon from "components/v1/icons/AddIcon";
import { useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { PopoverMessage } from "types/Messages";
import { AddEditSecretDialog } from "./components/AddEditSecretDialog";
import { LoginDialog } from "./components/LoginDialog";
import { useSecretAuth } from "./hooks/useSecretAuth";
import {
  useDeleteSecret,
  useListSecrets,
} from "./hooks/useSecretsApi";
import { SecretListItem } from "./types";

export function SecretsPage() {
  const { token, isAuthenticated, setToken, clearToken } = useSecretAuth();
  const apiOpts = { token, onUnauthorized: clearToken };

  const secretsQuery = useListSecrets(apiOpts);

  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editSecret, setEditSecret] =
    useState<SecretListItem | null>(null);
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(
    null,
  );
  const [toastMessage, setToastMessage] = useState<PopoverMessage | null>(null);

  const deleteSecret = useDeleteSecret(apiOpts);

  const secrets = secretsQuery.data ?? [];

  // Show LoginDialog only on 401, not on every page load with no token.
  // In OSS mode (auth.enabled=false) the server returns 200 with no token, so
  // isAuthenticated=false but secretsQuery.error is null → dialog stays hidden.
  const needs401Login =
    !isAuthenticated && (secretsQuery.error as any)?.status === 401;

  const columns = useMemo(
    () => [
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
        renderer: (name: string, cred: SecretListItem) => (
          <Box sx={{ display: "flex", gap: 2 }}>
            <Tooltip title="Edit secret">
              <IconButton
                size="small"
                onClick={() => setEditSecret(cred)}
                data-testid={`edit-${name}`}
              >
                <EditIcon size={20} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete secret">
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
    [],
  );

  return (
    <>
      <Helmet>
        <title>Secrets</title>
      </Helmet>

      {/* Dialogs */}
      {needs401Login && (
        <LoginDialog
          onSuccess={(tok) => {
            setToken(tok);
            secretsQuery.refetch();
          }}
        />
      )}

      {addDialogOpen && (
        <AddEditSecretDialog
          mode="add"
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() =>
            setToastMessage({ text: "Secret added.", severity: "success" })
          }
          onClose={() => setAddDialogOpen(false)}
        />
      )}

      {editSecret && (
        <AddEditSecretDialog
          mode="edit"
          initialName={editSecret.name}
          token={token}
          onUnauthorized={clearToken}
          onSuccess={() =>
            setToastMessage({
              text: "Secret updated.",
              severity: "success",
            })
          }
          onClose={() => setEditSecret(null)}
        />
      )}

      {confirmDeleteName && (
        <ConfirmChoiceDialog
          header="Delete Secret"
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
          isConfirmLoading={deleteSecret.isLoading}
          handleConfirmationValue={async (confirmed) => {
            if (confirmed && confirmDeleteName) {
              try {
                await deleteSecret.mutateAsync(confirmDeleteName);
                setToastMessage({
                  text: "Secret deleted.",
                  severity: "success",
                });
              } catch {
                setToastMessage({
                  text: "Failed to delete secret.",
                  severity: "error",
                });
              }
            }
            setConfirmDeleteName(null);
          }}
        />
      )}

      <SectionHeader
        title="Secrets"
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
                label: "Add Secret",
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
          <Header loading={secretsQuery.isFetching} />
          {/* @ts-ignore */}
          <DataTable
            localStorageKey="secretsTable"
            quickSearchEnabled
            quickSearchPlaceholder="Search secrets"
            keyField="name"
            data={secrets}
            columns={columns}
            noDataComponent={
              <NoDataComponent
                title="Secrets"
                description="Store API keys and secrets securely. Values are encrypted at rest and never shown after creation."
                buttonText="Add Secret"
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
