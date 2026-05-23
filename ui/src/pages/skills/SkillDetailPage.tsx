import { Box, CircularProgress, Typography } from "@mui/material";
import {
  ArrowClockwise as RefreshIcon,
  ArrowLeft as BackIcon,
  Code as CodeIcon,
  File as FileIcon,
  FileText as FileTextIcon,
  FolderSimple as FolderIcon,
} from "@phosphor-icons/react";
import { Button, Paper } from "components";
import ConductorBreadcrumbs from "components/v1/ConductorBreadcrumbs";
import Header from "components/Header";
import TagChip from "components/TagChip";
import { fetchWithContext, useFetchContext } from "plugins/fetch";
import { useEffect, useMemo, useState } from "react";
import { Helmet } from "react-helmet";
import { useNavigate, useParams } from "react-router";
import { useFetch } from "utils/query";
import { SKILLS_URL } from "utils/constants/route";
import { SkillSummary } from "./SkillsPage";

interface SkillFileEntry {
  path: string;
  size: number;
  sha256?: string;
  contentType?: string;
}

interface SkillDetail extends SkillSummary {
  files?: SkillFileEntry[];
  rawConfig?: {
    skillMd?: string;
    scripts?: Record<string, unknown>;
    agentFiles?: Record<string, unknown>;
    resourceFiles?: string[];
  };
}

interface SkillFileContent {
  path: string;
  content?: string;
  contentBase64?: string;
  binary: boolean;
  size: number;
  contentType?: string;
}

const CODE_FONT_FAMILY = 'Menlo, Monaco, "Courier New", monospace';
const EXPLORER_BG = "#f7f8fb";
const EDITOR_BG = "#fbfbfd";

interface FileTreeNode {
  name: string;
  path: string;
  file?: SkillFileEntry;
  children?: FileTreeNode[];
}

function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(path: string) {
  if (path.endsWith(".md") || path.endsWith(".txt")) {
    return <FileTextIcon size={16} />;
  }
  if (
    path.startsWith("scripts/") ||
    path.endsWith(".py") ||
    path.endsWith(".sh")
  ) {
    return <CodeIcon size={16} />;
  }
  return <FileIcon size={16} />;
}

function buildFileTree(files: SkillFileEntry[]) {
  const root: FileTreeNode[] = [];

  for (const file of files) {
    const parts = file.path.split("/");
    let siblings = root;
    let currentPath = "";

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isFile = index === parts.length - 1;

      if (isFile) {
        siblings.push({ name: part, path: file.path, file });
        return;
      }

      let folder = siblings.find((node) => !node.file && node.name === part);
      if (!folder) {
        folder = {
          name: part,
          path: currentPath,
          children: [],
        };
        siblings.push(folder);
      }
      siblings = folder.children ?? [];
    });
  }

  const sortNodes = (nodes: FileTreeNode[]) => {
    nodes.sort((left, right) => {
      if (left.file?.path === "SKILL.md") return -1;
      if (right.file?.path === "SKILL.md") return 1;
      if (Boolean(left.file) !== Boolean(right.file)) {
        return left.file ? 1 : -1;
      }
      return left.name.localeCompare(right.name);
    });
    nodes.forEach((node) => {
      if (node.children) sortNodes(node.children);
    });
  };

  sortNodes(root);
  return root;
}

function languageLabel(path: string, contentType?: string) {
  if (path.endsWith(".md")) return "Markdown";
  if (path.endsWith(".py")) return "Python";
  if (path.endsWith(".sh")) return "Shell";
  if (path.endsWith(".html")) return "HTML";
  if (path.endsWith(".json")) return "JSON";
  return contentType ?? "Text";
}

function ExplorerTree({
  nodes,
  activePath,
  onSelect,
  level = 0,
}: {
  nodes: FileTreeNode[];
  activePath: string;
  onSelect: (path: string) => void;
  level?: number;
}) {
  return (
    <>
      {nodes.map((node) => {
        if (!node.file) {
          return (
            <Box key={node.path}>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.75,
                  minHeight: 28,
                  pl: 1 + level * 1.5,
                  pr: 1,
                  color: "#6b7280",
                  fontFamily: CODE_FONT_FAMILY,
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: 0,
                }}
              >
                <FolderIcon size={15} weight="fill" />
                <Typography
                  component="span"
                  sx={{
                    fontFamily: CODE_FONT_FAMILY,
                    fontSize: 12,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {node.name}
                </Typography>
              </Box>
              <ExplorerTree
                nodes={node.children ?? []}
                activePath={activePath}
                onSelect={onSelect}
                level={level + 1}
              />
            </Box>
          );
        }

        const selected = activePath === node.file.path;
        return (
          <Box
            component="button"
            type="button"
            aria-label={node.file.path}
            key={node.file.path}
            onClick={() => onSelect(node.file!.path)}
            sx={{
              width: "100%",
              minHeight: 34,
              border: "1px solid",
              borderColor: selected
                ? "rgba(73, 105, 228, 0.24)"
                : "transparent",
              borderRadius: 1,
              bgcolor: selected ? "#ffffff" : "transparent",
              boxShadow: selected
                ? "inset 3px 0 0 #4969e4, 0 1px 2px rgba(16, 24, 40, 0.06)"
                : "none",
              color: "text.primary",
              cursor: "pointer",
              display: "grid",
              gridTemplateColumns: "18px minmax(0, 1fr) auto",
              alignItems: "center",
              gap: 0.75,
              px: 1,
              py: 0.65,
              pl: 1 + level * 1.5,
              textAlign: "left",
              font: "inherit",
              "&:hover": {
                bgcolor: selected ? "#ffffff" : "rgba(255, 255, 255, 0.72)",
                borderColor: selected
                  ? "rgba(73, 105, 228, 0.28)"
                  : "rgba(0, 0, 0, 0.08)",
              },
            }}
          >
            <Box
              sx={{
                color: selected ? "primary.main" : "text.secondary",
                display: "flex",
                alignItems: "center",
              }}
            >
              {fileIcon(node.file.path)}
            </Box>
            <Typography
              component="span"
              sx={{
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontFamily: CODE_FONT_FAMILY,
                fontSize: 12.5,
                fontWeight: selected ? 700 : 500,
                lineHeight: 1.2,
                letterSpacing: 0,
              }}
            >
              {node.name}
            </Typography>
            <Typography
              component="span"
              sx={{
                color: "text.secondary",
                fontFamily: CODE_FONT_FAMILY,
                fontSize: 11,
                lineHeight: 1,
              }}
            >
              {formatBytes(node.file.size)}
            </Typography>
          </Box>
        );
      })}
    </>
  );
}

export default function SkillDetailPage() {
  const { name = "", version = "latest" } = useParams();
  const decodedName = decodeURIComponent(name);
  const decodedVersion = decodeURIComponent(version);
  const navigate = useNavigate();
  const { data, isFetching, refetch } = useFetch<SkillDetail>(
    `skills/${encodeURIComponent(decodedName)}/versions/${encodeURIComponent(decodedVersion)}`,
    { staleTime: 5000 },
  );
  const fetchContext = useFetchContext();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<SkillFileContent | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);

  const files = useMemo(() => data?.files ?? [], [data]);
  const fileTree = useMemo(() => buildFileTree(files), [files]);
  const activePath = selectedPath ?? "SKILL.md";
  const activeFile = files.find((file) => file.path === activePath);
  const previewContent = fileContent?.content ?? data?.rawConfig?.skillMd ?? "";
  const previewLines = useMemo(
    () => (previewContent ? previewContent.split(/\r\n|\n|\r/) : [""]),
    [previewContent],
  );

  useEffect(() => {
    setSelectedPath(null);
    setFileContent(null);
  }, [decodedName, decodedVersion]);

  const loadFile = async (path: string) => {
    setSelectedPath(path);
    setLoadingFile(true);
    try {
      const content = await fetchWithContext(
        `skills/${encodeURIComponent(decodedName)}/versions/${encodeURIComponent(
          data?.version ?? decodedVersion,
        )}/files?path=${encodeURIComponent(path)}`,
        fetchContext,
        { method: "GET" },
      );
      setFileContent(content as SkillFileContent);
    } finally {
      setLoadingFile(false);
    }
  };

  return (
    <>
      <Helmet>
        <title>{decodedName} Skill</title>
      </Helmet>

      <Box
        component="header"
        sx={{
          px: 2.5,
          py: 1.25,
          bgcolor: "#fff",
          boxShadow: "0 1px 6px rgba(0, 0, 0, 0.12)",
          position: "relative",
          zIndex: 1,
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: { xs: "flex-start", md: "center" },
            justifyContent: "space-between",
            gap: 2,
            flexDirection: { xs: "column", md: "row" },
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <ConductorBreadcrumbs
              items={[
                { label: "Skills", to: SKILLS_URL.BASE },
                { label: decodedName, to: "" },
              ]}
            />
            <Typography
              sx={{
                mt: 0.25,
                fontSize: "14pt",
                fontWeight: 700,
                lineHeight: 1.2,
                wordBreak: "break-word",
              }}
            >
              {decodedName}
            </Typography>
            {data?.description && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 0.5 }}
              >
                {data.description}
              </Typography>
            )}
          </Box>

          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              flexWrap: "wrap",
              flexShrink: 0,
            }}
          >
            <Button
              color="secondary"
              variant="outlined"
              startIcon={<BackIcon />}
              onClick={() => navigate(SKILLS_URL.BASE)}
            >
              Back
            </Button>
            <Button
              color="secondary"
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => refetch()}
            >
              Refresh
            </Button>
          </Box>
        </Box>
      </Box>

      <Box
        sx={{
          p: 2,
          height: "calc(100vh - 92px)",
          minHeight: 620,
          boxSizing: "border-box",
        }}
      >
        <Paper
          id="skill-detail-wrapper"
          variant="outlined"
          sx={{
            height: "100%",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            bgcolor: "#fff",
          }}
        >
          <Header loading={isFetching} />
          {!data ? (
            <Box sx={{ p: 3 }}>
              <CircularProgress size={20} />
            </Box>
          ) : (
            <>
              <Box
                sx={{
                  px: 2,
                  py: 1.25,
                  borderBottom: "1px solid",
                  borderColor: "divider",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 2,
                  flexWrap: "wrap",
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    flexWrap: "wrap",
                  }}
                >
                  <TagChip size="small" label={`Version ${data.version}`} />
                  <TagChip size="small" label={formatBytes(data.packageSize)} />
                  <TagChip
                    size="small"
                    label={`${data.fileCount ?? files.length} files`}
                  />
                  <TagChip
                    size="small"
                    label={`${Object.keys(data.rawConfig?.agentFiles ?? {}).length} agents`}
                  />
                  <TagChip
                    size="small"
                    label={`${Object.keys(data.rawConfig?.scripts ?? {}).length} scripts`}
                  />
                  <TagChip
                    size="small"
                    label={`${data.rawConfig?.resourceFiles?.length ?? 0} resources`}
                  />
                </Box>
              </Box>

              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: {
                    xs: "1fr",
                    md: "minmax(300px, 340px) minmax(0, 1fr)",
                  },
                  gridTemplateRows: {
                    xs: "280px minmax(420px, 1fr)",
                    md: "1fr",
                  },
                  minHeight: 0,
                  flex: 1,
                }}
              >
                <Box
                  sx={{
                    borderRight: { xs: 0, md: "1px solid rgba(0, 0, 0, 0.12)" },
                    borderBottom: {
                      xs: "1px solid rgba(0, 0, 0, 0.12)",
                      md: 0,
                    },
                    bgcolor: EXPLORER_BG,
                    display: "flex",
                    flexDirection: "column",
                    minWidth: 0,
                    minHeight: 0,
                  }}
                >
                  <Box
                    sx={{
                      px: 2,
                      py: 1.5,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      bgcolor: "rgba(255, 255, 255, 0.58)",
                    }}
                  >
                    <Typography
                      variant="subtitle2"
                      sx={{ fontWeight: 700, lineHeight: 1.2 }}
                    >
                      Files
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ fontFamily: CODE_FONT_FAMILY }}
                    >
                      {data.fileCount ?? files.length} files ·{" "}
                      {formatBytes(data.packageSize)}
                    </Typography>
                  </Box>

                  <Box
                    sx={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 0.35,
                      p: 1,
                      minHeight: 0,
                      flex: 1,
                      overflow: "auto",
                    }}
                  >
                    <ExplorerTree
                      nodes={fileTree}
                      activePath={activePath}
                      onSelect={loadFile}
                    />
                  </Box>
                </Box>

                <Box
                  sx={{
                    minWidth: 0,
                    minHeight: 0,
                    display: "flex",
                    flexDirection: "column",
                    bgcolor: "#fff",
                  }}
                >
                  <Box
                    sx={{
                      px: 2,
                      py: 1.25,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 2,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                    }}
                  >
                    <Box sx={{ minWidth: 0 }}>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          fontFamily: CODE_FONT_FAMILY,
                          fontWeight: 700,
                          letterSpacing: 0,
                        }}
                      >
                        {activePath}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ fontFamily: CODE_FONT_FAMILY }}
                      >
                        {languageLabel(
                          activePath,
                          activeFile?.contentType ?? fileContent?.contentType,
                        )}
                      </Typography>
                    </Box>
                    <TagChip
                      size="small"
                      label={formatBytes(fileContent?.size ?? activeFile?.size)}
                    />
                  </Box>

                  {loadingFile ? (
                    <Box sx={{ p: 3, bgcolor: EDITOR_BG, flex: 1 }}>
                      <CircularProgress size={20} />
                    </Box>
                  ) : fileContent?.binary ? (
                    <Box sx={{ p: 3, bgcolor: EDITOR_BG, flex: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        Binary file preview is not available. Size:{" "}
                        {formatBytes(fileContent.size)}.
                      </Typography>
                    </Box>
                  ) : (
                    <Box
                      component="pre"
                      sx={{
                        m: 0,
                        flex: 1,
                        minHeight: 0,
                        p: 0,
                        bgcolor: EDITOR_BG,
                        overflow: "auto",
                        fontFamily: CODE_FONT_FAMILY,
                        fontSize: 13,
                        lineHeight: 1.55,
                      }}
                    >
                      {previewLines.map((line, index) => (
                        <Box
                          key={index}
                          sx={{
                            display: "grid",
                            gridTemplateColumns: "48px minmax(0, 1fr)",
                            alignItems: "stretch",
                            minHeight: 20,
                          }}
                        >
                          <Box
                            aria-hidden
                            component="span"
                            sx={{
                              display: "block",
                              px: 1.5,
                              color: "text.disabled",
                              textAlign: "right",
                              borderRight: "1px solid",
                              borderColor: "divider",
                              bgcolor: "#f3f4f7",
                              userSelect: "none",
                            }}
                          >
                            {index + 1}
                          </Box>
                          <Box
                            component="code"
                            sx={{
                              display: "block",
                              minWidth: 0,
                              px: 1.25,
                              whiteSpace: "pre-wrap",
                              overflowWrap: "anywhere",
                              fontFamily: CODE_FONT_FAMILY,
                            }}
                          >
                            {line || " "}
                          </Box>
                        </Box>
                      ))}
                    </Box>
                  )}
                </Box>
              </Box>
            </>
          )}
        </Paper>
      </Box>
    </>
  );
}
