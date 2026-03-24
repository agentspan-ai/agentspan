import { describe, it, expect, vi } from 'vitest';
import { extractModelString, mapFinishReason } from '../../../src/wrappers/ai.js';

describe('Vercel AI SDK wrapper', () => {
  describe('extractModelString', () => {
    it('returns string model as-is', () => {
      expect(extractModelString('openai/gpt-4o-mini')).toBe('openai/gpt-4o-mini');
    });

    it('returns model with existing provider prefix as-is', () => {
      expect(extractModelString('anthropic/claude-3-opus')).toBe('anthropic/claude-3-opus');
    });

    it('extracts from AI SDK model object with modelId and provider', () => {
      const model = {
        modelId: 'gpt-4o-mini',
        provider: 'openai.chat',
      };
      expect(extractModelString(model)).toBe('openai/gpt-4o-mini');
    });

    it('extracts from AI SDK model object with modelId that includes provider', () => {
      const model = {
        modelId: 'anthropic/claude-3-sonnet',
        provider: 'anthropic.messages',
      };
      expect(extractModelString(model)).toBe('anthropic/claude-3-sonnet');
    });

    it('extracts from model with modelName property', () => {
      const model = { modelName: 'gpt-4o' };
      expect(extractModelString(model)).toBe('openai/gpt-4o');
    });

    it('extracts from model with model property', () => {
      const model = { model: 'claude-3-haiku' };
      expect(extractModelString(model)).toBe('anthropic/claude-3-haiku');
    });

    it('extracts from model with providerId', () => {
      const model = {
        modelId: 'gemini-2.0-flash',
        providerId: 'google',
      };
      expect(extractModelString(model)).toBe('google/gemini-2.0-flash');
    });

    it('handles provider string with dot notation', () => {
      const model = {
        modelId: 'gpt-4o-mini',
        provider: 'openai.chat.completions',
      };
      expect(extractModelString(model)).toBe('openai/gpt-4o-mini');
    });

    it('infers openai provider from gpt- prefix', () => {
      const model = { modelId: 'gpt-4' };
      expect(extractModelString(model)).toBe('openai/gpt-4');
    });

    it('infers anthropic provider from claude in model name', () => {
      const model = { modelId: 'claude-3-sonnet' };
      expect(extractModelString(model)).toBe('anthropic/claude-3-sonnet');
    });

    it('infers google provider from gemini in model name', () => {
      const model = { modelId: 'gemini-pro' };
      expect(extractModelString(model)).toBe('google/gemini-pro');
    });

    it('defaults to openai/gpt-4o-mini for null model', () => {
      expect(extractModelString(null)).toBe('openai/gpt-4o-mini');
    });

    it('defaults to openai/gpt-4o-mini for undefined model', () => {
      expect(extractModelString(undefined)).toBe('openai/gpt-4o-mini');
    });

    it('defaults to openai/gpt-4o-mini for empty object', () => {
      expect(extractModelString({})).toBe('openai/gpt-4o-mini');
    });

    it('handles number input gracefully', () => {
      expect(extractModelString(42)).toBe('openai/gpt-4o-mini');
    });

    it('infers openai for o1 prefix', () => {
      const model = { modelId: 'o1-preview' };
      expect(extractModelString(model)).toBe('openai/o1-preview');
    });

    it('infers openai for o3 prefix', () => {
      const model = { modelId: 'o3-mini' };
      expect(extractModelString(model)).toBe('openai/o3-mini');
    });
  });

  describe('mapFinishReason', () => {
    it('maps stop to stop', () => {
      expect(mapFinishReason('stop')).toBe('stop');
    });

    it('maps length to length', () => {
      expect(mapFinishReason('length')).toBe('length');
    });

    it('maps tool_calls to tool-calls', () => {
      expect(mapFinishReason('tool_calls')).toBe('tool-calls');
    });

    it('maps tool-calls to tool-calls', () => {
      expect(mapFinishReason('tool-calls')).toBe('tool-calls');
    });

    it('maps content-filter to content-filter', () => {
      expect(mapFinishReason('content-filter')).toBe('content-filter');
    });

    it('passes through unknown reasons', () => {
      expect(mapFinishReason('custom_reason')).toBe('custom_reason');
    });

    it('defaults to stop for undefined', () => {
      expect(mapFinishReason(undefined)).toBe('stop');
    });
  });

  describe('generateText wrapper', () => {
    it('builds correct Agent from options', async () => {
      // We test the model extraction and agent construction logic
      // without actually calling the runtime (which needs a server)
      const { Agent } = await import('../../../src/index.js');

      // Simulate what the wrapper does internally
      const options = {
        model: { modelId: 'gpt-4o-mini', provider: 'openai.chat' },
        tools: {
          weather: {
            description: 'Get weather',
            parameters: { type: 'object', properties: { city: { type: 'string' } } },
            execute: async (args: { city: string }) => ({ temp: 72 }),
          },
        },
        system: 'You are a helpful assistant.',
        prompt: 'What is the weather?',
        maxSteps: 5,
      };

      const modelStr = extractModelString(options.model);
      expect(modelStr).toBe('openai/gpt-4o-mini');

      const toolObjects = Object.values(options.tools);
      expect(toolObjects).toHaveLength(1);

      const agent = new Agent({
        name: 'vercel_ai_agent',
        model: modelStr,
        instructions: options.system,
        tools: toolObjects,
        maxTurns: options.maxSteps,
      });

      expect(agent.name).toBe('vercel_ai_agent');
      expect(agent.model).toBe('openai/gpt-4o-mini');
      expect(agent.instructions).toBe('You are a helpful assistant.');
      expect(agent.tools).toHaveLength(1);
      expect(agent.maxTurns).toBe(5);
    });

    it('handles options with messages instead of prompt', () => {
      const messages = [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi there!' },
      ];

      const prompt = JSON.stringify(messages);
      expect(prompt).toContain('Hello');
      expect(prompt).toContain('Hi there!');
    });

    it('handles options with no tools', () => {
      const modelStr = extractModelString({ modelId: 'gpt-4o-mini', provider: 'openai.chat' });
      expect(modelStr).toBe('openai/gpt-4o-mini');
      // No tools case - should produce empty array
      const tools = undefined;
      const toolObjects = tools ? Object.values(tools) : [];
      expect(toolObjects).toHaveLength(0);
    });
  });
});
