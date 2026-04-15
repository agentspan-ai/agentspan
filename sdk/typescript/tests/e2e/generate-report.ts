#!/usr/bin/env npx tsx
/**
 * Generate HTML report from JUnit XML — matches Python SDK report format exactly.
 * Usage: npx tsx tests/e2e/generate-report.ts <junit.xml> <output.html>
 */

import { readFileSync, writeFileSync } from 'node:fs';

const xmlPath = process.argv[2];
const htmlPath = process.argv[3];

if (!xmlPath || !htmlPath) {
  console.error('Usage: npx tsx generate-report.ts <junit.xml> <output.html>');
  process.exit(1);
}

// ── Types ───────────────────────────────────────────────────────────────

interface TestCase {
  name: string;
  classname: string;
  time: number;
  status: 'PASSED' | 'FAILED' | 'ERROR' | 'SKIPPED';
  detail: string;
  errorSummary: string;
  location: string;
}

interface Suite {
  name: string;
  tests: TestCase[];
}

// ── Parse JUnit XML ─────────────────────────────────────────────────────

function parseJunit(xml: string): TestCase[] {
  const tests: TestCase[] = [];
  const tcRegex = /<testcase\s+([^>]*?)(?:\/>|>([\s\S]*?)<\/testcase>)/g;
  let match: RegExpExecArray | null;

  while ((match = tcRegex.exec(xml)) !== null) {
    const attrs = match[1];
    const body = match[2] ?? '';

    const name = attrs.match(/name="([^"]*)"/)?.[ 1] ?? '';
    const classname = attrs.match(/classname="([^"]*)"/)?.[ 1] ?? '';
    const time = parseFloat(attrs.match(/time="([^"]*)"/)?.[ 1] ?? '0');

    const failureMsg = body.match(/<failure[^>]*message="([^"]*)"/)?.[ 1] ?? '';
    const failureBody = body.match(/<failure[^>]*>([\s\S]*?)<\/failure>/)?.[ 1] ?? '';
    const errorMsg = body.match(/<error[^>]*message="([^"]*)"/)?.[ 1] ?? '';
    const errorBody = body.match(/<error[^>]*>([\s\S]*?)<\/error>/)?.[ 1] ?? '';
    const skipMsg = body.match(/<skipped[^>]*message="([^"]*)"/)?.[ 1] ?? '';
    const hasSkipped = body.includes('<skipped');
    const hasFailure = body.includes('<failure');
    const hasError = body.includes('<error');

    let status: TestCase['status'] = 'PASSED';
    let detail = '';
    let message = '';

    if (hasFailure) {
      status = 'FAILED';
      detail = failureBody || failureMsg;
      message = failureMsg;
    } else if (hasError) {
      status = 'ERROR';
      detail = errorBody || errorMsg;
      message = errorMsg;
    } else if (hasSkipped) {
      status = 'SKIPPED';
      detail = skipMsg;
      message = skipMsg;
    }

    tests.push({
      name,
      classname,
      time,
      status,
      detail: unescapeXml(detail),
      errorSummary: extractErrorSummary(unescapeXml(message), unescapeXml(detail)),
      location: extractLocation(unescapeXml(detail)),
    });
  }
  return tests;
}

function unescapeXml(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

function extractErrorSummary(message: string, detail: string): string {
  for (const line of detail.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith('AssertionError:')) return trimmed.slice('AssertionError:'.length).trim();
    if (trimmed.startsWith('Error:')) return trimmed.slice('Error:'.length).trim();
  }
  if (message) {
    if (message.startsWith('AssertionError:')) return message.slice('AssertionError:'.length).trim();
    return message.split('\n')[0].trim();
  }
  return '';
}

function extractLocation(detail: string): string {
  const locations: string[] = [];
  for (const line of detail.split('\n')) {
    const m = line.trim().match(/(\S+\.ts):(\d+):/);
    if (m) locations.push(`${m[1]}:${m[2]}`);
  }
  return locations.at(-1) ?? '';
}

// ── Suite grouping ──────────────────────────────────────────────────────

function suiteKeyFromClassname(classname: string): string {
  // "tests/e2e/test_suite1_basic_validation.test.ts > Suite 1: Basic Validation"
  const m = classname.match(/test_suite(\d+)_([a-z_]+)/);
  if (m) {
    const num = m[1];
    const words = m[2].replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    return `Suite ${num}: ${words}`;
  }
  // Fallback: use last segment after >
  const parts = classname.split('>');
  return parts.at(-1)?.trim() || classname;
}

function groupBySuite(tests: TestCase[]): Suite[] {
  const map = new Map<string, TestCase[]>();
  for (const t of tests) {
    const key = suiteKeyFromClassname(t.classname);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(t);
  }
  return Array.from(map.entries()).map(([name, tests]) => ({ name, tests }));
}

// ── HTML rendering (matches Python report_generator.py exactly) ─────────

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderHtml(tests: TestCase[]): string {
  const suites = groupBySuite(tests);
  const passed = tests.filter((t) => t.status === 'PASSED').length;
  const failed = tests.filter((t) => t.status === 'FAILED' || t.status === 'ERROR').length;
  const skipped = tests.filter((t) => t.status === 'SKIPPED').length;
  const total = tests.length;
  const totalTime = tests.reduce((s, t) => s + t.time, 0);
  const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  const overall = failed === 0 ? 'PASSED' : 'FAILED';
  const overallColor = failed === 0 ? '#22c55e' : '#ef4444';

  const statusColors: Record<string, string> = {
    PASSED: '#22c55e',
    FAILED: '#ef4444',
    ERROR: '#f97316',
    SKIPPED: '#eab308',
  };

  const testRows: string[] = [];
  for (const suite of suites) {
    const suiteId = suite.name.replace(/[^a-zA-Z0-9]/g, '_');
    const suitePass = suite.tests.filter((t) => t.status === 'PASSED').length;
    const suiteFail = suite.tests.filter((t) => t.status === 'FAILED' || t.status === 'ERROR').length;
    const suiteTotal = suite.tests.length;
    const suiteStatusColor = suiteFail === 0 ? '#22c55e' : '#ef4444';
    const suiteLabel =
      suiteFail === 0
        ? `${suitePass}/${suiteTotal} passed`
        : `${suiteFail} failed, ${suitePass} passed`;

    testRows.push(
      `<tr class='suite-header' onclick="toggleSuite('${suiteId}')">` +
        `<td colspan='3'>${esc(suite.name)}</td>` +
        `<td style='color:${suiteStatusColor}'>${suiteLabel}</td>` +
        `</tr>`,
    );

    for (const t of suite.tests) {
      const color = statusColors[t.status] ?? '#888';
      const detailParts: string[] = [];

      if ((t.status === 'FAILED' || t.status === 'ERROR') && t.errorSummary) {
        detailParts.push(`<div class='error-summary'>${esc(t.errorSummary)}</div>`);
      }
      if (t.location) {
        detailParts.push(`<div class='error-location'>${esc(t.location)}</div>`);
      }
      if (t.detail) {
        detailParts.push(
          `<details><summary>Full traceback</summary><pre>${esc(t.detail)}</pre></details>`,
        );
      }
      if (t.status === 'SKIPPED' && t.errorSummary) {
        detailParts.push(`<span class='skip-reason'>${esc(t.errorSummary)}</span>`);
      }

      const rowClass =
        'suite-row ' + suiteId + (t.status === 'FAILED' || t.status === 'ERROR' ? ' failed-row' : '');

      testRows.push(
        `<tr class='${rowClass}'>` +
          `<td>${esc(t.name)}</td>` +
          `<td style='color:${color};font-weight:bold'>${t.status}</td>` +
          `<td>${t.time.toFixed(2)}s</td>` +
          `<td>${detailParts.join('\n')}</td>` +
          `</tr>`,
      );
    }
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>E2E Test Report — TypeScript SDK</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0f172a; color: #e2e8f0; padding: 2rem; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; }
  .summary { display: flex; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .stat { background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; }
  .stat .label { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; }
  .stat .value { font-size: 1.5rem; font-weight: bold; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 0.5rem 1rem; background: #1e293b; color: #94a3b8;
       font-size: 0.75rem; text-transform: uppercase; }
  td { padding: 0.5rem 1rem; border-bottom: 1px solid #1e293b; vertical-align: top; }
  tr.suite-header { cursor: pointer; }
  tr.suite-header td { background: #1e293b; font-weight: bold; color: #60a5fa;
                        padding: 0.75rem 1rem; }
  tr.suite-header:hover td { background: #334155; }
  tr.failed-row td { background: #1c1117; }
  .error-summary { color: #fca5a5; font-weight: 600; margin-bottom: 0.25rem;
                     line-height: 1.4; }
  .error-location { color: #94a3b8; font-size: 0.8rem; margin-bottom: 0.25rem; }
  .skip-reason { color: #eab308; font-size: 0.85rem; }
  details { margin-top: 0.5rem; }
  summary { cursor: pointer; color: #64748b; font-size: 0.8rem; }
  summary:hover { color: #94a3b8; }
  pre { background: #1e293b; padding: 1rem; border-radius: 4px; overflow-x: auto;
         font-size: 0.75rem; margin-top: 0.5rem; white-space: pre-wrap;
         max-height: 400px; overflow-y: auto; }
</style>
<script>
function toggleSuite(suiteId) {
  document.querySelectorAll('.suite-row.' + suiteId).forEach(function(row) {
    row.style.display = row.style.display === 'none' ? '' : 'none';
  });
}
</script>
</head>
<body>
<h1>E2E Test Report — TypeScript SDK</h1>
<div class="summary">
  <div class="stat">
    <div class="label">Status</div>
    <div class="value" style="color:${overallColor}">${overall}</div>
  </div>
  <div class="stat">
    <div class="label">Total</div>
    <div class="value">${total}</div>
  </div>
  <div class="stat">
    <div class="label">Passed</div>
    <div class="value" style="color:#22c55e">${passed}</div>
  </div>
  <div class="stat">
    <div class="label">Failed</div>
    <div class="value" style="color:#ef4444">${failed}</div>
  </div>
  <div class="stat">
    <div class="label">Skipped</div>
    <div class="value" style="color:#eab308">${skipped}</div>
  </div>
  <div class="stat">
    <div class="label">Duration</div>
    <div class="value">${totalTime.toFixed(1)}s</div>
  </div>
  <div class="stat">
    <div class="label">Timestamp</div>
    <div class="value" style="font-size:1rem">${timestamp}</div>
  </div>
</div>
<table>
<thead><tr><th>Test</th><th>Status</th><th>Time</th><th>Detail</th></tr></thead>
<tbody>
${testRows.join('\n')}
</tbody>
</table>
</body>
</html>`;
}

// ── Main ────────────────────────────────────────────────────────────────

try {
  const xml = readFileSync(xmlPath, 'utf-8');
  const tests = parseJunit(xml);
  const html = renderHtml(tests);
  writeFileSync(htmlPath, html);
  console.log(`Report written to ${htmlPath} (${tests.length} tests)`);
} catch (e) {
  console.error(`Failed to generate report: ${e}`);
  process.exit(1);
}
