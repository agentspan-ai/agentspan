import { serializeLangGraph, _setDebugLog } from '../src/frameworks/langgraph-serializer.js';

// Import the same graph the example builds
import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

const AnalysisState = Annotation.Root({
  text: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  sentiment: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  keywords: Annotation<string[]>({ reducer: (_: string[], n: string[]) => n ?? _, default: () => [] }),
  summary: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
});

async function analyzeSentiment(state: any) {
  const response = await llm.invoke([
    new SystemMessage('Classify the sentiment. Return ONLY: positive, negative, or neutral.'),
    new HumanMessage(state.text),
  ]);
  return { sentiment: (response.content as string).trim().toLowerCase() };
}
async function extractKeywords(state: any) {
  const response = await llm.invoke([
    new SystemMessage('Extract 3-5 keywords. Return comma-separated list only.'),
    new HumanMessage(state.text),
  ]);
  return { keywords: (response.content as string).split(',').map(k => k.trim()) };
}
async function summarizeText(state: any) {
  const response = await llm.invoke([
    new SystemMessage('Summarize this text in one sentence.'),
    new HumanMessage(state.text),
  ]);
  return { summary: (response.content as string).trim() };
}

const analysisBuilder = new StateGraph(AnalysisState);
analysisBuilder.addNode('sentiment_node', analyzeSentiment);
analysisBuilder.addNode('keywords_node', extractKeywords);
analysisBuilder.addNode('summarize', summarizeText);
analysisBuilder.addEdge(START, 'sentiment_node');
analysisBuilder.addEdge('sentiment_node', 'keywords_node');
analysisBuilder.addEdge('keywords_node', 'summarize');
analysisBuilder.addEdge('summarize', END);
const analysisSubgraph = analysisBuilder.compile({ name: "analysis_subgraph" });

const DocumentState = Annotation.Root({
  document: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  analysis_text: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  sentiment: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  keywords: Annotation<string[]>({ reducer: (_: string[], n: string[]) => n ?? _, default: () => [] }),
  summary: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
  report: Annotation<string>({ reducer: (_: string, n: string) => n ?? _, default: () => '' }),
});

function prepare(state: any) { return { analysis_text: state.document }; }
async function runAnalysis(state: any) {
  const result = await analysisSubgraph.invoke({ text: state.analysis_text });
  return { sentiment: result.sentiment ?? '', keywords: result.keywords ?? [], summary: result.summary ?? '' };
}
function buildReport(state: any) {
  return { report: `Sentiment: ${state.sentiment}\nKeywords: ${(state.keywords ?? []).join(', ')}\nSummary: ${state.summary ?? ''}` };
}

const parentBuilder = new StateGraph(DocumentState);
parentBuilder.addNode('prepare', prepare);
parentBuilder.addNode('analysis', runAnalysis);
parentBuilder.addNode('build_report', buildReport);
parentBuilder.addEdge(START, 'prepare');
parentBuilder.addEdge('prepare', 'analysis');
parentBuilder.addEdge('analysis', 'build_report');
parentBuilder.addEdge('build_report', END);
const graph = parentBuilder.compile({ name: "document_pipeline_with_subgraph" });
(graph as any)._agentspan = { model: 'openai/gpt-4o-mini', tools: [], framework: 'langgraph' };

const [rawConfig, workers] = serializeLangGraph(graph);
console.log('=== rawConfig ===');
console.log(JSON.stringify(rawConfig, null, 2));
console.log('\n=== workers ===');
console.log(workers.map(w => w.name));
process.exit(0);
