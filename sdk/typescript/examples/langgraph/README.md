# LangGraph + Agentspan

Keep your existing LangGraph code. Add agentspan metadata and run with `runtime.run()`.

## createReactAgent

<table>
<tr><th>Before (vanilla LangGraph)</th><th>After (agentspan)</th></tr>
<tr><td>

```typescript
import { createReactAgent }
  from '@langchain/langgraph/prebuilt';
import { ChatOpenAI }
  from '@langchain/openai';
import { DynamicStructuredTool }
  from '@langchain/core/tools';
import { z } from 'zod';



const llm = new ChatOpenAI({
  model: 'gpt-4o-mini',
  temperature: 0,
});

const calculate = new DynamicStructuredTool({
  name: 'calculate',
  description: 'Evaluate a math expression.',
  schema: z.object({
    expression: z.string(),
  }),
  func: async ({ expression }) =>
    String(eval(expression)),
});

const graph = createReactAgent({
  llm,
  tools: [calculate],
});




const result = await graph.invoke({
  messages: [
    { role: 'user', content: 'What is 2+2?' }
  ],
});
```

</td><td>

```typescript
import { createReactAgent }
  from '@langchain/langgraph/prebuilt';
import { ChatOpenAI }
  from '@langchain/openai';
import { DynamicStructuredTool }
  from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '@agentspan-ai/sdk';
// ^^^ add agentspan import

const llm = new ChatOpenAI({
  model: 'gpt-4o-mini',
  temperature: 0,
});

const calculate = new DynamicStructuredTool({
  name: 'calculate',
  description: 'Evaluate a math expression.',
  schema: z.object({
    expression: z.string(),
  }),
  func: async ({ expression }) =>
    String(eval(expression)),
});

const graph = createReactAgent({
  llm,
  tools: [calculate],
});

// Add agentspan metadata
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [calculate],
  framework: 'langgraph',
};

const runtime = new AgentRuntime();
const result = await runtime.run(
// ^^^ runtime.run() instead of graph.invoke()
  graph, 'What is 2+2?',
);
result.printResult();
await runtime.shutdown();
```

</td></tr>
</table>

## Custom StateGraph

Same pattern — build the graph normally, attach metadata, run with `runtime.run()`.

<table>
<tr><th>Before (vanilla LangGraph)</th><th>After (agentspan)</th></tr>
<tr><td>

```typescript
import { StateGraph, Annotation,
  START, END }
  from '@langchain/langgraph';



const State = Annotation.Root({
  input: Annotation<string>(),
  output: Annotation<string>(),
});

const graph = new StateGraph(State)
  .addNode('process', async (state) => ({
    output: state.input.toUpperCase(),
  }))
  .addEdge(START, 'process')
  .addEdge('process', END)
  .compile();



const result = await graph.invoke({
  input: 'hello world',
});
console.log(result.output);
```

</td><td>

```typescript
import { StateGraph, Annotation,
  START, END }
  from '@langchain/langgraph';
import { AgentRuntime } from '@agentspan-ai/sdk';
// ^^^ add agentspan import

const State = Annotation.Root({
  input: Annotation<string>(),
  output: Annotation<string>(),
});

const graph = new StateGraph(State)
  .addNode('process', async (state) => ({
    output: state.input.toUpperCase(),
  }))
  .addEdge(START, 'process')
  .addEdge('process', END)
  .compile();

// Add agentspan metadata
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const runtime = new AgentRuntime();
const result = await runtime.run(
  graph, 'hello world',
);
result.printResult();
await runtime.shutdown();
```

</td></tr>
</table>

### What changes — summary

| What | Change |
|------|--------|
| **Imports** | Add `AgentRuntime` from `@agentspan-ai/sdk` |
| **Graph** | No changes to construction |
| **Metadata** | Add `(graph as any)._agentspan = { model, tools, framework: 'langgraph' }` |
| **Execution** | `graph.invoke({ messages })` → `runtime.run(graph, prompt)` |
| **Tools** | No changes — `DynamicStructuredTool` works as-is |

## Examples

| File | Description |
|------|-------------|
| `01-hello-world.ts` | Minimal createReactAgent, no tools |
| `02-react-with-tools.ts` | ReAct agent with 3 tools |
| `03-memory.ts` | Conversation memory |
| `04-simple-stategraph.ts` | Custom StateGraph pipeline |
| `05-tool-node.ts` | Explicit ToolNode usage |
| `06-conditional-routing.ts` | Conditional edges in StateGraph |
| `07-system-prompt.ts` | System prompt configuration |
| `08-structured-output.ts` | Typed output schemas |
| `09-math-agent.ts` | Math calculation agent |
| `10-research-agent.ts` | Multi-step research agent |

## Running

```bash
export AGENTSPAN_SERVER_URL=...
export OPENAI_API_KEY=...
cd sdk/typescript
npx tsx examples/langgraph/01-hello-world.ts
```
