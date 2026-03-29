/**
 * Advanced Orchestration -- agent orchestrating a complex multi-step pipeline.
 *
 * Demonstrates:
 *   - Combining structured output, prompt templates, and output parsers
 *   - A pipeline agent that decomposes tasks, assigns subtasks, and aggregates results
 *   - Tools that themselves invoke LLM chains (nested LLM calls)
 *   - Practical use case: automated business report generation from raw data inputs
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { ChatPromptTemplate } from '@langchain/core/prompts';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Parsers ──────────────────────────────────────────────

const strParser = new StringOutputParser();

// ── Zod schemas for structured report ────────────────────

const ReportSectionSchema = z.object({
  title: z.string().describe('Section title'),
  content: z.string().describe('Section content'),
  key_metrics: z.array(z.string()).describe('List of key metrics or data points'),
});

const ExecutiveReportSchema = z.object({
  report_title: z.string().describe('Title of the report'),
  executive_summary: z.string().describe('2-3 sentence executive summary'),
  sections: z.array(ReportSectionSchema).describe('Report sections'),
  recommendations: z.array(z.string()).describe('3-5 actionable recommendations'),
  risk_factors: z.array(z.string()).describe('Key risks to be aware of'),
});

// ── Chain-based tools ────────────────────────────────────

const analyzeMarketData = new DynamicStructuredTool({
  name: 'analyze_market_data',
  description: 'Analyze market position and competitive landscape for a company.',
  schema: z.object({
    company: z.string().describe('Company name'),
    sector: z.string().describe('Industry sector'),
  }),
  func: async ({ company, sector }) => {
    const llm = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', 'You are a market analyst. Provide a concise market analysis in 3-4 sentences covering position, trends, and competition.'],
      ['human', 'Analyze the market position of {company} in the {sector} sector.'],
    ]);
    const chain = prompt.pipe(llm).pipe(strParser);
    return chain.invoke({ company, sector });
  },
});

const generateFinancialMetrics = new DynamicStructuredTool({
  name: 'generate_financial_metrics',
  description: 'Calculate and interpret key financial metrics.',
  schema: z.object({
    company: z.string().describe('Company name'),
    revenue: z.string().describe("Annual revenue (e.g., '$5M', '$120M')"),
    growth_rate: z.string().describe("YoY growth rate (e.g., '25%', '-5%')"),
  }),
  func: async ({ company, revenue, growth_rate }) => {
    const llm = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', 'You are a financial analyst. Interpret these metrics and derive key insights including valuation implications.'],
      ['human', 'Company: {company}\nRevenue: {revenue}\nGrowth: {growth_rate}\n\nProvide 4-5 key financial insights.'],
    ]);
    const chain = prompt.pipe(llm).pipe(strParser);
    return chain.invoke({ company, revenue, growth_rate });
  },
});

const assessRisks = new DynamicStructuredTool({
  name: 'assess_risks',
  description: 'Assess key business risks for a company.',
  schema: z.object({
    company: z.string().describe('Company name'),
    sector: z.string().describe('Industry sector'),
    growth_rate: z.string().describe('Current growth rate'),
  }),
  func: async ({ company, sector, growth_rate }) => {
    const llm = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', 'You are a risk analyst. Identify the top 4-5 specific risks for this company, considering sector dynamics and growth trajectory.'],
      ['human', '{company} in {sector} growing at {growth_rate}'],
    ]);
    const chain = prompt.pipe(llm).pipe(strParser);
    return chain.invoke({ company, sector, growth_rate });
  },
});

const compileReport = new DynamicStructuredTool({
  name: 'compile_report',
  description: 'Compile all findings into a structured executive report.',
  schema: z.object({
    company: z.string().describe('Company name'),
    market_analysis: z.string().describe('Market analysis text'),
    financial_metrics: z.string().describe('Financial metrics text'),
    risk_assessment: z.string().describe('Risk assessment text'),
  }),
  func: async ({ company, market_analysis, financial_metrics, risk_assessment }) => {
    const llm = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
    const structuredLlm = llm.withStructuredOutput(ExecutiveReportSchema);
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', 'You are a business consultant creating an executive report. Return structured JSON with report_title, executive_summary, sections (each with title, content, key_metrics), recommendations, and risk_factors.'],
      ['human',
        'Create an executive report for {company}.\n\n' +
        'Market Analysis:\n{market_analysis}\n\n' +
        'Financial Metrics:\n{financial_metrics}\n\n' +
        'Risk Assessment:\n{risk_assessment}',
      ],
    ]);
    const chain = prompt.pipe(structuredLlm);

    try {
      const report = await chain.invoke({
        company,
        market_analysis,
        financial_metrics,
        risk_assessment,
      });

      let sectionsText = '';
      for (const sec of report.sections) {
        const metrics = sec.key_metrics.map((m: string) => `  * ${m}`).join('\n');
        sectionsText += `\n${sec.title}:\n${sec.content}\n${metrics}\n`;
      }

      const recs = report.recommendations
        .map((r: string, i: number) => `  ${i + 1}. ${r}`)
        .join('\n');
      const risks = report.risk_factors
        .map((r: string) => `  ! ${r}`)
        .join('\n');

      return (
        `${'='.repeat(60)}\n` +
        `${report.report_title}\n` +
        `${'='.repeat(60)}\n\n` +
        `EXECUTIVE SUMMARY:\n${report.executive_summary}\n` +
        `${sectionsText}\n` +
        `RECOMMENDATIONS:\n${recs}\n\n` +
        `KEY RISKS:\n${risks}\n`
      );
    } catch (e) {
      return `Report compilation error: ${e}`;
    }
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [analyzeMarketData, generateFinancialMetrics, assessRisks, compileReport];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

const ORCHESTRATOR_SYSTEM = `You are a senior business intelligence orchestrator.
For each company analysis request:
1. Analyze the market data first
2. Calculate and interpret financial metrics
3. Assess key business risks
4. Compile everything into a structured executive report
Always call all four tools and combine their outputs in the final report.`;

async function runOrchestrationAgent(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(ORCHESTRATOR_SYSTEM),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 8; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runOrchestrationAgent(input.input);
    return { output };
  },
});

(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agentRunnable);
    await runtime.serve(agentRunnable);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // agentRunnable,
    // 'Generate a complete executive report for TechStartup Inc., ' +
    // 'a SaaS company in the cloud infrastructure sector with $12M annual revenue ' +
    // 'and 45% year-over-year growth.'
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('25-advanced-orchestration.ts') || process.argv[1]?.endsWith('25-advanced-orchestration.js')) {
  main().catch(console.error);
}
