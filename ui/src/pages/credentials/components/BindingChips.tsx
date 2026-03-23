import { Chip, Stack, Typography } from "@mui/material";
import { BindingMeta } from "../types";

interface Props {
  bindings: BindingMeta[];
  onDelete: (logicalKey: string) => void;
}

export function BindingChips({ bindings, onDelete }: Props) {
  if (bindings.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary">
        No bindings — add one to alias a different key name to this credential.
      </Typography>
    );
  }

  return (
    <Stack direction="row" flexWrap="wrap" gap={1}>
      {bindings.map((b) => (
        <Chip
          key={b.logical_key}
          label={
            <span style={{ fontFamily: "monospace" }}>
              {b.logical_key} → {b.store_name}
            </span>
          }
          onDelete={() => onDelete(b.logical_key)}
          size="small"
          variant="outlined"
          color="primary"
        />
      ))}
    </Stack>
  );
}
