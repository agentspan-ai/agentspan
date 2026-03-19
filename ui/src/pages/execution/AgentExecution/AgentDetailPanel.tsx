/**
 * AgentDetailPanel — right-hand panel matching Conductor's task detail style.
 * Tabs: Summary | Input | Output | JSON
 */
import { useState, useRef } from "react";
import { Box, Paper, Typography, IconButton, Select, MenuItem } from "@mui/material";
import { X as CloseIcon, ArrowRight } from "@phosphor-icons/react";
import { Tab, Tabs } from "components";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentEvent, AgentRunData, AgentStatus, EventType } from "./types";
import { formatTokens, formatDuration } from "./agentExecutionUtils";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DetailNodeData {
  kind: "llm" | "tool" | "handoff" | "subagent" | "output" | "error" | "start" | "group";
  label: string;
  status: AgentStatus;
  event?: AgentEvent;
  subAgentRun?: AgentRunData;
  /** For group kind */
  groupType?: "agents" | "tools";
  groupAgents?: AgentRunData[];
  groupEvents?: AgentEvent[];
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
  // Object: wrap Monaco in fixed-height container (height="100%" requires flex parent,
  // which only the JSON tab provides — Input/Output tabs use block layout).
  return (
    <Box sx={{ height: 400, border: "1px solid rgba(0,0,0,0.08)", borderRadius: 1, overflow: "hidden" }}>
      <JsonView src={value} />
    </Box>
  );
}

// ─── Summary key-value row (matches Conductor's KeyValueTable style) ──────────

function SummaryRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "" || value === undefined) return null;
  return (
    <Box sx={{
      display: "flex", alignItems: "flex-start",
      px: 2, py: 1,
      borderBottom: "1px solid #e5e7eb",
      gap: 2,
    }}>
      <Typography sx={{ color: "#6b7280", fontSize: "0.875rem", minWidth: 148, flexShrink: 0, lineHeight: 1.7 }}>
        {label}
      </Typography>
      <Box sx={{ fontSize: "0.875rem", color: "#111827", wordBreak: "break-word", lineHeight: 1.7 }}>
        {value}
      </Box>
    </Box>
  );
}

function SummaryTable({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ border: "1px solid #e5e7eb", borderRadius: 1, overflow: "hidden", mx: 2, my: 1.5 }}>
      {children}
    </Box>
  );
}

// ─── Status pill chip (matches Conductor's status badge) ──────────────────────

function StatusChip({ status }: { status: AgentStatus }) {
  const cfg = {
    [AgentStatus.COMPLETED]: { bg: "#d4edda", color: "#155724", label: "COMPLETED" },
    [AgentStatus.FAILED]:    { bg: "#f8d7da", color: "#721c24", label: "FAILED"    },
    [AgentStatus.RUNNING]:   { bg: "#fff3cd", color: "#856404", label: "RUNNING"   },
    [AgentStatus.WAITING]:   { bg: "#fff3cd", color: "#856404", label: "WAITING"   },
  }[status] ?? { bg: "#e9ecef", color: "#495057", label: status.toUpperCase() };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      backgroundColor: cfg.bg, color: cfg.color,
      fontSize: "0.75rem", fontWeight: 600,
      padding: "2px 10px", borderRadius: 20,
      letterSpacing: "0.02em",
    }}>
      {cfg.label}
    </span>
  );
}

// Keep old name as alias for backward compat within this file
const StatusBadgeInline = StatusChip;

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

// ─── Parallel run selector ────────────────────────────────────────────────────

type WindowItem = { type: "chip"; idx: number } | { type: "gap"; from: number; to: number };

function buildWindow(total: number, sel: number): WindowItem[] {
  if (total <= 9) return Array.from({ length: total }, (_, i) => ({ type: "chip" as const, idx: i }));
  const visible = new Set(
    [0, 1, total - 2, total - 1,
     Math.max(0, sel - 2), Math.max(0, sel - 1), sel,
     Math.min(total - 1, sel + 1), Math.min(total - 1, sel + 2)]
    .filter(i => i >= 0 && i < total)
  );
  const sorted = Array.from(visible).sort((a, b) => a - b);
  const result: WindowItem[] = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i] > sorted[i - 1] + 1)
      result.push({ type: "gap", from: sorted[i - 1] + 1, to: sorted[i] - 1 });
    result.push({ type: "chip", idx: sorted[i] });
  }
  return result;
}

interface RunBarProps {
  count: number;
  statuses: AgentStatus[];
  selected: number;
  onSelect: (i: number) => void;
  labels: string[];
}

function RunBar({ count, statuses, selected, onSelect, labels }: RunBarProps) {
  const items = buildWindow(count, selected);
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, flexWrap: "wrap" }}>
      {items.map((item, i) => {
        if (item.type === "chip") {
          const { idx } = item;
          const st = statuses[idx];
          const color = st === AgentStatus.FAILED ? "#DD2222" : st === AgentStatus.RUNNING ? "#f59e0b" : "#40BA56";
          const active = idx === selected;
          return (
            <Box
              key={idx}
              component="button"
              onClick={() => onSelect(idx)}
              sx={{
                appearance: "none", fontFamily: "inherit", cursor: "pointer",
                minWidth: 32, height: 24, px: 0.5,
                display: "flex", alignItems: "center", justifyContent: "center",
                backgroundColor: active ? color : "#fff",
                color: active ? "#fff" : "#858585",
                border: `1px solid ${active ? color : "#DDDDDD"}`,
                borderRadius: "3px",
                fontSize: "0.65rem", fontWeight: active ? 700 : 500,
                transition: "all 0.1s", outline: "none",
                "&:hover": { borderColor: color, color: active ? "#fff" : color, backgroundColor: active ? color : `${color}12` },
              }}
            >
              {idx + 1}
            </Box>
          );
        }
        // Gap → dropdown listing all runs in the gap
        const { from, to } = item;
        const gapItems = Array.from({ length: to - from + 1 }, (_, k) => from + k);
        return (
          <Select
            key={`gap-${from}`}
            value=""
            displayEmpty
            renderValue={() => "···"}
            onChange={(e) => onSelect(Number(e.target.value))}
            size="small"
            variant="outlined"
            sx={{
              height: 24, minWidth: 36,
              "& .MuiSelect-select": { py: 0, px: 0.75, fontSize: "0.65rem", display: "flex", alignItems: "center", justifyContent: "center", color: "#858585" },
              "& .MuiOutlinedInput-notchedOutline": { borderColor: "#DDDDDD" },
              "& .MuiSelect-icon": { display: "none" },
            }}
          >
            {gapItems.map(idx => {
              const st = statuses[idx];
              const dot = st === AgentStatus.FAILED ? "#DD2222" : st === AgentStatus.RUNNING ? "#f59e0b" : "#40BA56";
              return (
                <MenuItem key={idx} value={idx} sx={{ fontSize: "0.75rem", gap: 1 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: dot, flexShrink: 0 }} />
                  {labels[idx] ?? `Run ${idx + 1}`}
                </MenuItem>
              );
            })}
          </Select>
        );
      })}
    </Box>
  );
}

// ─── Group detail panel (parallel agents / tool calls) ────────────────────────

function GroupDetailPanel({ node, onDrillIn }: { node: DetailNodeData; onDrillIn?: (run: AgentRunData) => void }) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const isAgents = node.groupType === "agents";
  const agents = node.groupAgents ?? [];
  const events = node.groupEvents ?? [];
  const count = isAgents ? agents.length : events.length;

  const statuses: AgentStatus[] = isAgents
    ? agents.map(a => a.status)
    : events.map(e => e.success === true ? AgentStatus.COMPLETED : e.success === false ? AgentStatus.FAILED : AgentStatus.RUNNING);

  const labels: string[] = isAgents
    ? agents.map((a, i) => `${a.agentName} #${i + 1}`)
    : events.map((e, i) => `${e.toolName ?? "tool"} #${i + 1}`);

  const completed = statuses.filter(s => s === AgentStatus.COMPLETED).length;
  const failed    = statuses.filter(s => s === AgentStatus.FAILED).length;
  const running   = count - completed - failed;

  const selAgent = isAgents ? agents[selectedIdx] : undefined;
  const selEvent = !isAgents ? events[selectedIdx] : undefined;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Stat bar */}
      <Box sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 2, borderBottom: "1px solid #e5e7eb", flexShrink: 0 }}>
        <Typography sx={{ fontSize: "0.75rem", color: "text.secondary" }}>{count} {isAgents ? "agents" : "calls"}</Typography>
        {completed > 0 && <Typography sx={{ fontSize: "0.75rem", color: "#40BA56", fontWeight: 600 }}>{completed} ✓</Typography>}
        {failed    > 0 && <Typography sx={{ fontSize: "0.75rem", color: "#DD2222", fontWeight: 600 }}>{failed} ✗</Typography>}
        {running   > 0 && <Typography sx={{ fontSize: "0.75rem", color: "#f59e0b", fontWeight: 600 }}>{running} ⟳</Typography>}
      </Box>

      {/* Run selector */}
      <Box sx={{ px: 2, py: 1.25, borderBottom: "1px solid #e5e7eb", flexShrink: 0 }}>
        <RunBar count={count} statuses={statuses} selected={selectedIdx} onSelect={setSelectedIdx} labels={labels} />
      </Box>

      {/* Selected run detail */}
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", scrollbarWidth: "none", "&::-webkit-scrollbar": { display: "none" } }}>
        {selAgent && (
          <Box>
            <SummaryTable>
              <SummaryRow label="Agent" value={selAgent.agentName} />
              {selAgent.model && <SummaryRow label="Model" value={selAgent.model} />}
              <SummaryRow label="Status" value={<StatusBadgeInline status={selAgent.status} />} />
              {selAgent.totalDurationMs > 0 && <SummaryRow label="Duration" value={formatDuration(selAgent.totalDurationMs)} />}
              {(selAgent.totalTokens.promptTokens + selAgent.totalTokens.completionTokens) > 0 && (
                <SummaryRow label="Total tokens" value={formatTokens(selAgent.totalTokens.promptTokens + selAgent.totalTokens.completionTokens)} />
              )}
              {selAgent.finishReason && <SummaryRow label="Finish reason" value={selAgent.finishReason.toUpperCase()} />}
              {selAgent.failureReason && <SummaryRow label="Failure reason" value={<span style={{ color: "#DC2626" }}>{selAgent.failureReason}</span>} />}
            </SummaryTable>
            {onDrillIn && (
              <Box sx={{ px: 2, py: 1 }}>
                <Box
                  onClick={() => onDrillIn(selAgent)}
                  sx={{
                    display: "inline-flex", alignItems: "center", gap: 0.75,
                    px: 1.5, py: 0.75, borderRadius: 1, cursor: "pointer",
                    fontSize: "0.8rem", fontWeight: 500, color: "#fff",
                    backgroundColor: "#4969e4", "&:hover": { backgroundColor: "#3858d6" },
                  }}
                >
                  View full execution <ArrowRight size={14} />
                </Box>
              </Box>
            )}
          </Box>
        )}
        {selEvent && (
          <Box>
            <SummaryTable>
              <SummaryRow label="Tool" value={selEvent.toolName ?? "tool"} />
              <SummaryRow label="Status" value={<StatusBadgeInline status={statuses[selectedIdx]} />} />
              {selEvent.durationMs ? <SummaryRow label="Duration" value={formatDuration(selEvent.durationMs)} /> : null}
              {selEvent.taskMeta?.workerId && <SummaryRow label="Worker" value={selEvent.taskMeta.workerId} />}
              {selEvent.taskMeta?.reasonForIncompletion && (
                <SummaryRow label="Failure" value={<span style={{ color: "#DC2626" }}>{selEvent.taskMeta.reasonForIncompletion}</span>} />
              )}
            </SummaryTable>
            {selEvent.toolArgs != null && (
              <SummaryTable>
              <SummaryRow label="Input" value={
                <Box sx={{ height: 180, border: "1px solid #e5e7eb", borderRadius: 1, overflow: "hidden" }}>
                  <JsonView src={selEvent.toolArgs} />
                </Box>
              } />
              {selEvent.result != null && (
                <SummaryRow label="Output" value={
                  <Box sx={{ height: 180, border: "1px solid #e5e7eb", borderRadius: 1, overflow: "hidden" }}>
                    <JsonView src={selEvent.result} />
                  </Box>
                } />
              )}
            </SummaryTable>
          </Box>
        )}
      </Box>
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
        <SummaryTable>
          <SummaryRow label="Agent" value={run.agentName} />
          {run.model && <SummaryRow label="Model" value={run.model} />}
          <SummaryRow label="Status" value={<StatusBadgeInline status={run.status} />} />
          {run.totalDurationMs > 0 && <SummaryRow label="Duration" value={formatDuration(run.totalDurationMs)} />}
          {(pt + ct) > 0 && <SummaryRow label="Total tokens" value={formatTokens(pt + ct)} />}
          {pt > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(pt)} />}
          {ct > 0 && <SummaryRow label="Completion tokens" value={formatTokens(ct)} />}
          {run.finishReason && <SummaryRow label="Finish reason" value={run.finishReason.toUpperCase()} />}
        </SummaryTable>
        {onDrillIn && (
          <Box sx={{ px: 2, py: 1 }}>
            <Box
              onClick={() => onDrillIn(run)}
              sx={{
                display: "inline-flex", alignItems: "center", gap: 0.75,
                px: 1.5, py: 0.75, borderRadius: 1, cursor: "pointer",
                fontSize: "0.8rem", fontWeight: 500, color: "#fff",
                backgroundColor: "#4969e4", transition: "all 0.15s",
                "&:hover": { backgroundColor: "#3858d6" },
              }}
            >
              View full execution <ArrowRight size={14} />
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
        <SummaryTable>
          <SummaryRow label="Kind" value="LLM Call" />
          <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
          {ev?.toolName && <SummaryRow label="Model" value={ev.toolName} />}
          {tok && (tok.promptTokens + tok.completionTokens) > 0 && <SummaryRow label="Total tokens" value={formatTokens(tok.promptTokens + tok.completionTokens)} />}
          {tok && tok.promptTokens > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(tok.promptTokens)} />}
          {tok && tok.completionTokens > 0 && <SummaryRow label="Completion tokens" value={formatTokens(tok.completionTokens)} />}
          {ev?.durationMs && <SummaryRow label="Duration" value={formatDuration(ev.durationMs)} />}
        </SummaryTable>
      </Box>
    );
  }

  if (node.kind === "tool") {
    const meta = ev?.taskMeta;
    const fmt = (ts?: number) =>
      ts ? new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 }) : undefined;
    return (
      <Box>
        <SummaryTable>
          <SummaryRow label="Tool" value={ev?.toolName ?? node.label} />
          {meta?.taskType && <SummaryRow label="Task type" value={meta.taskType} />}
          {meta?.referenceTaskName && <SummaryRow label="Reference name" value={meta.referenceTaskName} />}
          <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
          {ev?.durationMs ? <SummaryRow label="Duration" value={formatDuration(ev.durationMs)} /> : null}
          {fmt(meta?.scheduledTime) && <SummaryRow label="Scheduled" value={fmt(meta?.scheduledTime)!} />}
          {fmt(meta?.startTime) && <SummaryRow label="Start time" value={fmt(meta?.startTime)!} />}
          {fmt(meta?.endTime) && <SummaryRow label="End time" value={fmt(meta?.endTime)!} />}
          {meta?.workerId && <SummaryRow label="Worker" value={meta.workerId} />}
          {meta?.retryCount != null && meta.retryCount > 0 && <SummaryRow label="Retries" value={String(meta.retryCount)} />}
          {meta?.reasonForIncompletion && (
            <SummaryRow label="Failure reason" value={<span style={{ color: "#DC2626" }}>{meta.reasonForIncompletion}</span>} />
          )}
        </SummaryTable>
      </Box>
    );
  }

  if (node.kind === "handoff") {
    return (
      <Box>
        <SummaryTable>
          <SummaryRow label="Target agent" value={ev?.targetAgent ?? node.label} />
          <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
        </SummaryTable>
      </Box>
    );
  }

  if (node.kind === "subagent" && node.subAgentRun) {
    const run = node.subAgentRun;
    const pt = run.totalTokens.promptTokens;
    const ct = run.totalTokens.completionTokens;
    return (
      <Box>
        <SummaryTable>
          <SummaryRow label="Agent" value={run.agentName} />
          {run.model && <SummaryRow label="Model" value={run.model} />}
          <SummaryRow label="Status" value={<StatusBadgeInline status={run.status} />} />
          {run.totalDurationMs > 0 && <SummaryRow label="Duration" value={formatDuration(run.totalDurationMs)} />}
          {(pt + ct) > 0 && <SummaryRow label="Total tokens" value={formatTokens(pt + ct)} />}
          {pt > 0 && <SummaryRow label="Prompt tokens" value={formatTokens(pt)} />}
          {ct > 0 && <SummaryRow label="Completion tokens" value={formatTokens(ct)} />}
        </SummaryTable>
        {onDrillIn && (
          <Box sx={{ px: 2, py: 1 }}>
            <Box
              onClick={() => onDrillIn(run)}
              sx={{
                display: "inline-flex", alignItems: "center", gap: 0.75,
                px: 1.5, py: 0.75, borderRadius: 1, cursor: "pointer",
                fontSize: "0.8rem", fontWeight: 500, color: "#fff",
                backgroundColor: "#4969e4", transition: "all 0.15s",
                "&:hover": { backgroundColor: "#3858d6" },
              }}
            >
              View full execution <ArrowRight size={14} />
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
      <SummaryTable>
        <SummaryRow label="Kind" value={node.kind} />
        <SummaryRow label="Status" value={<StatusBadgeInline status={node.status} />} />
        {ev?.summary && <SummaryRow label="Summary" value={ev.summary} />}
      </SummaryTable>
    </Box>
  );
}

// ─── Resolve input value for a node ─────────────────────────────────────────

function resolveInput(node: DetailNodeData): unknown {
  if (node.kind === "start" && node.subAgentRun) return node.subAgentRun.input;
  if (node.kind === "subagent" && node.subAgentRun) return node.subAgentRun.input;
  const detail = node.event?.detail as any;
  if (detail && typeof detail === "object" && "input" in detail) return detail.input;
  // Fallback: toolArgs is always the raw input for TOOL_CALL events
  if (node.event?.toolArgs != null) return node.event.toolArgs;
  return null;
}

function resolveOutput(node: DetailNodeData): unknown {
  if (node.kind === "start" && node.subAgentRun) return node.subAgentRun.output;
  if (node.kind === "subagent" && node.subAgentRun) return node.subAgentRun.output;
  const detail = node.event?.detail as any;
  if (detail && typeof detail === "object" && "output" in detail) return detail.output;
  if (node.event?.type === EventType.DONE) return detail;
  // Fallback: result field carries tool output
  if (node.event?.result != null) return node.event.result;
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
  group:    "Parallel Group",
};

export function AgentDetailPanel({ node, onClose, onDrillIn }: AgentDetailPanelProps) {
  const [tab, setTab] = useState(SUMMARY_TAB);
  // Must be declared before any early returns to satisfy the Rules of Hooks
  const prevNodeId = useRef(node.label + node.kind);

  // Reset tab to summary when the non-group node changes
  if (node.kind !== "group" && prevNodeId.current !== node.label + node.kind) {
    prevNodeId.current = node.label + node.kind;
    setTab(SUMMARY_TAB);
  }

  // Group nodes get their own dedicated layout (no tabs)
  if (node.kind === "group") {
    return (
      <Paper square elevation={0} sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden", borderLeft: "1px solid", borderColor: "divider", backgroundColor: "#fff" }}>
        <Box sx={{ px: 2.5, pt: 2, pb: 1.5, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.5 }}>
                <Typography sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3, color: "text.primary", wordBreak: "break-word" }}>
                  {node.label}
                </Typography>
                <StatusChip status={node.status} />
              </Box>
              <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                {node.groupType === "agents" ? "Parallel Agents" : "Parallel Tool Calls"}
              </Typography>
            </Box>
            <IconButton size="small" onClick={onClose} sx={{ width: 26, height: 26, color: "text.disabled", flexShrink: 0, mt: 0.25, "&:hover": { color: "text.primary" } }}>
              <CloseIcon size={14} />
            </IconButton>
          </Box>
        </Box>
        <Box sx={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <GroupDetailPanel node={node} onDrillIn={onDrillIn} />
        </Box>
      </Paper>
    );
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
            {/* Name + status badge inline */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.5 }}>
              <Typography sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3, color: "text.primary", wordBreak: "break-word" }}>
                {node.label}
              </Typography>
              <StatusChip status={node.status} />
            </Box>
            {/* Kind label below */}
            <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              {KIND_DISPLAY[node.kind]}
            </Typography>
          </Box>
          <IconButton
            size="small" onClick={onClose}
            sx={{ width: 26, height: 26, color: "text.disabled", flexShrink: 0, mt: 0.25, "&:hover": { color: "text.primary" } }}
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
