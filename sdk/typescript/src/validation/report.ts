import type { JudgeResult } from './judge.js';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * A single run result for the report.
 */
export interface RunReport {
  name: string;
  group?: string;
  model: string;
  status: string;
  finishReason: string;
  duration?: number;
  judgeResult?: JudgeResult;
  error?: string;
}

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
 * Generate a color for a score value (1-5 scale).
 */
function scoreColor(score: number): string {
  if (score >= 4.5) return '#22c55e'; // green
  if (score >= 3.5) return '#84cc16'; // lime
  if (score >= 2.5) return '#eab308'; // yellow
  if (score >= 1.5) return '#f97316'; // orange
  return '#ef4444'; // red
}

/**
 * Generate an HTML validation report.
 */
export function generateReport(
  results: RunReport[],
  outputPath: string,
): void {
  // Collect all unique rubric names and models
  const rubricNames = new Set<string>();
  const models = new Set<string>();
  for (const r of results) {
    models.add(r.model);
    if (r.judgeResult) {
      for (const name of Object.keys(r.judgeResult.scores)) {
        rubricNames.add(name);
      }
    }
  }

  const rubricList = [...rubricNames];
  const passed = results.filter(
    (r) => r.status === 'COMPLETED' && (r.judgeResult?.passed ?? true),
  ).length;
  const failed = results.length - passed;

  // Build heatmap rows
  let heatmapRows = '';
  for (const r of results) {
    const badge =
      r.status === 'COMPLETED' && (r.judgeResult?.passed ?? true)
        ? '<span style="color:#22c55e;font-weight:bold">PASS</span>'
        : '<span style="color:#ef4444;font-weight:bold">FAIL</span>';

    let cells = '';
    for (const rubric of rubricList) {
      const score = r.judgeResult?.scores[rubric];
      if (score !== undefined) {
        cells += `<td style="background:${scoreColor(score)};color:white;text-align:center;padding:8px">${score.toFixed(1)}</td>`;
      } else {
        cells += '<td style="background:#e5e7eb;text-align:center;padding:8px">-</td>';
      }
    }

    const reasoning = r.judgeResult?.reasoning
      ? Object.entries(r.judgeResult.reasoning)
          .map(([k, v]) => `<strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}`)
          .join('<br>')
      : '';

    const errorHtml = r.error
      ? `<div style="color:#ef4444;margin-top:4px">${escapeHtml(r.error)}</div>`
      : '';

    heatmapRows += `
    <tr>
      <td style="padding:8px">${escapeHtml(r.name)}</td>
      <td style="padding:8px">${escapeHtml(r.model)}</td>
      <td style="padding:8px">${badge}</td>
      <td style="padding:8px">${r.judgeResult?.weightedAverage?.toFixed(2) ?? '-'}</td>
      ${cells}
      <td style="padding:8px">
        <details>
          <summary>Details</summary>
          <div style="padding:8px;font-size:12px">
            <div>Status: ${escapeHtml(r.status)}</div>
            <div>Finish: ${escapeHtml(r.finishReason)}</div>
            ${r.duration !== undefined ? `<div>Duration: ${r.duration}ms</div>` : ''}
            ${reasoning ? `<div style="margin-top:4px">${reasoning}</div>` : ''}
            ${errorHtml}
          </div>
        </details>
      </td>
    </tr>`;
  }

  const rubricHeaders = rubricList
    .map((name) => `<th style="padding:8px">${escapeHtml(name)}</th>`)
    .join('');

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agentspan Validation Report</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 20px; background: #f9fafb; }
    h1 { color: #1f2937; }
    .summary { display: flex; gap: 20px; margin-bottom: 20px; }
    .summary-card { padding: 16px 24px; border-radius: 8px; color: white; font-size: 18px; font-weight: bold; }
    .pass-card { background: #22c55e; }
    .fail-card { background: #ef4444; }
    .total-card { background: #3b82f6; }
    table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    th { background: #1f2937; color: white; padding: 12px 8px; text-align: left; }
    tr:nth-child(even) { background: #f9fafb; }
    tr:hover { background: #f3f4f6; }
    td { border-top: 1px solid #e5e7eb; }
    details summary { cursor: pointer; color: #3b82f6; }
  </style>
</head>
<body>
  <h1>Agentspan Validation Report</h1>
  <p>Generated: ${new Date().toISOString()}</p>

  <div class="summary">
    <div class="summary-card total-card">Total: ${results.length}</div>
    <div class="summary-card pass-card">Passed: ${passed}</div>
    <div class="summary-card fail-card">Failed: ${failed}</div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Run</th>
        <th>Model</th>
        <th>Result</th>
        <th>Avg Score</th>
        ${rubricHeaders}
        <th>Details</th>
      </tr>
    </thead>
    <tbody>
      ${heatmapRows}
    </tbody>
  </table>
</body>
</html>`;

  // Ensure directory exists
  const dir = path.dirname(outputPath);
  if (dir && !fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(outputPath, html, 'utf-8');
}
