/**
 * AgentDetailPanel — right-hand panel for the agent execution diagram.
 * Styled like the Conductor workflow RightPanel.
 * Shows Input/Output with smart rendering (markdown, JSON tab).
 */
import { useState } from "react";
import { Box, Paper, Typography, IconButton } from "@mui/material";
import { X as CloseIcon } from "@phosphor-icons/react";
import { Tab, Tabs } from "components";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentEvent, AgentRunData, AgentStatus, EventType } from "./types";

// ─── Simple JSON viewer (replaces Monaco for inline display) ─────────────────

function JsonView({ src }: { src: unknown }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 1.5,
        fontSize: "0.78rem",
        lineHeight: 1.6,
        fontFamily: "monospace",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        color: "text.primary",
        backgroundColor: "#f8f9fa",
        borderRadius: 1,
        overflowY: "auto",
        maxHeight: 400,
      }}
    >
      {JSON.stringify(src, null, 2)}
    </Box>
  );
}

// ─── Types ──────────────────────────────────────────────────────────────────

export interface DetailNodeData {
  kind: "llm" | "tool" | "handoff" | "subagent" | "output" | "error" | "start";
  label: string;
  status: AgentStatus;
  event?: AgentEvent;
  subAgentRun?: AgentRunData;
}

// ─── Smart output resolver ───────────────────────────────────────────────────

/**
 * If the object has a single key "result", unwrap it.
 * Handles: { result: "..." } → "..."
 */
function unwrapResult(value: unknown): unknown {
  if (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
  ) {
    const keys = Object.keys(value as object);
    if (keys.length === 1 && keys[0] === "result") {
      return (value as any).result;
    }
  }
  return value;
}

function looksLikeMarkdown(text: string): boolean {
  return /^#{1,6}\s|\*\*[^*]+\*\*|^[-*]\s|\n#{1,6}\s|^\d+\.\s|^>\s/m.test(text);
}

// ─── Markdown renderer ───────────────────────────────────────────────────────

function MarkdownView({ content }: { content: string }) {
  return (
    <Box
      sx={{
        "& h1,& h2,& h3": { fontWeight: 700, mt: 1.5, mb: 0.75, lineHeight: 1.3 },
        "& h1": { fontSize: "1rem" },
        "& h2": { fontSize: "0.9rem" },
        "& h3": { fontSize: "0.85rem" },
        "& p": { my: 0.75, lineHeight: 1.6, fontSize: "0.82rem" },
        "& ul,& ol": { pl: 2.5, my: 0.5 },
        "& li": { fontSize: "0.82rem", lineHeight: 1.5 },
        "& code": {
          backgroundColor: "grey.100",
          borderRadius: 0.5,
          px: 0.5,
          py: 0.1,
          fontFamily: "monospace",
          fontSize: "0.78rem",
        },
        "& pre": {
          backgroundColor: "grey.100",
          borderRadius: 1,
          p: 1.5,
          overflowX: "auto",
          my: 1,
          "& code": { backgroundColor: "transparent", p: 0 },
        },
        "& blockquote": {
          borderLeft: "3px solid",
          borderColor: "divider",
          pl: 1.5,
          my: 0.75,
          color: "text.secondary",
        },
        "& strong": { fontWeight: 700 },
        "& a": { color: "primary.main" },
        "& table": { borderCollapse: "collapse", width: "100%", my: 1 },
        "& th,& td": { border: "1px solid", borderColor: "divider", px: 1, py: 0.5, fontSize: "0.8rem" },
        "& th": { backgroundColor: "grey.50", fontWeight: 600 },
      }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </Box>
  );
}

// ─── Output content renderer ─────────────────────────────────────────────────

const OUTPUT_TAB = "output";
const JSON_TAB = "json";

function SmartOutputPanel({
  raw,
  label = "Output",
}: {
  raw: unknown;
  label?: string;
}) {
  const [tab, setTab] = useState(OUTPUT_TAB);

  const unwrapped = unwrapResult(raw);
  const isString = typeof unwrapped === "string";
  const isMarkdown = isString && looksLikeMarkdown(unwrapped as string);

  return (
    <Box>
      <Tabs
        value={tab}
        contextual
        variant="scrollable"
        scrollButtons="auto"
        style={{ borderBottom: "1px solid rgba(0,0,0,.1)", marginBottom: 0 }}
      >
        <Tab
          label={label}
          value={OUTPUT_TAB}
          onClick={() => setTab(OUTPUT_TAB)}
        />
        <Tab
          label="JSON"
          value={JSON_TAB}
          onClick={() => setTab(JSON_TAB)}
        />
      </Tabs>

      <Box sx={{ p: 2 }}>
        {tab === OUTPUT_TAB ? (
          isMarkdown ? (
            <MarkdownView content={unwrapped as string} />
          ) : isString ? (
            <Typography
              component="pre"
              sx={{
                fontFamily: "monospace",
                fontSize: "0.8rem",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                m: 0,
                lineHeight: 1.6,
              }}
            >
              {unwrapped as string}
            </Typography>
          ) : (
            <JsonView src={unwrapped} />
          )
        ) : (
          /* JSON tab — always shows raw full value */
          <JsonView src={raw} />
        )}
      </Box>
    </Box>
  );
}

const ACCENT = "#40BA56";
const RED    = "#DD2222";
const AMBER  = "#f59e0b";

// ─── Section label ────────────────────────────────────────────────────────────

function SectionLabel({ children, accent = ACCENT }: { children: React.ReactNode; accent?: string }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        px: 2,
        py: 0.75,
        borderBottom: "1px solid",
        borderColor: "divider",
        backgroundColor: "#fafafa",
        borderLeft: `2px solid ${accent}`,
      }}
    >
      <Typography
        sx={{
          fontSize: "0.65rem",
          fontWeight: 600,
          letterSpacing: "0.05em",
          textTransform: "uppercase",
          color: "text.secondary",
          lineHeight: 1,
        }}
      >
        {children}
      </Typography>
    </Box>
  );
}

// ─── Input section ────────────────────────────────────────────────────────────

function InputSection({ input }: { input: unknown }) {
  return (
    <Box>
      <SectionLabel accent="#9e9e9e">Input</SectionLabel>
      <Box sx={{ p: 1.5 }}>
        {typeof input === "object" && input !== null ? (
          <JsonView src={input} />
        ) : (
          <Typography
            component="pre"
            sx={{ fontFamily: "monospace", fontSize: "0.78rem", whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0, color: "text.primary" }}
          >
            {String(input ?? "")}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

// ─── Status indicator ────────────────────────────────────────────────────────

function StatusDot({ status }: { status: AgentStatus }) {
  const color =
    status === AgentStatus.COMPLETED ? ACCENT :
    status === AgentStatus.FAILED    ? RED :
    status === AgentStatus.RUNNING   ? AMBER : "#9e9e9e";

  const label =
    status === AgentStatus.COMPLETED ? "Completed" :
    status === AgentStatus.FAILED    ? "Failed" :
    status === AgentStatus.RUNNING   ? "Running" : "Waiting";

  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 1,
        py: 0.25,
        borderRadius: 1,
        backgroundColor: `${color}20`,
        border: `1px solid ${color}60`,
      }}
    >
      <Box
        sx={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          backgroundColor: color,
          flexShrink: 0,
        }}
      />
      <Typography variant="caption" sx={{ fontWeight: 600, color, fontSize: "0.7rem" }}>
        {label}
      </Typography>
    </Box>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────

interface AgentDetailPanelProps {
  node: DetailNodeData;
  onClose: () => void;
}

export function AgentDetailPanel({ node, onClose }: AgentDetailPanelProps) {
  const ev = node.event;
  const detail = ev?.detail as any;
  const hasInputOutput =
    detail &&
    typeof detail === "object" &&
    ("input" in detail || "output" in detail);

  return (
    <Paper
      square
      elevation={0}
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        borderLeft: "1px solid",
        borderColor: "divider",
        backgroundColor: "#fff",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2,
          py: 1.25,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          gap: 1,
          flexShrink: 0,
          backgroundColor: "#fafafa",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Kind label — tiny, muted */}
          <Typography
            sx={{
              fontSize: "0.65rem",
              fontWeight: 500,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              color: "text.disabled",
              lineHeight: 1,
              mb: 0.4,
            }}
          >
            {node.kind.replace("-", " ")}
          </Typography>
          {/* Node label */}
          <Typography
            sx={{
              fontWeight: 700,
              fontSize: "0.9rem",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              lineHeight: 1.2,
              color: "text.primary",
            }}
          >
            {node.label}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
          <StatusDot status={node.status} />
          <IconButton
            size="small"
            onClick={onClose}
            sx={{
              width: 24, height: 24,
              color: "text.disabled",
              "&:hover": { color: "text.primary" },
            }}
          >
            <CloseIcon size={14} />
          </IconButton>
        </Box>
      </Box>

      {/* Scrollable content */}
      <Box sx={{
        flex: 1, overflowY: "auto", minHeight: 0,
        scrollbarWidth: "thin",
        scrollbarColor: "#e2e8f0 transparent",
        "&::-webkit-scrollbar": { width: 4 },
        "&::-webkit-scrollbar-track": { background: "transparent" },
        "&::-webkit-scrollbar-thumb": { background: "#e2e8f0", borderRadius: 2 },
      }}>
        {/* Sub-agent detail */}
        {node.kind === "subagent" && node.subAgentRun && (
          <Box>
            {node.subAgentRun.input && (
              <InputSection input={node.subAgentRun.input} />
            )}
            {node.subAgentRun.output && (
              <>
                <SectionLabel accent={ACCENT}>Output</SectionLabel>
                <SmartOutputPanel raw={node.subAgentRun.output} label="Output" />
              </>
            )}
            {node.subAgentRun.failureReason && (
              <Box sx={{ p: 2 }}>
                <Typography variant="caption" sx={{ color: "#DD2222", fontFamily: "monospace", display: "block" }}>
                  {node.subAgentRun.failureReason}
                </Typography>
              </Box>
            )}
          </Box>
        )}

        {/* Event detail (LLM, Tool, etc.) */}
        {ev && hasInputOutput && (
          <>
            {detail.input && <InputSection input={detail.input} />}
            {detail.output !== undefined && (
              <>
                <SectionLabel accent={ACCENT}>Output</SectionLabel>
                <SmartOutputPanel raw={detail.output} label="Output" />
              </>
            )}
          </>
        )}

        {/* Plain detail (output/done event with string content) */}
        {ev && !hasInputOutput && ev.detail != null && (
          <SmartOutputPanel raw={ev.detail} label="Output" />
        )}
      </Box>
    </Paper>
  );
}

export default AgentDetailPanel;
