import {
  Box,
  Chip,
  Divider,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  Typography,
} from "@mui/material";
import { DataTable } from "components";
import { LegacyColumn } from "components/DataTable/types"; // used by caseColumns
import { Helmet } from "react-helmet";
import { useNavigate, useParams } from "react-router";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import { EXPERIMENTS_URL } from "utils/constants/route";
import { type Dataset, type DatasetCase, useDataset, useDatasets } from "./useEvalApi";


const caseColumns: LegacyColumn[] = [
  { id: "name", name: "name", label: "Case Name" },
  {
    id: "prompt",
    name: "prompt",
    label: "Prompt",
    renderer: (val: string) => (
      <Typography
        variant="body2"
        sx={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        title={val}
      >
        {val}
      </Typography>
    ),
  },
  {
    id: "semanticCriteria",
    name: "semanticCriteria",
    label: "Semantic Criterion",
    renderer: (val: string) =>
      val ? (
        <Typography
          variant="body2"
          sx={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          title={val}
        >
          {val}
        </Typography>
      ) : (
        <Typography variant="body2" color="text.disabled">
          —
        </Typography>
      ),
  },
  {
    id: "assertions",
    name: "assertions",
    label: "Assertions",
    renderer: (val: string[]) =>
      val?.length ? (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
          {val.map((a, i) => (
            <Chip key={i} label={a} size="small" variant="outlined" />
          ))}
        </Box>
      ) : (
        "—"
      ),
  },
  {
    id: "tags",
    name: "tags",
    label: "Tags",
    renderer: (val: string[]) =>
      val?.length ? (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
          {val.map((t, i) => (
            <Chip key={i} label={t} size="small" />
          ))}
        </Box>
      ) : (
        "—"
      ),
  },
];

function DatasetDetailPanel({ name }: { name: string }) {
  const { data: dataset, isLoading } = useDataset(decodeURIComponent(name));
  const rows: DatasetCase[] = dataset?.cases ?? [];

  return (
    <Box sx={{ flex: 1, minWidth: 0, pl: 2 }}>
      {isLoading && <LinearProgress />}
      {dataset && (
        <>
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle1" fontWeight={700}>
              {dataset.name}
            </Typography>
            <Box sx={{ display: "flex", gap: 2, mt: 0.5, flexWrap: "wrap" }}>
              {dataset.updatedAt && (
                <Typography variant="caption" color="text.secondary">
                  Last updated: {new Date(dataset.updatedAt).toLocaleString()}
                </Typography>
              )}
              {dataset.pushedBy && (
                <Typography variant="caption" color="text.secondary">
                  Pushed by: <strong>{dataset.pushedBy}</strong>
                </Typography>
              )}
            </Box>
          </Box>
          {rows.length === 0 ? (
            <Typography color="text.secondary">No cases in this dataset.</Typography>
          ) : (
            <DataTable
              title={`${rows.length} case${rows.length === 1 ? "" : "s"}`}
              columns={caseColumns}
              data={rows}
              paginationPerPage={20}
              paginationRowsPerPageOptions={[10, 20, 50]}
            />
          )}
        </>
      )}
    </Box>
  );
}

export default function DatasetsList() {
  const navigate = useNavigate();
  const { name: selectedName } = useParams<{ name?: string }>();
  const { data: datasets, isLoading } = useDatasets();

  const rows: Dataset[] = datasets ?? [];

  return (
    <>
      <Helmet>
        <title>Datasets</title>
      </Helmet>
      <SectionHeader _deprecate_marginTop={0} title="Datasets" />
      <SectionContainer>
        {isLoading && !rows.length ? (
          <LinearProgress />
        ) : !rows.length ? (
          <Typography sx={{ p: 3, color: "text.secondary" }}>
            No datasets yet. Push a dataset with{" "}
            <code>runtime.push_dataset(name, cases)</code> from the Python SDK.
          </Typography>
        ) : (
          <Box sx={{ display: "flex", gap: 0, alignItems: "flex-start" }}>
            {/* Left sidebar — dataset list */}
            <Box
              sx={{
                width: 240,
                flexShrink: 0,
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                bgcolor: "background.paper",
              }}
            >
              <Typography
                variant="caption"
                fontWeight={700}
                color="text.secondary"
                textTransform="uppercase"
                letterSpacing={0.5}
                sx={{ display: "block", px: 2, pt: 1.5, pb: 0.5 }}
              >
                {rows.length} dataset{rows.length !== 1 ? "s" : ""}
              </Typography>
              <List dense disablePadding>
                {rows.map((row) => {
                  const isSelected =
                    !!selectedName && decodeURIComponent(selectedName) === row.name;
                  return (
                    <ListItemButton
                      key={row.name}
                      selected={isSelected}
                      onClick={() => {
                        if (row.name)
                          navigate(
                            EXPERIMENTS_URL.DATASETS + "/" + encodeURIComponent(row.name),
                          );
                      }}
                      sx={{
                        borderLeft: "3px solid",
                        borderColor: isSelected ? "secondary.main" : "transparent",
                        "&.Mui-selected": { bgcolor: "rgba(91,106,240,0.07)" },
                      }}
                    >
                      <ListItemText
                        primary={
                          <Typography variant="body2" fontWeight={isSelected ? 700 : 400} noWrap>
                            {row.name}
                          </Typography>
                        }
                        secondary={
                          <Typography variant="caption" color="text.secondary">
                            {row.caseCount ?? 0} cases
                            {row.updatedAt
                              ? ` · ${new Date(row.updatedAt).toLocaleDateString()}`
                              : ""}
                          </Typography>
                        }
                      />
                    </ListItemButton>
                  );
                })}
              </List>
            </Box>
            {selectedName && (
              <>
                <Divider orientation="vertical" flexItem sx={{ mx: 2 }} />
                <DatasetDetailPanel name={selectedName} />
              </>
            )}
            {!selectedName && (
              <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "text.disabled", pt: 6 }}>
                <Typography variant="body2">Select a dataset to view its cases</Typography>
              </Box>
            )}
          </Box>
        )}
      </SectionContainer>
    </>
  );
}
