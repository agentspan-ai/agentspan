/**
 * Google ADK Hierarchical Agents -- multi-level agent delegation.
 *
 * Demonstrates:
 *   - Hierarchical multi-agent architecture
 *   - A top-level coordinator delegates to team leads
 *   - Team leads delegate to specialist agents with tools
 *   - Deep nesting of subAgents
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Level 3: Specialist tools ─────────────────────────────────────────

const checkApiHealth = new FunctionTool({
  name: 'check_api_health',
  description: 'Check the health status of an API service.',
  parameters: z.object({
    service: z.string().describe('Service name to check'),
  }),
  execute: async (args: { service: string }) => {
    const services: Record<string, { status: string; latency_ms: number; uptime: string }> = {
      auth: { status: 'healthy', latency_ms: 45, uptime: '99.99%' },
      payments: { status: 'degraded', latency_ms: 350, uptime: '99.5%' },
      users: { status: 'healthy', latency_ms: 28, uptime: '99.98%' },
    };
    return services[args.service.toLowerCase()] ?? { status: 'unknown', message: `Service '${args.service}' not found` };
  },
});

const checkErrorLogs = new FunctionTool({
  name: 'check_error_logs',
  description: 'Check recent error logs for a service.',
  parameters: z.object({
    service: z.string().describe('Service name'),
    hours: z.number().describe('Number of hours to look back').default(1),
  }),
  execute: async (args: { service: string; hours?: number }) => {
    const hours = args.hours ?? 1;
    const logs: Record<string, { errors: number; warnings: number; top_error: string }> = {
      auth: { errors: 2, warnings: 5, top_error: 'Token validation timeout' },
      payments: { errors: 47, warnings: 120, top_error: 'Gateway timeout on /charge' },
      users: { errors: 0, warnings: 1, top_error: 'None' },
    };
    return { service: args.service, period_hours: hours, ...(logs[args.service.toLowerCase()] ?? { errors: -1 }) };
  },
});

const runSecurityScan = new FunctionTool({
  name: 'run_security_scan',
  description: 'Run a security vulnerability scan.',
  parameters: z.object({
    target: z.string().describe('Target service or endpoint to scan'),
  }),
  execute: async (args: { target: string }) => ({
    target: args.target,
    vulnerabilities: { critical: 0, high: 1, medium: 3, low: 7 },
    top_finding: 'Outdated TLS 1.1 still enabled on /legacy endpoint',
    recommendation: 'Disable TLS 1.1, enforce TLS 1.3',
  }),
});

const checkPerformanceMetrics = new FunctionTool({
  name: 'check_performance_metrics',
  description: 'Get performance metrics for a service.',
  parameters: z.object({
    service: z.string().describe('Service name'),
  }),
  execute: async (args: { service: string }) => {
    const metrics: Record<string, { p50_ms: number; p95_ms: number; p99_ms: number; rps: number }> = {
      auth: { p50_ms: 22, p95_ms: 89, p99_ms: 145, rps: 1200 },
      payments: { p50_ms: 180, p95_ms: 450, p99_ms: 1200, rps: 300 },
      users: { p50_ms: 15, p95_ms: 45, p99_ms: 78, rps: 800 },
    };
    return { service: args.service, ...(metrics[args.service.toLowerCase()] ?? { error: 'No data' }) };
  },
});

// ── Level 2: Team lead agents ─────────────────────────────────────────

export const opsAgent = new LlmAgent({
  name: 'ops_specialist',
  model,
  description: 'Monitors service health and investigates operational issues.',
  instruction: 'Check service health and error logs. Identify issues and their severity.',
  tools: [checkApiHealth, checkErrorLogs],
});

export const securityAgent = new LlmAgent({
  name: 'security_specialist',
  model,
  description: 'Runs security scans and identifies vulnerabilities.',
  instruction: 'Run security scans and report findings with recommendations.',
  tools: [runSecurityScan],
});

export const performanceAgent = new LlmAgent({
  name: 'performance_specialist',
  model,
  description: 'Analyzes performance metrics and identifies bottlenecks.',
  instruction: 'Check performance metrics and identify latency issues.',
  tools: [checkPerformanceMetrics],
});

// ── Level 1: Team leads ───────────────────────────────────────────────

export const reliabilityLead = new LlmAgent({
  name: 'reliability_team_lead',
  model,
  description: 'Leads the reliability team covering ops and performance.',
  instruction:
    'You lead the reliability team. Coordinate the ops specialist ' +
    'and performance specialist to investigate service issues. ' +
    'Provide a consolidated reliability report.',
  subAgents: [opsAgent, performanceAgent],
});

export const securityLead = new LlmAgent({
  name: 'security_team_lead',
  model,
  description: 'Leads the security team for vulnerability assessment.',
  instruction:
    'You lead the security team. Use the security specialist to ' +
    'assess vulnerabilities. Provide risk assessment and remediation priorities.',
  subAgents: [securityAgent],
});

// ── Top level: Platform coordinator ──────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'platform_coordinator',
  model,
  instruction:
    'You are the platform engineering coordinator. When asked to assess ' +
    'platform health:\n' +
    '1. Have the reliability team check service health and performance\n' +
    '2. Have the security team assess vulnerabilities\n' +
    '3. Compile a comprehensive platform status report\n\n' +
    'Prioritize critical issues and provide an executive summary.',
  subAgents: [reliabilityLead, securityLead],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    coordinator,
    'Give me a full platform health assessment. Focus on the payments service ' +
    'which seems to be having issues.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(coordinator);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents platform_coordinator
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(coordinator);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('10-hierarchical-agents.ts') || process.argv[1]?.endsWith('10-hierarchical-agents.js')) {
  main().catch(console.error);
}
