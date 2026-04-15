import { it } from 'vitest';
import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage, AIMessageChunk } from '@langchain/core/messages';
import { serializeLangGraph } from '../../src/frameworks/langgraph-serializer.js';

it('dump 28 rawConfig', () => {
  const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0, streaming: true });
  const SS = Annotation.Root({
    messages: Annotation<Array<any>>({
      reducer: (_p: any[], n: any[]) => n ?? _p,
      default: () => [],
    }),
  });
  async function generate(state: any) {
    const messages = state.messages || [];
    const response = await llm.invoke(messages);
    return { messages: [...messages, response] };
  }
  const builder = new StateGraph(SS);
  builder.addNode('generate', generate);
  builder.addEdge(START, 'generate');
  builder.addEdge('generate', END);
  const graph = builder.compile({ name: 'streaming_agent' });
  (graph as any)._agentspan = { model: 'openai/gpt-4o-mini', framework: 'langgraph' };

  const [rawConfig] = serializeLangGraph(graph);
  const g = rawConfig._graph as any;
  console.log('has _graph:', !!g);
  console.log('input_key:', g?.input_key);
  console.log('_input_is_messages:', g?._input_is_messages);
});
