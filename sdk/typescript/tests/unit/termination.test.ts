import { describe, it, expect } from 'vitest';
import {
  TerminationCondition,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,
  AndCondition,
  OrCondition,
} from '../../src/termination.js';

// ── Individual conditions ───────────────────────────────

describe('TextMention', () => {
  it('serializes to wire format', () => {
    const cond = new TextMention('DONE');
    expect(cond.toJSON()).toEqual({
      type: 'text_mention',
      text: 'DONE',
      caseSensitive: false,
    });
  });

  it('supports case-sensitive option', () => {
    const cond = new TextMention('FINISH', true);
    expect(cond.toJSON()).toEqual({
      type: 'text_mention',
      text: 'FINISH',
      caseSensitive: true,
    });
  });

  it('is an instance of TerminationCondition', () => {
    const cond = new TextMention('DONE');
    expect(cond).toBeInstanceOf(TerminationCondition);
  });
});

describe('StopMessage', () => {
  it('serializes to wire format', () => {
    const cond = new StopMessage('STOP');
    expect(cond.toJSON()).toEqual({
      type: 'stop_message',
      stopMessage: 'STOP',
    });
  });

  it('is an instance of TerminationCondition', () => {
    const cond = new StopMessage('STOP');
    expect(cond).toBeInstanceOf(TerminationCondition);
  });
});

describe('MaxMessage', () => {
  it('serializes to wire format', () => {
    const cond = new MaxMessage(10);
    expect(cond.toJSON()).toEqual({
      type: 'max_message',
      maxMessages: 10,
    });
  });

  it('is an instance of TerminationCondition', () => {
    const cond = new MaxMessage(10);
    expect(cond).toBeInstanceOf(TerminationCondition);
  });
});

describe('TokenUsageCondition', () => {
  it('serializes with all options', () => {
    const cond = new TokenUsageCondition({
      maxTotalTokens: 1000,
      maxPromptTokens: 500,
      maxCompletionTokens: 500,
    });
    expect(cond.toJSON()).toEqual({
      type: 'token_usage',
      maxTotalTokens: 1000,
      maxPromptTokens: 500,
      maxCompletionTokens: 500,
    });
  });

  it('serializes with partial options', () => {
    const cond = new TokenUsageCondition({ maxTotalTokens: 2000 });
    const json = cond.toJSON() as Record<string, unknown>;
    expect(json.type).toBe('token_usage');
    expect(json.maxTotalTokens).toBe(2000);
    expect(json.maxPromptTokens).toBeUndefined();
    expect(json.maxCompletionTokens).toBeUndefined();
  });

  it('is an instance of TerminationCondition', () => {
    const cond = new TokenUsageCondition({ maxTotalTokens: 1000 });
    expect(cond).toBeInstanceOf(TerminationCondition);
  });
});

// ── Composition (.and / .or) ────────────────────────────

describe('Composition', () => {
  describe('.and()', () => {
    it('composes two conditions with AND', () => {
      const a = new TextMention('DONE');
      const b = new MaxMessage(10);
      const composed = a.and(b);

      expect(composed).toBeInstanceOf(AndCondition);
      expect(composed).toBeInstanceOf(TerminationCondition);
      expect(composed.toJSON()).toEqual({
        type: 'and',
        conditions: [
          { type: 'text_mention', text: 'DONE', caseSensitive: false },
          { type: 'max_message', maxMessages: 10 },
        ],
      });
    });
  });

  describe('.or()', () => {
    it('composes two conditions with OR', () => {
      const a = new TextMention('DONE');
      const b = new StopMessage('STOP');
      const composed = a.or(b);

      expect(composed).toBeInstanceOf(OrCondition);
      expect(composed).toBeInstanceOf(TerminationCondition);
      expect(composed.toJSON()).toEqual({
        type: 'or',
        conditions: [
          { type: 'text_mention', text: 'DONE', caseSensitive: false },
          { type: 'stop_message', stopMessage: 'STOP' },
        ],
      });
    });
  });

  describe('deeply nested composition', () => {
    it('supports nested .and() and .or()', () => {
      const textDone = new TextMention('DONE');
      const maxMsg = new MaxMessage(20);
      const stopMsg = new StopMessage('STOP');
      const tokenLimit = new TokenUsageCondition({ maxTotalTokens: 5000 });

      // (textDone AND maxMsg) OR (stopMsg AND tokenLimit)
      const composed = textDone.and(maxMsg).or(stopMsg.and(tokenLimit));

      const json = composed.toJSON() as Record<string, unknown>;
      expect(json.type).toBe('or');

      const conditions = json.conditions as Array<Record<string, unknown>>;
      expect(conditions).toHaveLength(2);

      expect(conditions[0].type).toBe('and');
      expect(conditions[1].type).toBe('and');

      // First AND
      const firstAnd = conditions[0].conditions as Array<Record<string, unknown>>;
      expect(firstAnd[0].type).toBe('text_mention');
      expect(firstAnd[1].type).toBe('max_message');

      // Second AND
      const secondAnd = conditions[1].conditions as Array<Record<string, unknown>>;
      expect(secondAnd[0].type).toBe('stop_message');
      expect(secondAnd[1].type).toBe('token_usage');
    });

    it('allows chaining .or() on an AND result', () => {
      const a = new TextMention('A');
      const b = new TextMention('B');
      const c = new TextMention('C');

      const composed = a.and(b).or(c);
      const json = composed.toJSON() as Record<string, unknown>;
      expect(json.type).toBe('or');

      const conditions = json.conditions as Array<Record<string, unknown>>;
      expect(conditions).toHaveLength(2);
      expect(conditions[0].type).toBe('and');
      expect(conditions[1].type).toBe('text_mention');
    });
  });

  describe('flattening (Python parity)', () => {
    it('flattens A.or(B).or(C) to or([A, B, C])', () => {
      const a = new TextMention('A');
      const b = new TextMention('B');
      const c = new TextMention('C');

      const composed = a.or(b).or(c);
      const json = composed.toJSON() as Record<string, unknown>;
      expect(json.type).toBe('or');

      const conditions = json.conditions as Array<Record<string, unknown>>;
      expect(conditions).toHaveLength(3);
      expect(conditions[0]).toEqual({ type: 'text_mention', text: 'A', caseSensitive: false });
      expect(conditions[1]).toEqual({ type: 'text_mention', text: 'B', caseSensitive: false });
      expect(conditions[2]).toEqual({ type: 'text_mention', text: 'C', caseSensitive: false });
    });

    it('flattens A.and(B).and(C) to and([A, B, C])', () => {
      const a = new MaxMessage(10);
      const b = new MaxMessage(20);
      const c = new MaxMessage(30);

      const composed = a.and(b).and(c);
      const json = composed.toJSON() as Record<string, unknown>;
      expect(json.type).toBe('and');

      const conditions = json.conditions as Array<Record<string, unknown>>;
      expect(conditions).toHaveLength(3);
    });

    it('does not flatten mixed: A.or(B).and(C) keeps or inside and', () => {
      const a = new TextMention('A');
      const b = new TextMention('B');
      const c = new MaxMessage(10);

      const composed = a.or(b).and(c);
      const json = composed.toJSON() as Record<string, unknown>;
      expect(json.type).toBe('and');

      const conditions = json.conditions as Array<Record<string, unknown>>;
      expect(conditions).toHaveLength(2);
      expect(conditions[0]).toEqual({
        type: 'or',
        conditions: [
          { type: 'text_mention', text: 'A', caseSensitive: false },
          { type: 'text_mention', text: 'B', caseSensitive: false },
        ],
      });
      expect(conditions[1]).toEqual({ type: 'max_message', maxMessages: 10 });
    });
  });
});
