/**
 * AgentDetailPanel — right-hand panel matching Conductor's task detail style.
 * Tabs: Summary | Input | Output | JSON
 */
import { useState, useRef } from "react";
import { Box, Paper, Typography, IconButton } from "@mui/material";
import { X as CloseIcon, ArrowRight } from "@phosphor-icons/react";
import { Tab, Tabs } from "components";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentEvent, AgentRunData, AgentStatus, EventType } from "./types";
import { formatTokens, formatDuration } from "./agentExecutionUtils";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DetailNodeData {
  kind: "llm" | "tool" | "handoff" | "subagent" | "output" | "error" | "start";
  label: string;
  status: AgentStatus;
  event?: AgentEvent;
  subAgentRun?: AgentRunData;
}

// ─── Tab keys ────────────────────────────────────────────────────────────────

const SUMMARY_TAB = "summary";
const INPUT_TAB   = "input";
const OUTPUT_TAB  = "output";
const JSON_TAB    = "json";

// ─── JSON editor viewer (Monaco, fills available height) ─────────────────────

function JsonView({ src }: { src: unknown }) {
  const json = JSON.stringify(src, null, 2);
  return (
    <Editor
      height="100%"
      language="json"
      value={json}
      options={{
        readOnly: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        lineNumbers: "off",
        folding: true,
        wordWrap: "on",
        fontSize: 12,
        renderLineHighlight: "none",
        overviewRulerLanes: 0,
        renderIndentGuides: false,
      } as any}
      theme="vs"
    />
  );
}

// ─── Markdown renderer ────────────────────────────────────────────────────────

function looksLikeMarkdown(text: string): boolean {
  return /^#{1,6}\s|\*\*[^*]+\*\*|^[-*]\s|\n#{1,6}\s|^\d+\.\s|^>\s/m.test(text);
}

function MarkdownView({ content }: { content: string }) {
  return (
    <Box sx={{
      "& h1,& h2,& h3": { fontWeight: 700, mt: 1.5, mb: 0.75, lineHeight: 1.3 },
      "& h1": { fontSize: "1rem" }, "& h2": { fontSize: "0.9rem" }, "& h3": { fontSize: "0.85rem" },
      "& p": { my: 0.75, lineHeight: 1.6, fontSize: "0.875rem" },
      "& ul,& ol": { pl: 2.5, my: 0.5 },
      "& li": { fontSize: "0.875rem", lineHeight: 1.5 },
      "& code": { backgroundColor: "#f1f5f9", borderRadius: 0.5, px: 0.5, fontFamily: "monospace", fontSize: "0.8rem" },
      "& pre": { backgroundColor: "#f1f5f9", borderRadius: 1, p: 1.5, overflowX: "auto", my: 1, "& code": { backgroundColor: "transparent", p: 0 } },
      "& blockquote": { borderLeft: "3px solid", borderColor: "divider", pl: 1.5, my: 0.75, color: "text.secondary" },
      "& strong": { fontWeight: 700 },
      "& a": { color: "primary.main" },
      "& table": { borderCollapse: "collapse", width: "100%", my: 1 },
      "& th,& td": { border: "1px solid", borderColor: "divider", px: 1, py: 0.5, fontSize: "0.875rem" },
      "& th": { backgroundColor: "grey.50", fontWeight: 600 },
    }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </Box>
  );
}

// ─── Smart content renderer (text/markdown/JSON) ──────────────────────────────

function ContentView({ value, label }: { value: unknown; label?: string }) {
  if (value == null) {
    return (
      <Typography variant="body2" color="text.disabled" sx={{ py: 2, textAlign: "center", fontSize: "0.875rem" }}>
        No {label ?? "data"}
      </Typography>
    );
  }
  if (typeof value === "string") {
    if (looksLikeMarkdown(value)) return <MarkdownView content={value} />;
    return (
      <Box component="pre" sx={{ m: 0, fontFamily: "monospace", fontSize: "0.8rem", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.6 }}>
        {value}
      </Box>
    );
  }
  return <JsonView src={value} />;
}

// ─── Summary key-value row (matches Conductor's KeyValueTable style) ──────────

function SummaryRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "" || value === undefined) return null;
  return (
    <Box sx={{
      display: "flex", alignItems: "flex-start",
      px: 3, py: 1.5,
      borderBottom: "1px solid rgba(0,0,0,0.1)",
      gap: 2,
    }}>
      <Typography sx={{ opacity: 0.7, fontSize: "0.875rem", minWidth: 140, flexShrink: 0 }}>
        {label}
      </Typography>
      <Box sx={{ fontSize: "0.875rem", color: "text.primary", wordBreak: "break-word" }}>
        {value}
      </Box>
    </Box>
  );
}

// ─── Status text (plain colored text, no pill) ────────────────────────────────

function StatusBadgeInline({ status }: { status: AgentStatus }) {
  const color =
    status === AgentStatus.COMPLETED ? "#40BA56" :
    status === AgentStatus.FAILED    ? "#DD2222" :
    status === AgentStatus.RUNNING   ? "#f59e0b" : "#9e9e9e";
  const label =
    status === AgentStatus.COMPLETED ? "Completed" :
    status === AgentStatus.FAILED    ? "Failed"    :
    status === AgentStatus.RUNNING   ? "Running"   : "Waiting";
  return <span style={{ color, fontWeight: 600, fontSize: "0.875rem" }}>{label}</span>;
}

// ─── Agent definition section ─────────────────────────────────────────────────

function AgentDefSection({ agentDef }: { agentDef: Record<string, unknown> }) {
  const instructions = (agentDef.instructions ?? agentDef.description) as string | undefined;
  const tools = agentDef.tools as Array<{ name: string } | string> | undefined;
  const defModel = agentDef.model as string | undefined;

  if (!instructions && !tools?.length && !defModel) return null;

  return (
    <Box sx={{ borderTop: "1px solid rgba(0,0,0,0.06)", mt: 1 }}>
      <Typography sx={{
        px: 3, pt: 1.5, pb: 0.5,
        fontSize: "0.65rem", fontWeight: 600,
        color: "#4969e4", textTransform: "uppercase", letterSpacing: "0.06em",
      }}>
        Agent Definition
      </Typography>
      {defModel && <SummaryRow label="Configured model" value={defModel} />}
      {tools && tools.length > 0 && (
        <SummaryRow
          label={`Tools (${tools.length})`}
          value={
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {tools.slice(0, 12).map((t, i) => (
                <Box key={i} sx={{
                  px: 0.75, py: 0.25, borderRadius: 0.5,
                  backgroundColor: "#f0f4ff", border: "1px solid #d1d9f5",
                  fontSize: "0.72rem", color: "#4969e4",
                }}>
                  {typeof t === "string" ? t : (t as any).name ?? JSON.stringify(t)}
                </Box>
              ))}
              {tools.length > 12 && (
                <Box sx={{ fontSize: "0.72rem", color: "text.secondary", alignSelf: "center" }}>
                  +{tools.length - 12} more
                </Box>
              )}
            </Box>
          }
        />
      )}
      {instructions && (
        <SummaryRow
          label="Instructions"
          value={
            <Box component="pre" sx={{
              m: 0, fontSize: "0.78rem", fontFamily: "inherit",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
              color: "text.secondary", lineHeight: 1.5,
              maxHeight: 120, overflowY: "auto",
            }}>
              {instructions.slice(0, 400)}{instructions.length > 400 ? "…" : ""}
            </Box>
          }
        />
      )}
    </Box>
  );
}

// ─── Summary tab content per node kind ──────────────────────────────────────

function SummaryContent({ node, onDrillIn }: { node: DetailNodeData; onDrillIn?: (run: AgentRunData) => void }) {
  const ev = node.event;
  const detail = ev?.detail as any;

  if (node.kind === "start" && node.subAgentRun) {
    const run = node.subAgentRun;
    const pt = run.totalTokens.promptTokens;
    const ct = run.totalTokens.completionTokens;
    return (
      <Box>
        <SummaryRow label="Agent" value={run.agentName} />
        {run.model && <SummaryRow label="Model" value={run.model} />}
        <SummaryRow label="Status" value={<StatusBadgeInline status={run.status} />} />
        {run.totalDurationMs > 0 && <SummaryRow label="Duration" value={formatDuration(run.totalDurationMs)} />}
        {(pt + ct) > 0 && <SummaryRow label="Total tokens" value={formatTokens(pt + ct)} />}
        {pt > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(pt)} />}
        {ct > 0 && <SummaryRow label="Completion tokens" value={formatTokens(ct)} />}
        {run.finishReason && <SummaryRow label="Finish reason" value={run.finishReason} />}
        {onDrillIn && (
          <Box sx={{ px: 3, py: 1.5 }}>
            <Box
              onClick={() => onDrillIn(run)}
              sx={{
                display: "inline-flex", alignItems: "center", gap: 0.75,
                px: 1.5, py: 0.75,
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: 500,
                color: "#fff",
                backgroundColor: "#4969e4",
                transition: "all 0.15s",
                "&:hover": { backgroundColor: "#3858d6", borderColor: "#3858d6" },
              }}
            >
              View full execution
              <ArrowRight size={14} />
            </Box>
          </Box>
        )}
        {run.agentDef && <AgentDefSection agentDef={run.agentDef} />}
      </Box>
    );
  }

  if (node.kind === "llm") {
    const tok = ev?.tokens;
    return (
      <Box>
        <SummaryRow label="Kind" value="LLM Call" />
        <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
        {ev?.toolName && <SummaryRow label="Model" value={ev.toolName} />}
        {tok && (tok.promptTokens + tok.completionTokens) > 0 && <SummaryRow label="Total tokens" value={formatTokens(tok.promptTokens + tok.completionTokens)} />}
        {tok && tok.promptTokens > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(tok.promptTokens)} />}
        {tok && tok.completionTokens > 0 && <SummaryRow label="Completion tokens" value={formatTokens(tok.completionTokens)} />}
        {ev?.durationMs && <SummaryRow label="Duration" value={formatDuration(ev.durationMs)} />}
      </Box>
    );
  }

  if (node.kind === "tool") {
    return (
      <Box>
        <SummaryRow label="Tool" value={ev?.toolName ?? node.label} />
        <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
        {ev?.durationMs && <SummaryRow label="Duration" value={formatDuration(ev.durationMs)} />}
      </Box>
    );
  }

  if (node.kind === "handoff") {
    return (
      <Box>
        <SummaryRow label="Target agent" value={ev?.targetAgent ?? node.label} />
        <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
      </Box>
    );
  }

  if (node.kind === "subagent" && node.subAgentRun) {
    const run = node.subAgentRun;
    const pt = run.totalTokens.promptTokens;
    const ct = run.totalTokens.completionTokens;
    return (
      <Box>
        <SummaryRow label="Agent" value={run.agentName} />
        {run.model && <SummaryRow label="Model" value={run.model} />}
        <SummaryRow label="Status" value={<StatusBadgeInline status={run.status} />} />
        {run.totalDurationMs > 0 && <SummaryRow label="Duration" value={formatDuration(run.totalDurationMs)} />}
        {(pt + ct) > 0 && <SummaryRow label="Total tokens" value={formatTokens(pt + ct)} />}
        {pt > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(pt)} />}
        {ct > 0 && <SummaryRow label="Completion tokens" value={formatTokens(ct)} />}
        {onDrillIn && (
          <Box sx={{ px: 3, py: 1.5 }}>
            <Box
              onClick={() => onDrillIn(run)}
              sx={{
                display: "inline-flex", alignItems: "center", gap: 0.75,
                px: 1.5, py: 0.75,
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: 500,
                color: "#fff",
                backgroundColor: "#4969e4",
                transition: "all 0.15s",
                "&:hover": { backgroundColor: "#3858d6", borderColor: "#3858d6" },
              }}
            >
              View full execution
              <ArrowRight size={14} />
            </Box>
          </Box>
        )}
        {run.agentDef && <AgentDefSection agentDef={run.agentDef} />}
      </Box>
    );
  }

  // output / error / fallback
  return (
    <Box>
      <SummaryRow label="Kind" value={node.kind} />
      <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
      {ev?.summary && <SummaryRow label="Summary" value={ev.summary} />}
    </Box>
  );
}

// ─── Resolve input value for a node ─────────────────────────────────────────

function resolveInput(node: DetailNodeData): unknown {
  if (node.kind === "start" && node.subAgentRun) return node.subAgentRun.input;
  if (node.kind === "subagent" && node.subAgentRun) return node.subAgentRun.input;
  const detail = node.event?.detail as any;
  if (detail && typeof detail === "object" && "input" in detail) return detail.input;
  if (node.event?.type === EventType.TOOL_CALL) return (node.event.detail as any)?.input;
  return null;
}

function resolveOutput(node: DetailNodeData): unknown {
  if (node.kind === "start" && node.subAgentRun) return node.subAgentRun.output;
  if (node.kind === "subagent" && node.subAgentRun) return node.subAgentRun.output;
  const detail = node.event?.detail as any;
  if (detail && typeof detail === "object" && "output" in detail) return detail.output;
  if (node.event?.type === EventType.DONE) return detail;
  return null;
}

function resolveJsonData(node: DetailNodeData): unknown {
  if (node.kind === "start" && node.subAgentRun) {
    const r = node.subAgentRun;
    return { agentName: r.agentName, model: r.model, status: r.status, tokens: r.totalTokens, durationMs: r.totalDurationMs, finishReason: r.finishReason };
  }
  if (node.kind === "subagent" && node.subAgentRun) {
    const r = node.subAgentRun;
    return { agentName: r.agentName, model: r.model, status: r.status, tokens: r.totalTokens, durationMs: r.totalDurationMs };
  }
  return node.event?.detail ?? null;
}

// ─── Main panel ───────────────────────────────────────────────────────────────

interface AgentDetailPanelProps {
  node: DetailNodeData;
  onClose: () => void;
  onDrillIn?: (run: AgentRunData) => void;
}

const KIND_DISPLAY: Record<DetailNodeData["kind"], string> = {
  start:    "Agent",
  subagent: "Sub-agent",
  llm:      "LLM Call",
  tool:     "Tool Call",
  handoff:  "Handoff",
  output:   "Output",
  error:    "Error",
};

export function AgentDetailPanel({ node, onClose, onDrillIn }: AgentDetailPanelProps) {
  const [tab, setTab] = useState(SUMMARY_TAB);

  // Reset to summary whenever a different node is opened
  const prevNodeId = useRef(node.label + node.kind);
  if (prevNodeId.current !== node.label + node.kind) {
    prevNodeId.current = node.label + node.kind;
    setTab(SUMMARY_TAB);
  }

  const inputValue  = resolveInput(node);
  const outputValue = resolveOutput(node);
  const jsonData    = resolveJsonData(node);

  const hasInput  = inputValue  != null;
  const hasOutput = outputValue != null;

  return (
    <Paper
      square elevation={0}
      sx={{
        height: "100%", display: "flex", flexDirection: "column",
        overflow: "hidden", borderLeft: "1px solid", borderColor: "divider",
        backgroundColor: "#fff",
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <Box sx={{
        px: 2.5, pt: 2, pb: 1.5,
        borderBottom: "1px solid", borderColor: "divider",
        flexShrink: 0, backgroundColor: "#fff",
      }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{
              fontSize: "0.65rem", fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "text.disabled", lineHeight: 1, mb: 0.5,
            }}>
              {KIND_DISPLAY[node.kind]}
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography sx={{
                fontWeight: 700, fontSize: "1rem", lineHeight: 1.2,
                color: "text.primary", wordBreak: "break-word",
              }}>
                {node.label}
              </Typography>
              <StatusBadgeInline status={node.status} />
            </Box>
          </Box>
          <IconButton
            size="small" onClick={onClose}
            sx={{ width: 26, height: 26, color: "text.disabled", flexShrink: 0, "&:hover": { color: "text.primary" } }}
          >
            <CloseIcon size={14} />
          </IconButton>
        </Box>
      </Box>

      {/* ── Tabs ──────────────────────────────────────────────────────── */}
      <Box sx={{ flexShrink: 0 }}>
        <Tabs
          value={tab}
          contextual
          variant="scrollable"
          scrollButtons="auto"
          style={{ marginBottom: 0 }}
        >
          {[
            <Tab key="summary" label="Summary" value={SUMMARY_TAB} onClick={() => setTab(SUMMARY_TAB)} />,
            hasInput  ? <Tab key="input"  label="Input"  value={INPUT_TAB}  onClick={() => setTab(INPUT_TAB)}  /> : null,
            hasOutput ? <Tab key="output" label="Output" value={OUTPUT_TAB} onClick={() => setTab(OUTPUT_TAB)} /> : null,
            <Tab key="json"    label="JSON"    value={JSON_TAB}    onClick={() => setTab(JSON_TAB)} />,
          ].filter(Boolean)}
        </Tabs>
      </Box>

      {/* ── Content ───────────────────────────────────────────────────── */}
      <Box sx={{
        flex: 1, minHeight: 0,
        display: tab === JSON_TAB ? "flex" : "block",
        flexDirection: "column",
        overflowY: tab === JSON_TAB ? "hidden" : "auto",
        scrollbarWidth: "none",
        "&::-webkit-scrollbar": { display: "none" },
      }}>
        {tab === SUMMARY_TAB && (
          <SummaryContent node={node} onDrillIn={onDrillIn} />
        )}
        {tab === INPUT_TAB && (
          <Box sx={{ p: 2 }}>
            <ContentView value={inputValue} label="input" />
          </Box>
        )}
        {tab === OUTPUT_TAB && (
          <Box sx={{ p: 2 }}>
            <ContentView value={outputValue} label="output" />
          </Box>
        )}
        {tab === JSON_TAB && (
          <Box sx={{ flex: 1, minHeight: 0 }}>
            <JsonView src={jsonData} />
          </Box>
        )}
      </Box>
    </Paper>
  );
}

export default AgentDetailPanel;
