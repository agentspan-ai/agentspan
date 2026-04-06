import { describe, it, expect } from 'vitest';
import { serializeLangChain } from '../../../src/frameworks/langchain-serializer.js';

describe('serializeLangChain', () => {
  describe('full extraction', () => {
    it('extracts model and tools from AgentExecutor', () => {
      function searchFn(query: string) { return `results for ${query}`; }

      const mockExecutor = {
        name: 'my_langchain_agent',
        invoke: () => {},
        lc_namespace: ['langchain', 'agents'],
        agent: {
          llm: {
            model_name: 'gpt-4o',
            constructor: { name: 'ChatOpenAI' },
          },
        },
        tools: [
          {
            name: 'search',
            description: 'Search the internet for information',
            func: searchFn,
            params_json_schema: {
              type: 'object',
              properties: { query: { type: 'string' } },
            },
          },
        ],
      };

      const [config, workers] = serializeLangChain(mockExecutor);

      expect(config.name).toBe('my_langchain_agent');
      expect(config.model).toBe('openai/gpt-4o');
      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(1);
      expect(tools[0]._worker_ref).toBe('search');
      expect(tools[0].description).toBe('Search the internet for information');

      expect(workers).toHaveLength(1);
      expect(workers[0].name).toBe('search');
      expect(workers[0].func).toBe(searchFn);
    });

    it('extracts model from agent.llm_chain.llm path', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: {
          llm_chain: {
            llm: {
              model_name: 'claude-3-sonnet',
              constructor: { name: 'ChatAnthropic' },
            },
          },
        },
        tools: [
          {
            name: 'calc',
            description: 'Calculator',
            func: () => {},
            params_json_schema: { type: 'object', properties: {} },
          },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('anthropic/claude-3-sonnet');
    });

    it('extracts model from agent.runnable.first path', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: {
          runnable: {
            first: {
              model: 'gpt-4',
              constructor: { name: 'ChatOpenAI' },
            },
          },
        },
        tools: [
          {
            name: 'tool1',
            description: 'Tool one',
            func: () => {},
            params_json_schema: { type: 'object', properties: {} },
          },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('openai/gpt-4');
    });

    it('extracts model from top-level llm property', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        llm: {
          model_name: 'gemini-pro',
          constructor: { name: 'ChatGoogleGenerativeAI' },
        },
        tools: [
          {
            name: 'tool1',
            description: 'Tool',
            func: () => {},
            params_json_schema: { type: 'object', properties: {} },
          },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('google/gemini-pro');
    });

    it('extracts multiple tools with schemas', () => {
      function tool1Fn() { return 'a'; }
      function tool2Fn() { return 'b'; }

      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          {
            name: 'search',
            description: 'Search the web',
            func: tool1Fn,
            params_json_schema: { type: 'object', properties: { q: { type: 'string' } } },
          },
          {
            name: 'calculate',
            description: 'Do math',
            func: tool2Fn,
            params_json_schema: { type: 'object', properties: { expr: { type: 'string' } } },
          },
        ],
      };

      const [config, workers] = serializeLangChain(mockExecutor);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(2);
      expect(workers).toHaveLength(2);
      expect(workers[0].func).toBe(tool1Fn);
      expect(workers[1].func).toBe(tool2Fn);
    });
  });

  describe('tool callable extraction', () => {
    it('extracts from func property', () => {
      const fn = () => 'result';
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          { name: 'tool', description: 'A tool', func: fn, params_json_schema: { type: 'object' } },
        ],
      };

      const [, workers] = serializeLangChain(mockExecutor);
      expect(workers[0].func).toBe(fn);
    });

    it('extracts from _run method', () => {
      const runFn = () => 'result';
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          { name: 'tool', description: 'A tool', _run: runFn, params_json_schema: { type: 'object' } },
        ],
      };

      const [, workers] = serializeLangChain(mockExecutor);
      expect(workers[0].func).toBe(runFn);
    });

    it('produces no worker when tool has no callable', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          { name: 'remote_tool', description: 'Remote only', params_json_schema: { type: 'object' } },
        ],
      };

      const [config, workers] = serializeLangChain(mockExecutor);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(1);
      expect(tools[0]._worker_ref).toBe('remote_tool');
      // No local worker since there's no callable
      expect(workers).toHaveLength(0);
    });
  });

  describe('fallback cases', () => {
    it('falls through to passthrough when no model found', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        tools: [{ name: 'tool', func: () => {} }],
      };

      const [config, workers] = serializeLangChain(mockExecutor);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
      expect(workers[0].func).toBeNull();
    });

    it('falls through to passthrough when no tools found', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [],
      };

      const [config, workers] = serializeLangChain(mockExecutor);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
    });

    it('falls through to passthrough when tools is not an array', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
      };

      const [config, workers] = serializeLangChain(mockExecutor);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
    });
  });

  describe('name derivation', () => {
    it('uses executor.name when available', () => {
      const mockExecutor = {
        name: 'custom_agent',
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          { name: 't', description: '', func: () => {}, params_json_schema: { type: 'object' } },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.name).toBe('custom_agent');
    });

    it('defaults to langchain_agent when no name', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o', constructor: { name: 'ChatOpenAI' } } },
        tools: [
          { name: 't', description: '', func: () => {}, params_json_schema: { type: 'object' } },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.name).toBe('langchain_agent');
    });
  });

  describe('provider inference', () => {
    it('infers openai from gpt- prefix', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gpt-4o-mini' } },
        tools: [
          { name: 't', description: '', func: () => {}, params_json_schema: { type: 'object' } },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('openai/gpt-4o-mini');
    });

    it('infers anthropic from claude in model name', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'claude-3-opus' } },
        tools: [
          { name: 't', description: '', func: () => {}, params_json_schema: { type: 'object' } },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('anthropic/claude-3-opus');
    });

    it('infers google from gemini in model name', () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ['langchain'],
        agent: { llm: { model_name: 'gemini-2.0-flash' } },
        tools: [
          { name: 't', description: '', func: () => {}, params_json_schema: { type: 'object' } },
        ],
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe('google/gemini-2.0-flash');
    });
  });
});
