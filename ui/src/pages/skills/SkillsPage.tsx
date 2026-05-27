import { Box, Tooltip, Typography } from "@mui/material";
import { ArrowClockwise as RefreshIcon } from "@phosphor-icons/react";
import { Button, DataTable, NavLink, Paper } from "components";
import Header from "components/Header";
import NoDataComponent from "components/NoDataComponent";
import TagChip from "components/TagChip";
import { useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import SectionContainer from "shared/SectionContainer";
import SectionHeader from "shared/SectionHeader";
import SectionHeaderActions from "shared/SectionHeaderActions";
import { useFetch } from "utils/query";
import { SKILLS_URL } from "utils/constants/route";
import { LegacyColumn } from "components/DataTable/types";

export interface SkillSummary {
  name: string;
  version: string;
  description?: string;
  checksum?: string;
  status?: string;
  fileCount?: number;
  scriptCount?: number;
  subAgentCount?: number;
  resourceCount?: number;
  packageSize?: number;
}

function shortHash(value?: string) {
  return value ? value.slice(0, 12) : "";
}

function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function skillPath(skill: SkillSummary) {
  return `${SKILLS_URL.BASE}/${encodeURIComponent(skill.name)}/${encodeURIComponent(
    skill.version,
  )}`;
}

export default function SkillsPage() {
  const { data, isFetching, refetch } = useFetch<SkillSummary[]>("skills", {
    staleTime: 5000,
  });
  const [searchTerm, setSearchTerm] = useState("");
  const skills = data ?? [];
  const columns = useMemo<LegacyColumn[]>(
    () => [
      {
        id: "name",
        name: "name",
        label: "Name",
        sortable: true,
        searchable: true,
        grow: 1.3,
        renderer: (_name: string, skill: SkillSummary) => (
          <Box sx={{ minWidth: 0 }}>
            <NavLink path={skillPath(skill)}>{skill.name}</NavLink>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.25 }}
            >
              {skill.version}
            </Typography>
          </Box>
        ),
      },
      {
        id: "description",
        name: "description",
        label: "Description",
        sortable: true,
        searchable: true,
        grow: 2,
        renderer: (description?: string) => (
          <Tooltip
            title={description || ""}
            disableHoverListener={!description}
          >
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: 3,
                overflow: "hidden",
                lineHeight: 1.45,
              }}
            >
              {description || "No description"}
            </Typography>
          </Tooltip>
        ),
      },
      {
        id: "contents",
        name: "fileCount",
        label: "Contents",
        searchable: false,
        grow: 1.5,
        renderer: (_fileCount: number, skill: SkillSummary) => (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.75,
              flexWrap: "wrap",
              py: 0.5,
            }}
          >
            <TagChip size="small" label={`${skill.fileCount ?? 0} files`} />
            <TagChip
              size="small"
              label={`${skill.subAgentCount ?? 0} agents`}
            />
            <TagChip size="small" label={`${skill.scriptCount ?? 0} scripts`} />
            <TagChip
              size="small"
              label={`${skill.resourceCount ?? 0} resources`}
            />
          </Box>
        ),
      },
      {
        id: "status",
        name: "status",
        label: "Status",
        sortable: true,
        searchable: true,
        grow: 0.7,
        renderer: (status?: string) => (
          <TagChip size="small" label={status || "Unknown"} />
        ),
      },
      {
        id: "packageSize",
        name: "packageSize",
        label: "Size",
        sortable: true,
        searchable: false,
        grow: 0.5,
        renderer: (packageSize?: number) => (
          <Typography variant="body2" color="text.secondary">
            {formatBytes(packageSize)}
          </Typography>
        ),
      },
      {
        id: "checksum",
        name: "checksum",
        label: "Checksum",
        sortable: false,
        searchable: true,
        grow: 0.8,
        renderer: (checksum?: string) => (
          <Typography
            variant="body2"
            color="text.secondary"
            fontFamily="monospace"
            sx={{ whiteSpace: "nowrap" }}
          >
            {shortHash(checksum)}
          </Typography>
        ),
      },
      {
        id: "actions",
        name: "name",
        label: "Actions",
        sortable: false,
        searchable: false,
        grow: 0.4,
        renderer: (_name: string, skill: SkillSummary) => (
          <Button
            size="small"
            variant="text"
            href={skillPath(skill)}
            sx={{ textTransform: "none" }}
          >
            Browse
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <Helmet>
        <title>Skills</title>
      </Helmet>
      <SectionHeader
        _deprecate_marginTop={0}
        title="Skills"
        actions={
          <SectionHeaderActions
            buttons={[
              {
                label: "Refresh",
                color: "secondary",
                onClick: () => refetch(),
              },
            ]}
          />
        }
      />
      <SectionContainer>
        <Paper id="skills-table-wrapper" variant="outlined">
          <Header loading={isFetching} />
          {data && (
            <DataTable
              localStorageKey="skillsTable"
              quickSearchEnabled
              quickSearchPlaceholder="Search skills"
              searchTerm={searchTerm}
              onSearchTermChange={setSearchTerm}
              keyField="name"
              data={skills}
              columns={columns}
              defaultShowColumns={[
                "name",
                "description",
                "contents",
                "status",
                "packageSize",
                "checksum",
                "actions",
              ]}
              customActions={[
                <Tooltip title="Refresh skills" key="refreshSkills">
                  <Button
                    variant="text"
                    color="inherit"
                    size="small"
                    startIcon={<RefreshIcon />}
                    onClick={refetch as () => void}
                  >
                    Refresh
                  </Button>
                </Tooltip>,
              ]}
              noDataComponent={
                searchTerm === "" ? (
                  <NoDataComponent
                    title="Skills"
                    description="No skills registered yet. Use agentspan skill register to upload one."
                  />
                ) : (
                  <NoDataComponent
                    title="Empty"
                    description="No skills match the current search."
                    buttonText="Clear search"
                    buttonHandler={() => setSearchTerm("")}
                  />
                )
              }
            />
          )}
        </Paper>
      </SectionContainer>
    </>
  );
}
