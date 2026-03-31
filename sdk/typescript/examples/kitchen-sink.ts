/**
 * Kitchen Sink — Content Publishing Platform
 *
 * A single mega-workflow that exercises every Agentspan SDK feature (89 features).
 * See docs/sdk-design/kitchen-sink.md for the full scenario specification.
 *
 * Demonstrates:
 *   - All 8 multi-agent strategies
 *   - All tool types (worker, http, mcp, api, agent_tool, human, media, RAG)
 *   - All guardrail types (regex, llm, custom, external) with all OnFail modes
 *   - HITL (approve, reject, feedback, UserProxyAgent, human_tool)
 *   - Memory (conversation + semantic)
 *   - Code execution (local, docker, jupyter, serverless)
 *   - Credentials (all isolation modes, CredentialFile)
 *   - Streaming (sync), termination, handoffs, callbacks
 *   - Structured output, prompt templates, agent chaining, gate conditions
 *   - Extended thinking, planner mode, required_tools, include_contents
 *   - GPTAssistantAgent, agentTool(), scatterGather()
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL, AGENTSPAN_LLM_MODEL env vars
 *   - For full execution: Docker, MCP server, credential store
 */

import { z } from 'zod';

import {
  // Core
  Agent,
  AgentRuntime,
  PromptTemplate,
  scatterGather,
  AgentConfigSerializer,

  // Tools
  tool,
  httpTool,
  mcpTool,
  apiTool,
  agentTool,
  humanTool,
  imageTool,
  audioTool,
  videoTool,
  pdfTool,
  searchTool,
  indexTool,
  getToolDef,

  // Decorators
  agent,

  // Guardrails
  guardrail,
  RegexGuardrail,
  LLMGuardrail,

  // Results / Stream / Events
  EventTypes,
  AgentStream,

  // Runtime
  configure,
  run,
  start,
  stream,
  deploy,
  plan,
  shutdown,

  // Termination
  TerminationCondition,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,

  // Handoffs
  OnToolResult,
  OnTextMention,
  OnCondition,
  TextGate,
  gate,

  // Memory
  ConversationMemory,
  SemanticMemory,
  InMemoryStore,

  // Callbacks
  CallbackHandler,
  CALLBACK_POSITIONS,
  getCallbackWorkerNames,

  // Code Execution
  LocalCodeExecutor,
  DockerCodeExecutor,
  JupyterCodeExecutor,
  ServerlessCodeExecutor,

  // Credentials
  getCredential,

  // Extended
  UserProxyAgent,
  GPTAssistantAgent,

  // Discovery & Tracing
  discoverAgents,
  isTracingEnabled,
} from '../src/index.js';

import type {
  GuardrailResult,
  ToolContext,
  CredentialFile,
  CodeExecutionConfig,
  CliConfig,
  AgentResult,
} from '../src/index.js';

// ── Settings ─────────────────────────────────────────────

const LLM_MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// ── Mock data (equivalent to Python kitchen_sink_helpers) ─

const MOCK_RESEARCH_DATA: Record<string, unknown> = {
  quantum_computing: {
    title: 'Quantum Computing Advances 2026',
    findings: ['Error correction breakthrough', 'New qubit architectures'],
  },
};

const MOCK_PAST_ARTICLES = [
  { title: 'Quantum Computing 101', content: 'Introduction to qubits...' },
  { title: 'AI and Quantum Synergy', content: 'How AI leverages quantum...' },
  { title: 'Classical vs Quantum', content: 'Comparing classical and quantum...' },
];

function containsSqlInjection(input: string): boolean {
  const patterns = ['DROP TABLE', 'DELETE FROM', '; --', "' OR '1'='1"];
  return patterns.some((p) => input.toUpperCase().includes(p.toUpperCase()));
}

// Callback log for tracking lifecycle events
const callbackLog: Array<{ type: string; data: Record<string, unknown> }> = [];

// ═══════════════════════════════════════════════════════════════════════
// STAGE 1: Intake & Classification
// Features: #5 Router, #30 structured output, #63 PromptTemplate, @agent
// ═══════════════════════════════════════════════════════════════════════

const ClassificationResult = z.object({
  category: z.enum(['tech', 'business', 'creative']).describe('Article category'),
  priority: z.number().describe('Priority level (1=highest)'),
  tags: z.array(z.string()).describe('Relevant tags'),
  metadata: z.record(z.string(), z.string()).optional().describe('Additional metadata'),
}).describe('ClassificationResult');

// @agent decorator equivalents
const techClassifier = agent(
  () => 'Classify tech articles.',
  { name: 'tech_classifier', model: LLM_MODEL },
);

const businessClassifier = agent(
  () => 'Classify business articles.',
  { name: 'business_classifier', model: LLM_MODEL },
);

const creativeClassifier = agent(
  () => 'Classify creative articles.',
  { name: 'creative_classifier', model: LLM_MODEL },
);

const intakeRouter = new Agent({
  name: 'intake_router',
  model: LLM_MODEL,
  instructions: new PromptTemplate(
    'article-classifier',
    { categories: 'tech, business, creative' },
  ),
  agents: [techClassifier, businessClassifier, creativeClassifier],
  strategy: 'router',
  router: new Agent({
    name: 'category_router',
    model: LLM_MODEL,
    instructions: 'Route to the appropriate classifier based on the article topic.',
  }),
  outputType: ClassificationResult,
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 2: Research Team
// Features: #4 Parallel, #76 scatter_gather, #10 native tool,
//   #11 http_tool, #12 mcp_tool, #89 api_tool, #18 ToolContext,
//   #19 tool credentials, #21 external tool, #52 isolated creds,
//   #53 in-process creds, #55 HTTP header creds, #56 MCP creds,
//   CredentialFile
// ═══════════════════════════════════════════════════════════════════════

// -- Native tool with ToolContext + file-based credentials (#10, #18, #19, #52) --
const researchDatabase = tool(
  async (args: { query: string }, ctx?: ToolContext) => {
    const session = ctx?.sessionId ?? 'unknown';
    const execution = ctx?.executionId ?? 'unknown';
    return {
      query: args.query,
      sessionId: session,
      executionId: execution,
      results: MOCK_RESEARCH_DATA['quantum_computing'] ?? {},
    };
  },
  {
    name: 'research_database',
    description: 'Search internal research database.',
    inputSchema: z.object({ query: z.string() }),
    credentials: [{ envVar: 'RESEARCH_API_KEY' } as CredentialFile],
  },
);

// -- In-process credential access (#53) --
const analyzeTrends = tool(
  async (args: { topic: string }) => {
    let key: string;
    try {
      key = await getCredential('ANALYTICS_KEY');
    } catch {
      key = '';
    }
    return { topic: args.topic, trendScore: 0.87, keyPresent: Boolean(key) };
  },
  {
    name: 'analyze_trends',
    description: 'Analyze trending topics using analytics API.',
    inputSchema: z.object({ topic: z.string() }),
    isolated: false,
    credentials: ['ANALYTICS_KEY'],
  },
);

// -- HTTP tool with credential header substitution (#11, #55) --
const webSearch = httpTool({
  name: 'web_search',
  description: 'Search the web for recent articles and papers.',
  url: 'https://api.example.com/search',
  method: 'GET',
  headers: { Authorization: 'Bearer ${SEARCH_API_KEY}' },
  inputSchema: {
    type: 'object',
    properties: { q: { type: 'string' } },
    required: ['q'],
  },
  credentials: ['SEARCH_API_KEY'],
});

// -- MCP tool with credentials (#12, #56) --
const mcpFactChecker = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  name: 'fact_checker',
  description: 'Verify factual claims using knowledge base.',
  toolNames: ['verify_claim', 'check_source'],
  credentials: ['MCP_AUTH_TOKEN'],
});

// -- API tool auto-discovered from OpenAPI spec (#89) --
const petstoreApi = apiTool({
  url: 'https://petstore3.swagger.io/api/v3/openapi.json',
  name: 'petstore',
  maxTools: 5,
});

// -- External tool (no local worker) (#21) --
const externalResearchAggregator = tool(
  async (_args: { query: string; sources?: number }) => {
    // Stub — dispatched to remote worker
    return {};
  },
  {
    name: 'external_research_aggregator',
    description: 'Aggregate research from external sources. Runs on remote worker.',
    inputSchema: z.object({
      query: z.string(),
      sources: z.number().optional(),
    }),
    external: true,
  },
);

// -- Researcher agent for scatter_gather --
const researcherWorker = new Agent({
  name: 'research_worker',
  model: LLM_MODEL,
  instructions: 'Research the given topic thoroughly using available tools.',
  tools: [researchDatabase, webSearch, mcpFactChecker, externalResearchAggregator],
  credentials: ['SEARCH_API_KEY', 'MCP_AUTH_TOKEN'],
});

// -- scatter_gather (#76) --
const researchCoordinator = scatterGather({
  name: 'research_coordinator',
  model: LLM_MODEL,
  instructions:
    'Create research tasks for the topic: web search, data analysis, ' +
    'and fact checking. Dispatch workers for each.',
  workers: [researcherWorker],
});

const dataAnalyst = new Agent({
  name: 'data_analyst',
  model: LLM_MODEL,
  instructions: 'Analyze data trends for the topic.',
  tools: [analyzeTrends, petstoreApi],
});

const researchTeam = new Agent({
  name: 'research_team',
  agents: [researchCoordinator, dataAnalyst],
  strategy: 'parallel',
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 3: Writing Pipeline
// Features: #3 Sequential (>>), #31 ConversationMemory,
//   #32 SemanticMemory, #39 agent chaining, #62 Callbacks (all 6),
//   #77 stop_when
// ═══════════════════════════════════════════════════════════════════════

const semanticStore = new InMemoryStore();
const semanticMem = new SemanticMemory({ store: semanticStore });
for (const article of MOCK_PAST_ARTICLES) {
  semanticMem.add(`Past article: ${article.title}`);
}

const recallPastArticles = tool(
  async (args: { query: string }) => {
    const results = semanticMem.search(args.query, 3);
    return { results: results.map((r) => ({ content: r.content })) };
  },
  {
    name: 'recall_past_articles',
    description: 'Retrieve relevant past articles from semantic memory.',
    inputSchema: z.object({ query: z.string() }),
  },
);

// -- CallbackHandler (#62) --
class PublishingCallbackHandler extends CallbackHandler {
  async onAgentStart(agentName: string): Promise<void> {
    callbackLog.push({ type: 'before_agent', data: { agentName } });
  }
  async onAgentEnd(agentName: string): Promise<void> {
    callbackLog.push({ type: 'after_agent', data: { agentName } });
  }
  async onModelStart(agentName: string, messages: unknown[]): Promise<void> {
    callbackLog.push({ type: 'before_model', data: { agentName, messageCount: messages.length } });
  }
  async onModelEnd(agentName: string): Promise<void> {
    callbackLog.push({ type: 'after_model', data: { agentName } });
  }
  async onToolStart(agentName: string, toolName: string): Promise<void> {
    callbackLog.push({ type: 'before_tool', data: { agentName, toolName } });
  }
  async onToolEnd(agentName: string, toolName: string): Promise<void> {
    callbackLog.push({ type: 'after_tool', data: { agentName, toolName } });
  }
}

function stopWhenArticleComplete(messages: unknown[]): boolean {
  if (messages.length === 0) return false;
  const last = messages[messages.length - 1];
  if (last && typeof last === 'object') {
    const content = (last as Record<string, unknown>).content;
    if (typeof content === 'string' && content.includes('ARTICLE_COMPLETE')) {
      return true;
    }
  }
  return false;
}

const draftWriter = new Agent({
  name: 'draft_writer',
  model: LLM_MODEL,
  instructions: 'Write a comprehensive article draft based on research findings.',
  tools: [recallPastArticles],
  memory: new ConversationMemory({ maxMessages: 50 }),
  callbacks: [new PublishingCallbackHandler()],
});

const editorAgent = new Agent({
  name: 'editor',
  model: LLM_MODEL,
  instructions:
    'Review and edit the article. Fix grammar, improve clarity. ' +
    'When done, include ARTICLE_COMPLETE.',
  stopWhen: stopWhenArticleComplete,
});

// Sequential pipeline via .pipe() (#39)
const writingPipeline = draftWriter.pipe(editorAgent);

// ═══════════════════════════════════════════════════════════════════════
// STAGE 4: Review & Safety
// Features: #22 RegexGuardrail, #23 LLMGuardrail, #24 custom @guardrail,
//   #25 external guardrail, #20 tool guardrail,
//   #26 RETRY, #27 RAISE, #28 FIX, #29 HUMAN
// ═══════════════════════════════════════════════════════════════════════

// -- Regex guardrail (on_fail=RETRY) (#22, #26) --
const piiGuardrail = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: [
    '\\b\\d{3}-\\d{2}-\\d{4}\\b',
    '\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b',
  ],
  mode: 'block',
  position: 'output',
  onFail: 'retry',
  message: 'PII detected. Redact all personal information.',
});

// -- LLM guardrail (on_fail=FIX) (#23, #28) --
const biasGuardrail = new LLMGuardrail({
  name: 'bias_detector',
  model: 'openai/gpt-4o-mini',
  policy: 'Check for biased language or stereotypes. If found, provide corrected version.',
  position: 'output',
  onFail: 'fix',
  maxTokens: 10000,
});

// -- Custom guardrail (on_fail=HUMAN) (#24, #29) --
const factValidator = guardrail(
  (content: string): GuardrailResult => {
    const redFlags = ['the best', 'the worst', 'always', 'never', 'guaranteed'];
    const found = redFlags.filter((rf) => content.toLowerCase().includes(rf));
    if (found.length > 0) {
      return { passed: false, message: `Unverifiable claims: ${found.join(', ')}` };
    }
    return { passed: true };
  },
  { name: 'fact_validator', position: 'output', onFail: 'human' },
);

// -- External guardrail (on_fail=RAISE) (#25, #27) --
const complianceGuardrail = guardrail.external({
  name: 'compliance_check',
  position: 'output',
  onFail: 'raise',
});

// -- Tool guardrail (input validation) (#20) --
const sqlInjectionGuard = guardrail(
  (content: string): GuardrailResult => {
    if (containsSqlInjection(content)) {
      return { passed: false, message: 'SQL injection detected.' };
    }
    return { passed: true };
  },
  { name: 'sql_injection_guard', position: 'input', onFail: 'raise' },
);

const safeSearch = tool(
  async (args: { query: string }) => {
    return { query: args.query, results: ['result1', 'result2'] };
  },
  {
    name: 'safe_search',
    description: 'Search with SQL injection protection.',
    inputSchema: z.object({ query: z.string() }),
    guardrails: [sqlInjectionGuard],
  },
);

const reviewAgent = new Agent({
  name: 'safety_reviewer',
  model: LLM_MODEL,
  instructions: 'Review the article for safety and compliance.',
  tools: [safeSearch],
  guardrails: [
    piiGuardrail.toGuardrailDef(),     // #26 on_fail=RETRY
    biasGuardrail.toGuardrailDef(),     // #28 on_fail=FIX
    { ...factValidator, onFail: 'human' as const, position: 'output' as const }, // #29 on_fail=HUMAN
    complianceGuardrail,                 // #27 on_fail=RAISE (external)
  ],
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 5: Editorial Approval
// Features: #17 approval_required, #40 approve, #41 reject,
//   #42 feedback/respond, #14 human_tool, #65 UserProxyAgent
// ═══════════════════════════════════════════════════════════════════════

const publishArticle = tool(
  async (args: { title: string; content: string; platform: string }) => {
    return { status: 'published', title: args.title, platform: args.platform };
  },
  {
    name: 'publish_article',
    description: 'Publish article to platform. Requires editorial approval.',
    inputSchema: z.object({
      title: z.string(),
      content: z.string(),
      platform: z.string(),
    }),
    approvalRequired: true,
  },
);

const editorialQuestion = humanTool({
  name: 'ask_editor',
  description: 'Ask the editor a question about the article.',
  inputSchema: {
    type: 'object',
    properties: { question: { type: 'string' } },
    required: ['question'],
  },
});

const editorialReviewer = new UserProxyAgent({
  name: 'editorial_reviewer',
  mode: 'TERMINATE',
  instructions: 'You are the editorial reviewer. Provide feedback on article quality.',
});

const editorialAgent = new Agent({
  name: 'editorial_approval',
  model: LLM_MODEL,
  instructions: 'Review the article, ask questions, get approval before publishing.',
  tools: [publishArticle, editorialQuestion],
  agents: [editorialReviewer],
  strategy: 'handoff',
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 6: Translation & Discussion
// Features: #6 round_robin, #7 random, #8 swarm, #9 manual,
//   #35 OnTextMention, #37 allowed_transitions, #38 introductions
// ═══════════════════════════════════════════════════════════════════════

const spanishTranslator = new Agent({
  name: 'spanish_translator',
  model: LLM_MODEL,
  instructions: 'You translate articles to Spanish with a formal tone.',
  introduction: 'I am the Spanish translator, specializing in formal academic translations.',
});

const frenchTranslator = new Agent({
  name: 'french_translator',
  model: LLM_MODEL,
  instructions: 'You translate articles to French with a conversational tone.',
  introduction: 'I am the French translator, specializing in conversational translations.',
});

const germanTranslator = new Agent({
  name: 'german_translator',
  model: LLM_MODEL,
  instructions: 'You translate articles to German with a technical tone.',
  introduction: 'I am the German translator, specializing in technical translations.',
});

// Round-robin debate (#6)
const toneDebate = new Agent({
  name: 'tone_debate',
  agents: [spanishTranslator, frenchTranslator, germanTranslator],
  strategy: 'round_robin',
  maxTurns: 6,
});

// Swarm with OnTextMention handoff (#8, #35)
const translationSwarm = new Agent({
  name: 'translation_swarm',
  agents: [spanishTranslator, frenchTranslator, germanTranslator],
  strategy: 'swarm',
  handoffs: [
    new OnTextMention({ text: 'Spanish', target: 'spanish_translator' }),
    new OnTextMention({ text: 'French', target: 'french_translator' }),
    new OnTextMention({ text: 'German', target: 'german_translator' }),
  ],
  allowedTransitions: {
    spanish_translator: ['french_translator', 'german_translator'],
    french_translator: ['spanish_translator', 'german_translator'],
    german_translator: ['spanish_translator', 'french_translator'],
  },
});

// Random strategy (#7)
const titleBrainstorm = new Agent({
  name: 'title_brainstorm',
  agents: [spanishTranslator, frenchTranslator, germanTranslator],
  strategy: 'random',
  maxTurns: 3,
});

// Manual selection (#9)
const manualTranslation = new Agent({
  name: 'manual_translation',
  agents: [spanishTranslator, frenchTranslator, germanTranslator],
  strategy: 'manual',
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 7: Publishing Pipeline
// Features: #2 Handoff, #33 composable termination, #34 OnToolResult,
//   #36 OnCondition, #71 gate condition, #88 external agent
// ═══════════════════════════════════════════════════════════════════════

const formatCheck = tool(
  async (args: { content: string }) => {
    return { formatted: true, issues: [] };
  },
  {
    name: 'format_check',
    description: 'Check article formatting.',
    inputSchema: z.object({ content: z.string() }),
  },
);

function shouldHandoffToPublisher(messages: unknown[]): boolean {
  if (messages.length === 0) return false;
  const last = messages[messages.length - 1];
  if (last && typeof last === 'object') {
    const content = String((last as Record<string, unknown>).content ?? '');
    return content.includes('formatted');
  }
  return false;
}

const formatter = new Agent({
  name: 'formatter',
  model: LLM_MODEL,
  instructions: 'Format the article according to publishing guidelines.',
  tools: [formatCheck],
});

// External agent (#88)
const externalPublisher = new Agent({
  name: 'external_publisher',
  external: true,
  instructions: 'Publish to the CMS platform.',
});

const publishingPipeline = new Agent({
  name: 'publishing_pipeline',
  model: LLM_MODEL,
  instructions: 'Manage the publishing workflow from formatting to publication.',
  agents: [formatter, externalPublisher],
  strategy: 'handoff',
  handoffs: [
    new OnToolResult({ target: 'external_publisher', toolName: 'format_check' }),
    new OnCondition({ target: 'external_publisher', condition: shouldHandoffToPublisher }),
  ],
  termination: new TextMention('PUBLISHED').or(
    new MaxMessage(50).and(new TokenUsageCondition({ maxTotalTokens: 100000 })),
  ),
  gate: new TextGate({ text: 'APPROVED' }),
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 8: Analytics & Reporting
// Features: #13 agent_tool, #15 media tools, #16 RAG tools,
//   #58-61 code executors, #64 token tracking, #66 GPTAssistantAgent,
//   #67 thinking, #68 include_contents, #69 planner, #70 required_tools,
//   #72 CLI config
// ═══════════════════════════════════════════════════════════════════════

// -- Code executors (#58-61) --
const localExecutor = new LocalCodeExecutor({ timeout: 10 });
const dockerExecutor = new DockerCodeExecutor({ image: 'python:3.12-slim', timeout: 15 });
const jupyterExecutor = new JupyterCodeExecutor({ timeout: 30 });
const serverlessExecutor = new ServerlessCodeExecutor({
  endpoint: 'https://api.example.com/functions/analytics',
  timeout: 30,
});

// -- Media tools (#15) --
const articleThumbnail = imageTool({
  name: 'generate_thumbnail',
  description: 'Generate an article thumbnail image.',
  llmProvider: 'openai',
  model: 'dall-e-3',
});

const audioSummary = audioTool({
  name: 'generate_audio_summary',
  description: 'Generate an audio summary of the article.',
  llmProvider: 'openai',
  model: 'tts-1',
});

const videoHighlight = videoTool({
  name: 'generate_video_highlight',
  description: 'Generate a short video highlight.',
  llmProvider: 'openai',
  model: 'sora',
});

const articlePdf = pdfTool({
  name: 'generate_article_pdf',
  description: 'Generate a PDF version of the article.',
});

// -- RAG tools (#16) --
const articleIndexer = indexTool({
  name: 'index_article',
  description: 'Index the article for future retrieval.',
  vectorDb: 'pgvector',
  index: 'articles',
  embeddingModelProvider: 'openai',
  embeddingModel: 'text-embedding-3-small',
});

const articleSearchTool = searchTool({
  name: 'search_articles',
  description: 'Search for related articles.',
  vectorDb: 'pgvector',
  index: 'articles',
  embeddingModelProvider: 'openai',
  embeddingModel: 'text-embedding-3-small',
  maxResults: 5,
});

// -- agent_tool: wrap sub-agent as callable tool (#13) --
const quickResearcher = new Agent({
  name: 'quick_researcher',
  model: LLM_MODEL,
  instructions: 'Do a quick research lookup on the given topic.',
});

const researchSubtool = agentTool(quickResearcher, {
  name: 'quick_research',
  description: 'Quick research lookup as a tool.',
});

// -- GPTAssistantAgent (#66) --
const gptAssistant = new GPTAssistantAgent({
  name: 'openai_research_assistant',
  assistantId: 'asst_placeholder_id',
  model: 'gpt-4o',
  instructions: 'You are a research assistant with access to code interpreter.',
});

// -- ArticleReport output schema --
const ArticleReport = z.object({
  wordCount: z.number(),
  sentimentScore: z.number(),
  readabilityGrade: z.string(),
  topKeywords: z.array(z.string()),
}).describe('ArticleReport');

const analyticsAgent = new Agent({
  name: 'analytics_agent',
  model: LLM_MODEL,
  instructions: 'Analyze the published article and generate a comprehensive analytics report.',
  tools: [
    localExecutor.asTool(),
    dockerExecutor.asTool('run_sandboxed'),
    jupyterExecutor.asTool('run_notebook'),
    serverlessExecutor.asTool('run_cloud'),
    articleThumbnail,
    audioSummary,
    videoHighlight,
    articlePdf,
    articleIndexer,
    articleSearchTool,
    researchSubtool,
  ],
  agents: [gptAssistant],
  strategy: 'handoff',
  thinkingBudgetTokens: 2048,            // #67
  includeContents: 'default',             // #68
  outputType: ArticleReport,              // #30
  requiredTools: ['index_article'],       // #70
  codeExecutionConfig: {                  // #58
    enabled: true,
    allowedLanguages: ['python', 'shell'],
    allowedCommands: ['python3', 'pip'],
    timeout: 30,
  },
  cliConfig: {                            // #72
    enabled: true,
    allowedCommands: ['git', 'gh'],
    timeout: 30,
  },
  metadata: { stage: 'analytics', version: '1.0' },
  planner: true,                          // #69
});

// ═══════════════════════════════════════════════════════════════════════
// FULL PIPELINE (hierarchical composition of all stages)
// ═══════════════════════════════════════════════════════════════════════

const fullPipeline = new Agent({
  name: 'content_publishing_platform',
  model: LLM_MODEL,
  instructions:
    'You are a content publishing platform. Process article requests ' +
    'through all pipeline stages: classification, research, writing, ' +
    'review, editorial approval, translation, publishing, and analytics.',
  agents: [
    intakeRouter,           // Stage 1
    researchTeam,           // Stage 2
    writingPipeline,        // Stage 3 (sequential via .pipe())
    reviewAgent,            // Stage 4
    editorialAgent,         // Stage 5
    translationSwarm,       // Stage 6
    publishingPipeline,     // Stage 7
    analyticsAgent,         // Stage 8
  ],
  strategy: 'sequential',
  termination: new TextMention('PIPELINE_COMPLETE').or(new MaxMessage(200)),
});

// ═══════════════════════════════════════════════════════════════════════
// STAGE 9: Execution Modes
// Features: #43-51 all execution modes, #74 discover_agents, #75 tracing
// ═══════════════════════════════════════════════════════════════════════

const PROMPT =
  'Write a comprehensive tech article about quantum computing ' +
  'advances in 2026, get it reviewed, translate to Spanish, ' +
  'and publish.';

async function main() {
  // Feature #75: OTel tracing check
  if (isTracingEnabled()) {
    console.log('[tracing] OpenTelemetry tracing is enabled');
  }

  const runtime = new AgentRuntime();

  // ── Feature #49: deploy ────────────────────────────────
  console.log('=== Deploy ===');
  const deployment = await runtime.deploy(fullPipeline);
  console.log(`  Deployed: ${deployment.workflowName} (${deployment.agentName})`);

  // ── Feature #51: plan (dry-run) ────────────────────────
  console.log('\n=== Plan (dry-run) ===');
  const executionPlan = await runtime.plan(fullPipeline);
  console.log('  Plan compiled successfully');

  // ── Feature #43: stream (sync SSE + HITL) ──────────────
  console.log('\n=== Stream Execution ===');
  const agentStream = await runtime.stream(fullPipeline, PROMPT);
  console.log(`  Execution: ${agentStream.executionId}\n`);

  const hitlState = { approved: 0, rejected: 0, feedback: 0 };

  for await (const event of agentStream) {
    switch (event.type) {
      case EventTypes.THINKING:
        console.log(`  [thinking] ${(event.content ?? '').slice(0, 80)}...`);
        break;
      case EventTypes.TOOL_CALL:
        console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
        break;
      case EventTypes.TOOL_RESULT:
        console.log(`  [tool_result] ${event.toolName} -> ${String(event.result).slice(0, 80)}...`);
        break;
      case EventTypes.HANDOFF:
        console.log(`  [handoff] -> ${event.target}`);
        break;
      case EventTypes.GUARDRAIL_PASS:
        console.log(`  [guardrail_pass] ${event.guardrailName}`);
        break;
      case EventTypes.GUARDRAIL_FAIL:
        console.log(`  [guardrail_fail] ${event.guardrailName}: ${event.content}`);
        break;
      case EventTypes.MESSAGE:
        console.log(`  [message] ${(event.content ?? '').slice(0, 80)}...`);
        break;
      case EventTypes.WAITING:
        console.log('\n  --- HITL: Approval required ---');
        if (hitlState.feedback === 0) {
          await agentStream.send('Please add more details about quantum error correction.');
          hitlState.feedback++;
          console.log('  Sent feedback (revision request)\n');
        } else if (hitlState.rejected === 0) {
          await agentStream.reject('Title needs improvement');
          hitlState.rejected++;
          console.log('  Rejected (title needs work)\n');
        } else {
          await agentStream.approve();
          hitlState.approved++;
          console.log('  Approved\n');
        }
        break;
      case EventTypes.ERROR:
        console.log(`  [error] ${event.content}`);
        break;
      case EventTypes.DONE:
        console.log('\n  [done] Pipeline complete');
        break;
    }
  }

  const result = await agentStream.getResult();
  result.printResult();

  // ── Feature #64: Token tracking ────────────────────────
  if (result.tokenUsage) {
    console.log(`\nTotal tokens: ${result.tokenUsage.totalTokens}`);
    console.log(`  Prompt: ${result.tokenUsage.promptTokens}`);
    console.log(`  Completion: ${result.tokenUsage.completionTokens}`);
  }

  // ── Callback log ───────────────────────────────────────
  console.log(`\nCallback events: ${callbackLog.length}`);
  for (const ev of callbackLog.slice(0, 5)) {
    console.log(`  ${ev.type}:`, ev.data);
  }

  // ── Feature #48: start + polling ───────────────────────
  console.log('\n=== Start + Polling ===');
  const handle = await runtime.start(fullPipeline, PROMPT);
  console.log(`  Started: ${handle.executionId}`);
  const status = await handle.getStatus();
  console.log(`  Status: ${status.status}, Running: ${status.isRunning}`);

  // ── Feature #46: top-level convenience APIs ────────────
  console.log('\n=== Top-Level Convenience API ===');
  configure({});
  const simpleAgent = new Agent({
    name: 'simple_test',
    model: LLM_MODEL,
    instructions: 'Say hello.',
  });
  const simpleResult = await run(simpleAgent, 'Hello!');
  console.log(`  run() status: ${simpleResult.status}`);

  // ── Feature #74: discover_agents ───────────────────────
  console.log('\n=== Discover Agents ===');
  try {
    const discovered = await discoverAgents('sdk/typescript/examples');
    console.log(`  Discovered ${discovered.length} agents`);
  } catch (e: unknown) {
    console.log(`  Discovery: ${e instanceof Error ? e.message : e}`);
  }

  // ── Feature #50: serve (blocking — commented) ──────────
  // await serve(); // Starts worker poll loop; uncomment to run as server

  // ── Cleanup ────────────────────────────────────────────
  await shutdown();
  console.log('\n=== Kitchen Sink Complete ===');
}

// ═══════════════════════════════════════════════════════════════════════
// EXPORTS for structural testing
// ═══════════════════════════════════════════════════════════════════════

export {
  // Stage 1
  intakeRouter,
  techClassifier,
  businessClassifier,
  creativeClassifier,
  ClassificationResult,

  // Stage 2
  researchTeam,
  researchCoordinator,
  dataAnalyst,
  researcherWorker,
  researchDatabase,
  analyzeTrends,
  webSearch,
  mcpFactChecker,
  petstoreApi,
  externalResearchAggregator,

  // Stage 3
  writingPipeline,
  draftWriter,
  editorAgent,
  semanticMem,
  recallPastArticles,
  callbackLog,

  // Stage 4
  reviewAgent,
  piiGuardrail,
  biasGuardrail,
  factValidator,
  complianceGuardrail,
  sqlInjectionGuard,
  safeSearch,

  // Stage 5
  editorialAgent,
  publishArticle,
  editorialQuestion,
  editorialReviewer,

  // Stage 6
  toneDebate,
  translationSwarm,
  titleBrainstorm,
  manualTranslation,
  spanishTranslator,
  frenchTranslator,
  germanTranslator,

  // Stage 7
  publishingPipeline,
  formatter,
  externalPublisher,
  formatCheck,

  // Stage 8
  analyticsAgent,
  gptAssistant,
  quickResearcher,
  researchSubtool,
  ArticleReport,

  // Full pipeline
  fullPipeline,
};

// Only run main() when executed directly (not imported)
if (typeof process !== 'undefined' && (process.argv[1]?.endsWith('kitchen-sink.ts') || process.argv[1]?.endsWith('kitchen-sink.js'))) {
  main().catch(console.error);
}
