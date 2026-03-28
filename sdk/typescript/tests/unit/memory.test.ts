import { describe, it, expect } from 'vitest';
import {
  ConversationMemory,
  SemanticMemory,
  InMemoryStore,
} from '../../src/memory.js';
import type { MemoryStore } from '../../src/memory.js';

// ── ConversationMemory ──────────────────────────────────

describe('ConversationMemory', () => {
  describe('add and get messages', () => {
    it('adds user, assistant, and system messages', () => {
      const mem = new ConversationMemory();
      mem.addUserMessage('Hello');
      mem.addAssistantMessage('Hi there!');
      mem.addSystemMessage('You are a helpful assistant.');

      const messages = mem.toChatMessages();
      expect(messages).toHaveLength(3);
      expect(messages[0]).toEqual({ role: 'user', content: 'Hello' });
      expect(messages[1]).toEqual({ role: 'assistant', content: 'Hi there!' });
      expect(messages[2]).toEqual({ role: 'system', content: 'You are a helpful assistant.' });
    });

    it('adds tool calls and tool results', () => {
      const mem = new ConversationMemory();
      mem.addToolCall('search', { query: 'test' });
      mem.addToolResult('search', { results: ['a', 'b'] });

      const messages = mem.toChatMessages();
      expect(messages).toHaveLength(2);
      expect(messages[0]).toEqual({ role: 'tool', name: 'search', args: { query: 'test' } });
      expect(messages[1]).toEqual({ role: 'tool', name: 'search', result: { results: ['a', 'b'] } });
    });

    it('clear removes all messages', () => {
      const mem = new ConversationMemory();
      mem.addUserMessage('Hello');
      mem.addAssistantMessage('Hi');
      mem.clear();

      expect(mem.toChatMessages()).toHaveLength(0);
    });
  });

  describe('windowing with system message preservation', () => {
    it('trims oldest non-system messages when maxMessages exceeded', () => {
      const mem = new ConversationMemory({ maxMessages: 3 });
      mem.addSystemMessage('System prompt');
      mem.addUserMessage('msg1');
      mem.addUserMessage('msg2');
      mem.addUserMessage('msg3');
      mem.addUserMessage('msg4');

      const messages = mem.toChatMessages();
      // Should keep system + last 2 non-system = 3 total
      expect(messages).toHaveLength(3);
      expect(messages[0]).toEqual({ role: 'system', content: 'System prompt' });
      expect(messages[1]).toEqual({ role: 'user', content: 'msg3' });
      expect(messages[2]).toEqual({ role: 'user', content: 'msg4' });
    });

    it('always preserves all system messages even if they exceed maxMessages', () => {
      const mem = new ConversationMemory({ maxMessages: 2 });
      mem.addSystemMessage('System 1');
      mem.addSystemMessage('System 2');
      mem.addSystemMessage('System 3');
      mem.addUserMessage('Hello');

      const messages = mem.toChatMessages();
      // All 3 system messages preserved; no room for non-system
      // maxMessages=2 < 3 system messages, so all system messages are kept
      // and 0 non-system slots available (max(0, 2-3)=0)
      expect(messages).toHaveLength(3);
      expect(messages.every((m) => m.role === 'system')).toBe(true);
    });

    it('returns all messages when under maxMessages', () => {
      const mem = new ConversationMemory({ maxMessages: 10 });
      mem.addUserMessage('Hello');
      mem.addAssistantMessage('Hi');

      const messages = mem.toChatMessages();
      expect(messages).toHaveLength(2);
    });

    it('returns all messages when maxMessages is not set', () => {
      const mem = new ConversationMemory();
      for (let i = 0; i < 100; i++) {
        mem.addUserMessage(`msg${i}`);
      }
      expect(mem.toChatMessages()).toHaveLength(100);
    });

    it('preserves relative ordering of system and non-system messages', () => {
      const mem = new ConversationMemory({ maxMessages: 4 });
      mem.addSystemMessage('System prompt');
      mem.addUserMessage('msg1');
      mem.addAssistantMessage('reply1');
      mem.addUserMessage('msg2');
      mem.addAssistantMessage('reply2');
      mem.addUserMessage('msg3');

      const messages = mem.toChatMessages();
      expect(messages).toHaveLength(4);
      expect(messages[0]).toEqual({ role: 'system', content: 'System prompt' });
      // last 3 non-system in original order: msg2, reply2, msg3
      expect(messages[1]).toEqual({ role: 'user', content: 'msg2' });
      expect(messages[2]).toEqual({ role: 'assistant', content: 'reply2' });
      expect(messages[3]).toEqual({ role: 'user', content: 'msg3' });
    });
  });

  describe('toJSON', () => {
    it('serializes with messages and maxMessages', () => {
      const mem = new ConversationMemory({ maxMessages: 50 });
      mem.addUserMessage('Hello');
      mem.addAssistantMessage('Hi');

      const json = mem.toJSON();
      expect(json.maxMessages).toBe(50);
      expect(json.messages).toHaveLength(2);
    });

    it('serializes without maxMessages when not set', () => {
      const mem = new ConversationMemory();
      mem.addUserMessage('Hello');

      const json = mem.toJSON();
      expect(json.maxMessages).toBeUndefined();
      expect(json.messages).toHaveLength(1);
    });

    it('toJSON messages respect windowing', () => {
      const mem = new ConversationMemory({ maxMessages: 2 });
      mem.addUserMessage('msg1');
      mem.addUserMessage('msg2');
      mem.addUserMessage('msg3');

      const json = mem.toJSON();
      expect(json.messages).toHaveLength(2);
      expect(json.messages[0]).toEqual({ role: 'user', content: 'msg2' });
      expect(json.messages[1]).toEqual({ role: 'user', content: 'msg3' });
    });
  });
});

// ── SemanticMemory + InMemoryStore ──────────────────────

describe('SemanticMemory + InMemoryStore', () => {
  describe('add/search/delete/clear', () => {
    it('adds entries and retrieves them via search', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('TypeScript is a typed superset of JavaScript');
      memory.add('Python is great for data science');
      memory.add('JavaScript runs in the browser');

      const results = memory.search('JavaScript');
      expect(results.length).toBeGreaterThan(0);
      // JavaScript should match the first and third entries
      expect(results.some((r) => r.includes('TypeScript'))).toBe(true);
      expect(results.some((r) => r.includes('browser'))).toBe(true);
    });

    it('returns entries in order of relevance', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('The cat sat on the mat');
      memory.add('The dog played in the park');
      memory.add('The cat and dog are friends');

      const results = memory.search('cat dog friends');
      // 'The cat and dog are friends' should rank highest (3 keyword matches)
      expect(results[0]).toBe('The cat and dog are friends');
    });

    it('delete removes a specific entry', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      const id = memory.add('To be deleted');
      memory.add('To be kept');

      memory.delete(id);

      const all = memory.listAll();
      expect(all).toHaveLength(1);
      expect(all[0].content).toBe('To be kept');
    });

    it('clear removes all entries', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('Entry 1');
      memory.add('Entry 2');
      memory.clear();

      expect(memory.listAll()).toHaveLength(0);
    });

    it('listAll returns all entries', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('Entry 1');
      memory.add('Entry 2');
      memory.add('Entry 3');

      expect(memory.listAll()).toHaveLength(3);
    });

    it('add returns an id', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      const id = memory.add('Some content');
      expect(typeof id).toBe('string');
      expect(id.length).toBeGreaterThan(0);
    });

    it('add includes metadata on entries', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('Content with metadata', { source: 'test', priority: 1 });

      const all = memory.listAll();
      expect(all).toHaveLength(1);
      expect(all[0].metadata).toEqual({ source: 'test', priority: 1 });
    });

    it('search respects topK parameter', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('apple orange banana');
      memory.add('apple grape pear');
      memory.add('apple mango kiwi');

      const results = memory.search('apple', 2);
      expect(results).toHaveLength(2);
    });

    it('search defaults to topK=5', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      for (let i = 0; i < 10; i++) {
        memory.add(`entry with keyword ${i}`);
      }

      const results = memory.search('keyword');
      expect(results).toHaveLength(5);
    });
  });

  describe('keyword overlap ranking', () => {
    it('ranks entries by number of matching keywords', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('alpha');           // 1 match of 3
      memory.add('alpha beta');      // 2 matches of 3
      memory.add('alpha beta gamma'); // 3 matches of 3

      const results = memory.search('alpha beta gamma');
      expect(results[0]).toBe('alpha beta gamma');
      expect(results[1]).toBe('alpha beta');
      expect(results[2]).toBe('alpha');
    });

    it('returns no results when no keywords match', () => {
      const store = new InMemoryStore();
      const memory = new SemanticMemory({ store });

      memory.add('hello world');

      const results = memory.search('completely unrelated terms');
      expect(results).toHaveLength(0);
    });
  });
});

// ── InMemoryStore directly ──────────────────────────────

describe('InMemoryStore', () => {
  it('implements MemoryStore interface', () => {
    const store: MemoryStore = new InMemoryStore();
    const id = store.add({ content: 'test', timestamp: Date.now() });
    expect(typeof id).toBe('string');

    const results = store.search('test', 5);
    expect(results).toHaveLength(1);

    store.delete(id);
    expect(store.listAll()).toHaveLength(0);

    store.add({ content: 'a', timestamp: Date.now() });
    store.clear();
    expect(store.listAll()).toHaveLength(0);
  });
});
