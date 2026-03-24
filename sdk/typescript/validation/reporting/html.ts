/**
 * HTML report generation — self-contained validation report.
 *
 * Generates an HTML file with:
 * - Score heatmap table (example x run, color-coded 1-5)
 * - Summary stats (total, pass, fail, avg score)
 * - Dark mode toggle
 * - Expandable details per example
 * - Filter by status
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import type { ValidationResult } from '../types.js';

/**
 * Escape HTML special characters.
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Generate a background color for a 1-5 score.
 */
function scoreColor(score: number): string {
  if (score >= 5) return '#16a34a';
  if (score >= 4) return '#65a30d';
  if (score >= 3) return '#ca8a04';
  if (score >= 2) return '#ea580c';
  return '#dc2626';
}

/**
 * Status badge CSS class.
 */
function statusBadge(status: string): string {
  switch (status) {
    case 'PASS':
      return 'badge-pass';
    case 'FAIL':
      return 'badge-fail';
    case 'WARN':
      return 'badge-warn';
    default:
      return 'badge-fail';
  }
}

/**
 * Generate a self-contained HTML validation report.
 */
export function generateHtmlReport(
  results: ValidationResult[],
  outputPath: string,
): void {
  const total = results.length;
  const passed = results.filter((r) => r.status === 'PASS').length;
  const failed = results.filter((r) => r.status === 'FAIL').length;
  const warned = results.filter((r) => r.status === 'WARN').length;

  const scores = results.filter((r) => r.judgeScore != null).map((r) => r.judgeScore!);
  const avgScore = scores.length > 0 ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(2) : 'N/A';

  const avgDuration = total > 0
    ? (results.reduce((a, r) => a + r.duration, 0) / total).toFixed(1)
    : '0';

  // Build table rows
  let rows = '';
  for (const r of results) {
    const scoreCell = r.judgeScore != null
      ? `<td class="score-cell" style="background:${scoreColor(r.judgeScore)};color:white">${r.judgeScore}</td>`
      : '<td class="score-cell na">-</td>';

    const comparisonCell = r.comparisonScore != null
      ? `<td class="score-cell" style="background:${scoreColor(r.comparisonScore)};color:white">${r.comparisonScore}</td>`
      : '<td class="score-cell na">-</td>';

    const checksHtml = [
      `Workflow: ${r.checks.workflowCompleted ? 'OK' : 'FAIL'}`,
      `Errors: ${r.checks.noUnhandledErrors ? 'None' : 'FOUND'}`,
      `Tools: ${r.checks.allToolsSucceeded ? 'OK' : 'FAIL'} (${r.checks.toolAudit.length} calls)`,
      `LLM: ${r.checks.llmEngaged ? 'OK' : 'FAIL'}`,
      `Output: ${r.checks.outputNonEmpty ? 'OK' : 'EMPTY'}`,
    ].join('<br>');

    const outputPreview = escapeHtml(r.output.slice(0, 500));
    const judgeReason = r.judgeReason ? escapeHtml(r.judgeReason) : '';
    const comparisonReason = r.comparisonReason ? escapeHtml(r.comparisonReason) : '';
    const errorHtml = r.error ? `<div class="error-text">${escapeHtml(r.error)}</div>` : '';

    rows += `
    <tr data-status="${r.status}">
      <td>${escapeHtml(r.example)}</td>
      <td><span class="${statusBadge(r.status)}">${r.status}</span></td>
      <td>${r.duration.toFixed(1)}s</td>
      ${scoreCell}
      ${comparisonCell}
      <td>
        <details>
          <summary>Checks</summary>
          <div class="details-content">${checksHtml}</div>
        </details>
      </td>
      <td>
        <details>
          <summary>Details</summary>
          <div class="details-content">
            ${outputPreview ? `<div class="output-block"><strong>Output:</strong><pre>${outputPreview}</pre></div>` : ''}
            ${judgeReason ? `<div><strong>Judge:</strong> ${judgeReason}</div>` : ''}
            ${comparisonReason ? `<div><strong>Comparison:</strong> ${comparisonReason}</div>` : ''}
            ${errorHtml}
            <div><strong>Events:</strong> ${r.events.length}</div>
          </div>
        </details>
      </td>
    </tr>`;
  }

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agentspan TypeScript SDK Validation Report</title>
  <style>
    :root {
      --bg: #f9fafb;
      --surface: #ffffff;
      --text: #1f2937;
      --text-secondary: #6b7280;
      --border: #e5e7eb;
      --hover: #f3f4f6;
    }
    .dark {
      --bg: #111827;
      --surface: #1f2937;
      --text: #f9fafb;
      --text-secondary: #9ca3af;
      --border: #374151;
      --hover: #374151;
    }
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      margin: 0; padding: 20px;
      background: var(--bg); color: var(--text);
      transition: background 0.2s, color 0.2s;
    }
    h1 { margin: 0 0 4px; }
    .subtitle { color: var(--text-secondary); margin: 0 0 20px; }
    .controls { display: flex; gap: 12px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }
    .controls button {
      padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
      background: var(--surface); color: var(--text); cursor: pointer; font-size: 13px;
    }
    .controls button.active { background: #3b82f6; color: white; border-color: #3b82f6; }
    .controls button:hover { opacity: 0.85; }
    .summary { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
    .card {
      padding: 16px 24px; border-radius: 10px; color: white;
      font-weight: bold; font-size: 16px; min-width: 120px; text-align: center;
    }
    .card-total { background: #3b82f6; }
    .card-pass { background: #16a34a; }
    .card-fail { background: #dc2626; }
    .card-warn { background: #ca8a04; }
    .card-avg { background: #7c3aed; }
    .card .big { font-size: 28px; display: block; margin-bottom: 2px; }
    table {
      border-collapse: collapse; width: 100%;
      background: var(--surface); border-radius: 10px;
      overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    th {
      background: #1e293b; color: white; padding: 12px 10px;
      text-align: left; font-size: 13px; white-space: nowrap;
    }
    td { padding: 10px; border-top: 1px solid var(--border); font-size: 13px; }
    tr:hover { background: var(--hover); }
    .score-cell { text-align: center; font-weight: bold; border-radius: 4px; min-width: 40px; }
    .score-cell.na { background: var(--border); color: var(--text-secondary); }
    .badge-pass { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }
    .badge-fail { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }
    .badge-warn { background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }
    details summary { cursor: pointer; color: #3b82f6; font-size: 12px; }
    .details-content { padding: 8px 0; font-size: 12px; line-height: 1.6; }
    .output-block pre {
      background: var(--bg); padding: 8px; border-radius: 4px;
      overflow-x: auto; font-size: 11px; max-height: 200px; white-space: pre-wrap;
    }
    .error-text { color: #dc2626; margin-top: 4px; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <h1>Agentspan TypeScript SDK Validation Report</h1>
  <p class="subtitle">Generated: ${new Date().toISOString()}</p>

  <div class="summary">
    <div class="card card-total"><span class="big">${total}</span>Total</div>
    <div class="card card-pass"><span class="big">${passed}</span>Passed</div>
    <div class="card card-fail"><span class="big">${failed}</span>Failed</div>
    <div class="card card-warn"><span class="big">${warned}</span>Warned</div>
    <div class="card card-avg"><span class="big">${avgScore}</span>Avg Score</div>
  </div>

  <div class="controls">
    <button id="filter-all" class="active" onclick="filterBy('all')">All</button>
    <button id="filter-pass" onclick="filterBy('PASS')">PASS</button>
    <button id="filter-fail" onclick="filterBy('FAIL')">FAIL</button>
    <button id="filter-warn" onclick="filterBy('WARN')">WARN</button>
    <span style="margin-left:auto"></span>
    <button onclick="toggleDark()">Dark Mode</button>
  </div>

  <table>
    <thead>
      <tr>
        <th>Example</th>
        <th>Status</th>
        <th>Duration</th>
        <th>Judge</th>
        <th>Comparison</th>
        <th>Checks</th>
        <th>Details</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>

  <p class="subtitle" style="margin-top:16px">
    Average duration: ${avgDuration}s | Total examples: ${total}
  </p>

  <script>
    function filterBy(status) {
      document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
      document.getElementById('filter-' + status.toLowerCase()).classList.add('active');
      document.querySelectorAll('tbody tr').forEach(row => {
        if (status === 'all' || row.dataset.status === status) {
          row.classList.remove('hidden');
        } else {
          row.classList.add('hidden');
        }
      });
    }
    function toggleDark() {
      document.documentElement.classList.toggle('dark');
    }
  </script>
</body>
</html>`;

  const dir = path.dirname(outputPath);
  if (dir && !fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(outputPath, html, 'utf-8');
}
