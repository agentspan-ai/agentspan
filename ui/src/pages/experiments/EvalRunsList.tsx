import { Box, Card, CardContent, Chip, LinearProgress, TextField, Typography } from "@mui/material";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import { DataTable } from "components";
import { useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import { useNavigate } from "react-router";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import { LegacyColumn } from "components/DataTable/types";
import { EXPERIMENTS_URL } from "utils/constants/route";
import { useEvalRuns, type EvalRun } from "./useEvalApi";

function PassRateBar({ run }: { run: EvalRun }) {
  const pct =
    run.totalCases > 0 ? Math.round((run.passedCases / run.totalCases) * 100) : 0;
  const color = pct === 100 ? "success" : pct >= 50 ? "warning" : "error";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <LinearProgress
        variant="determinate"
        value={pct}
        color={color}
        sx={{ width: 80, height: 6, borderRadius: 3 }}
      />
      <Typography variant="body2">
        {run.passedCases}/{run.totalCases}
      </Typography>
    </Box>
  );
}

function CaseBadges({ run }: { run: EvalRun }) {
  const failed = run.totalCases - run.passedCases;
  return (
    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
      {run.passedCases > 0 && (
        <Chip label={`${run.passedCases} pass`} size="small" color="success" variant="outlined" />
      )}
      {failed > 0 && (
        <Chip label={`${failed} fail`} size="small" color="error" variant="outlined" />
      )}
    </Box>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color?: string;
}) {
  return (
    <Card variant="outlined" sx={{ flex: 1 }}>
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Typography
          variant="caption"
          color="text.secondary"
          fontWeight={700}
          textTransform="uppercase"
          letterSpacing={0.5}
          display="block"
        >
          {label}
        </Typography>
        <Typography variant="h5" fontWeight={700} color={color ?? "text.primary"}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

const TAG = "allowRowEvents";

const columns: LegacyColumn[] = [
  {
    id: "name",
    name: "name",
    label: "Run Name",
    renderer: (val: string, row: EvalRun) => (
      <Typography variant="body2" fontWeight={600} data-tag={TAG}>
        {val || row.id?.slice(0, 8)}
      </Typography>
    ),
  },
  {
    id: "agentName",
    name: "agentName",
    label: "Agent",
    renderer: (val: string) =>
      val ? (
        <span data-tag={TAG}>
          <Chip label={val} size="small" variant="outlined" sx={{ fontFamily: "monospace", pointerEvents: "none" }} />
        </span>
      ) : (
        <span data-tag={TAG}>—</span>
      ),
  },
  {
    id: "passRate",
    name: "passedCases",
    label: "Pass Rate",
    renderer: (_val: number, row: EvalRun) => (
      <span data-tag={TAG}>
        <PassRateBar run={row} />
      </span>
    ),
  },
  {
    id: "cases",
    name: "totalCases",
    label: "Cases",
    renderer: (_val: number, row: EvalRun) => (
      <span data-tag={TAG}>
        <CaseBadges run={row} />
      </span>
    ),
  },
  {
    id: "strategyValid",
    name: "strategy",
    label: "Strategy Valid",
    renderer: (val: string) =>
      val ? (
        <span data-tag={TAG}>
          <Chip label={`✓ ${val}`} size="small" color="success" variant="outlined" sx={{ pointerEvents: "none" }} />
        </span>
      ) : (
        <Typography variant="body2" color="text.disabled" data-tag={TAG}>
          —
        </Typography>
      ),
  },
  {
    id: "timestamp",
    name: "timestamp",
    label: "Ran At",
    renderer: (val: string) => (
      <Typography variant="body2" color="text.secondary" data-tag={TAG}>
        {val ? new Date(val).toLocaleString() : "—"}
      </Typography>
    ),
  },
];

export default function EvalRunsList() {
  const navigate = useNavigate();
  const { data, isLoading } = useEvalRuns(0, 200);
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [resultFilter, setResultFilter] = useState("all");

  const allRows: EvalRun[] = data?.results ?? [];

  const agents = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.agentName).filter(Boolean))),
    [allRows],
  );

  const rows = useMemo(() => {
    return allRows.filter((r) => {
      const q = search.toLowerCase();
      const matchSearch =
        !q ||
        (r.name ?? "").toLowerCase().includes(q) ||
        (r.agentName ?? "").toLowerCase().includes(q);
      const matchAgent = agentFilter === "all" || r.agentName === agentFilter;
      const pct = r.totalCases > 0 ? r.passedCases / r.totalCases : 0;
      const matchResult =
        resultFilter === "all" ||
        (resultFilter === "passing" && pct === 1) ||
        (resultFilter === "failing" && pct < 1);
      return matchSearch && matchAgent && matchResult;
    });
  }, [allRows, search, agentFilter, resultFilter]);

  const passing = allRows.filter(
    (r) => r.passedCases === r.totalCases && r.totalCases > 0,
  ).length;
  const failing = allRows.length - passing;
  const avgPct =
    allRows.length > 0
      ? Math.round(
          (allRows.reduce(
            (s, r) => s + (r.totalCases > 0 ? r.passedCases / r.totalCases : 0),
            0,
          ) /
            allRows.length) *
            100,
        )
      : 0;

  return (
    <>
      <Helmet>
        <title>Eval Runs</title>
      </Helmet>
      <SectionHeader _deprecate_marginTop={0} title="Eval Runs" />
      <SectionContainer>
        {isLoading && <LinearProgress />}
        {!isLoading && (
          <>
            {/* Stats row */}
            <Box sx={{ display: "flex", gap: 1.5, mb: 2.5 }}>
              <StatCard label="Total Runs" value={allRows.length} color="primary.main" />
              <StatCard label="Passing" value={passing} color="success.main" />
              <StatCard label="Failing" value={failing} color="error.main" />
              <StatCard label="Avg Pass Rate" value={`${avgPct}%`} />
            </Box>

            {/* Filters */}
            <Box sx={{ display: "flex", gap: 1.5, mb: 2, alignItems: "center" }}>
              <TextField
                size="small"
                placeholder="Search by run name or agent…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                sx={{ width: 280 }}
              />
              <Select
                size="small"
                value={agentFilter}
                onChange={(e) => setAgentFilter(e.target.value)}
                sx={{ minWidth: 160 }}
              >
                <MenuItem value="all">All Agents</MenuItem>
                {agents.map((a) => (
                  <MenuItem key={a} value={a}>
                    {a}
                  </MenuItem>
                ))}
              </Select>
              <Select
                size="small"
                value={resultFilter}
                onChange={(e) => setResultFilter(e.target.value)}
                sx={{ minWidth: 160 }}
              >
                <MenuItem value="all">All Results</MenuItem>
                <MenuItem value="passing">Passing</MenuItem>
                <MenuItem value="failing">Failing</MenuItem>
              </Select>
            </Box>

            {allRows.length >= 200 && (
              <Typography variant="caption" color="warning.main" sx={{ px: 2, pt: 1.5, pb: 0, display: "block" }}>
                Showing the 200 most recent runs. Older runs may not be visible.
              </Typography>
            )}
            {rows.length === 0 ? (
              <Typography sx={{ p: 3, color: "text.secondary" }}>
                {allRows.length === 0
                  ? "No eval runs yet. Run an eval suite with the Python SDK to see results here."
                  : "No runs match the current filters."}
              </Typography>
            ) : (
              <DataTable
                title={`${rows.length} eval run${rows.length === 1 ? "" : "s"}`}
                columns={columns}
                data={rows}
                onRowClicked={(row: EvalRun) => {
                  if (row.id) navigate(EXPERIMENTS_URL.EVAL_RUNS + "/" + row.id);
                }}
                pointerOnHover
                highlightOnHover
                paginationPerPage={20}
                paginationRowsPerPageOptions={[10, 20, 50]}
              />
            )}
          </>
        )}
      </SectionContainer>
    </>
  );
}
