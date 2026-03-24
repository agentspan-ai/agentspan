import { describe, it, expect, beforeEach } from 'vitest';
import {
  coerceValue,
  extractToolContext,
  captureStateMutations,
  appendStateUpdates,
  stripInternalKeys,
  recordFailure,
  recordSuccess,
  isCircuitBreakerOpen,
  resetCircuitBreaker,
  resetAllCircuitBreakers,
} from '../../src/worker.js';

// ── coerceValue ─────────────────────────────────────────

describe('coerceValue', () => {
  describe('null/empty handling', () => {
    it('returns null unchanged', () => {
      expect(coerceValue(null)).toBeNull();
    });

    it('returns undefined unchanged', () => {
      expect(coerceValue(undefined)).toBeUndefined();
    });

    it('returns value unchanged when targetType is undefined', () => {
      expect(coerceValue('hello')).toBe('hello');
    });

    it('returns value unchanged when targetType is empty string', () => {
      expect(coerceValue('hello', '')).toBe('hello');
    });
  });

  describe('type match short-circuit', () => {
    it('returns string unchanged for string target', () => {
      expect(coerceValue('hello', 'string')).toBe('hello');
    });

    it('returns number unchanged for number target', () => {
      expect(coerceValue(42, 'number')).toBe(42);
    });

    it('returns boolean unchanged for boolean target', () => {
      expect(coerceValue(true, 'boolean')).toBe(true);
    });

    it('returns object unchanged for object target', () => {
      const obj = { a: 1 };
      expect(coerceValue(obj, 'object')).toBe(obj);
    });
  });

  describe('string to object/array via JSON', () => {
    it('parses JSON string to object', () => {
      expect(coerceValue('{"a":1}', 'object')).toEqual({ a: 1 });
    });

    it('parses JSON string to array', () => {
      expect(coerceValue('[1,2,3]', 'array')).toEqual([1, 2, 3]);
    });

    it('returns original string on invalid JSON', () => {
      expect(coerceValue('not json', 'object')).toBe('not json');
    });

    it('returns original string on invalid JSON for array target', () => {
      expect(coerceValue('not json', 'array')).toBe('not json');
    });
  });

  describe('object/array to string via JSON', () => {
    it('stringifies object to string', () => {
      expect(coerceValue({ a: 1 }, 'string')).toBe('{"a":1}');
    });

    it('stringifies array to string', () => {
      expect(coerceValue([1, 2, 3], 'string')).toBe('[1,2,3]');
    });
  });

  describe('string to number', () => {
    it('converts numeric string to number', () => {
      expect(coerceValue('42', 'number')).toBe(42);
    });

    it('converts float string to number', () => {
      expect(coerceValue('3.14', 'number')).toBe(3.14);
    });

    it('returns original string for NaN', () => {
      expect(coerceValue('not-a-number', 'number')).toBe('not-a-number');
    });

    it('converts zero string', () => {
      expect(coerceValue('0', 'number')).toBe(0);
    });

    it('converts negative string', () => {
      expect(coerceValue('-5', 'number')).toBe(-5);
    });
  });

  describe('string to boolean', () => {
    it('converts "true" to true', () => {
      expect(coerceValue('true', 'boolean')).toBe(true);
    });

    it('converts "1" to true', () => {
      expect(coerceValue('1', 'boolean')).toBe(true);
    });

    it('converts "yes" to true', () => {
      expect(coerceValue('yes', 'boolean')).toBe(true);
    });

    it('converts "false" to false', () => {
      expect(coerceValue('false', 'boolean')).toBe(false);
    });

    it('converts "0" to false', () => {
      expect(coerceValue('0', 'boolean')).toBe(false);
    });

    it('converts "no" to false', () => {
      expect(coerceValue('no', 'boolean')).toBe(false);
    });

    it('is case-insensitive', () => {
      expect(coerceValue('TRUE', 'boolean')).toBe(true);
      expect(coerceValue('False', 'boolean')).toBe(false);
      expect(coerceValue('YES', 'boolean')).toBe(true);
      expect(coerceValue('NO', 'boolean')).toBe(false);
    });

    it('returns original for unrecognized boolean string', () => {
      expect(coerceValue('maybe', 'boolean')).toBe('maybe');
    });
  });

  describe('fallback', () => {
    it('returns original value for unknown conversion', () => {
      expect(coerceValue(42, 'boolean')).toBe(42);
    });

    it('returns original value for unrecognized target type', () => {
      expect(coerceValue('hello', 'custom_type')).toBe('hello');
    });

    it('is case-insensitive on target type', () => {
      expect(coerceValue('42', 'Number')).toBe(42);
      expect(coerceValue('true', 'Boolean')).toBe(true);
    });
  });
});

// ── Circuit breaker ─────────────────────────────────────

describe('Circuit breaker', () => {
  beforeEach(() => {
    resetAllCircuitBreakers();
  });

  it('is closed by default', () => {
    expect(isCircuitBreakerOpen('test_tool')).toBe(false);
  });

  it('opens after 10 consecutive failures', () => {
    for (let i = 0; i < 9; i++) {
      recordFailure('test_tool');
      expect(isCircuitBreakerOpen('test_tool')).toBe(false);
    }
    recordFailure('test_tool');
    expect(isCircuitBreakerOpen('test_tool')).toBe(true);
  });

  it('resets counter on success', () => {
    for (let i = 0; i < 5; i++) {
      recordFailure('test_tool');
    }
    recordSuccess('test_tool');
    expect(isCircuitBreakerOpen('test_tool')).toBe(false);

    // Need 10 more failures now
    for (let i = 0; i < 9; i++) {
      recordFailure('test_tool');
      expect(isCircuitBreakerOpen('test_tool')).toBe(false);
    }
    recordFailure('test_tool');
    expect(isCircuitBreakerOpen('test_tool')).toBe(true);
  });

  it('tracks tools independently', () => {
    for (let i = 0; i < 10; i++) {
      recordFailure('tool_a');
    }
    expect(isCircuitBreakerOpen('tool_a')).toBe(true);
    expect(isCircuitBreakerOpen('tool_b')).toBe(false);
  });

  it('resetCircuitBreaker resets specific tool', () => {
    for (let i = 0; i < 10; i++) {
      recordFailure('tool_a');
      recordFailure('tool_b');
    }
    resetCircuitBreaker('tool_a');
    expect(isCircuitBreakerOpen('tool_a')).toBe(false);
    expect(isCircuitBreakerOpen('tool_b')).toBe(true);
  });

  it('resetAllCircuitBreakers resets everything', () => {
    for (let i = 0; i < 10; i++) {
      recordFailure('tool_a');
      recordFailure('tool_b');
    }
    resetAllCircuitBreakers();
    expect(isCircuitBreakerOpen('tool_a')).toBe(false);
    expect(isCircuitBreakerOpen('tool_b')).toBe(false);
  });

  it('success on open breaker closes it', () => {
    for (let i = 0; i < 10; i++) {
      recordFailure('test_tool');
    }
    expect(isCircuitBreakerOpen('test_tool')).toBe(true);
    recordSuccess('test_tool');
    expect(isCircuitBreakerOpen('test_tool')).toBe(false);
  });
});

// ── ToolContext extraction ───────────────────────────────

describe('extractToolContext', () => {
  it('extracts context from __agentspan_ctx__', () => {
    const inputData = {
      someArg: 'value',
      __agentspan_ctx__: {
        sessionId: 'sess-1',
        workflowId: 'wf-1',
        agentName: 'my_agent',
        metadata: { key: 'val' },
        dependencies: { dep: 'service' },
        state: { counter: 0 },
      },
    };

    const ctx = extractToolContext(inputData);
    expect(ctx).not.toBeNull();
    expect(ctx!.sessionId).toBe('sess-1');
    expect(ctx!.workflowId).toBe('wf-1');
    expect(ctx!.agentName).toBe('my_agent');
    expect(ctx!.metadata).toEqual({ key: 'val' });
    expect(ctx!.dependencies).toEqual({ dep: 'service' });
    expect(ctx!.state).toEqual({ counter: 0 });
  });

  it('returns null when __agentspan_ctx__ is missing', () => {
    const ctx = extractToolContext({ someArg: 'value' });
    expect(ctx).toBeNull();
  });

  it('returns null when __agentspan_ctx__ is null', () => {
    const ctx = extractToolContext({ __agentspan_ctx__: null });
    expect(ctx).toBeNull();
  });

  it('creates a mutable copy of state', () => {
    const originalState = { counter: 0 };
    const inputData = {
      __agentspan_ctx__: {
        sessionId: '',
        workflowId: '',
        agentName: '',
        metadata: {},
        dependencies: {},
        state: originalState,
      },
    };

    const ctx = extractToolContext(inputData);
    expect(ctx).not.toBeNull();
    ctx!.state.counter = 42;
    expect(originalState.counter).toBe(0); // Original unchanged
  });

  it('defaults missing fields to empty values', () => {
    const ctx = extractToolContext({
      __agentspan_ctx__: {},
    });
    expect(ctx).not.toBeNull();
    expect(ctx!.sessionId).toBe('');
    expect(ctx!.workflowId).toBe('');
    expect(ctx!.agentName).toBe('');
    expect(ctx!.metadata).toEqual({});
    expect(ctx!.dependencies).toEqual({});
    expect(ctx!.state).toEqual({});
  });
});

// ── State mutation capture ──────────────────────────────

describe('captureStateMutations', () => {
  it('detects added keys', () => {
    const original = { a: 1 };
    const current = { a: 1, b: 2 };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ b: 2 });
  });

  it('detects modified keys', () => {
    const original = { a: 1, b: 2 };
    const current = { a: 1, b: 99 };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ b: 99 });
  });

  it('returns null when no changes', () => {
    const original = { a: 1, b: 2 };
    const current = { a: 1, b: 2 };
    const updates = captureStateMutations(original, current);
    expect(updates).toBeNull();
  });

  it('detects deep changes in nested objects', () => {
    const original = { nested: { x: 1 } };
    const current = { nested: { x: 2 } };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ nested: { x: 2 } });
  });

  it('handles empty original state', () => {
    const original = {};
    const current = { key: 'value' };
    const updates = captureStateMutations(original, current);
    expect(updates).toEqual({ key: 'value' });
  });
});

describe('appendStateUpdates', () => {
  it('merges into object result', () => {
    const result = { data: 'hello' };
    const updates = { counter: 1 };
    expect(appendStateUpdates(result, updates)).toEqual({
      data: 'hello',
      _state_updates: { counter: 1 },
    });
  });

  it('wraps non-object result', () => {
    const updates = { counter: 1 };
    expect(appendStateUpdates('hello', updates)).toEqual({
      result: 'hello',
      _state_updates: { counter: 1 },
    });
  });

  it('wraps null result', () => {
    const updates = { counter: 1 };
    expect(appendStateUpdates(null, updates)).toEqual({
      result: null,
      _state_updates: { counter: 1 },
    });
  });

  it('wraps number result', () => {
    const updates = { key: 'val' };
    expect(appendStateUpdates(42, updates)).toEqual({
      result: 42,
      _state_updates: { key: 'val' },
    });
  });

  it('wraps array result', () => {
    const updates = { key: 'val' };
    expect(appendStateUpdates([1, 2, 3], updates)).toEqual({
      result: [1, 2, 3],
      _state_updates: { key: 'val' },
    });
  });
});

// ── Key stripping ───────────────────────────────────────

describe('stripInternalKeys', () => {
  it('removes _agent_state', () => {
    const input = { _agent_state: 'internal', data: 'keep' };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: 'keep' });
    expect(result).not.toHaveProperty('_agent_state');
  });

  it('removes method', () => {
    const input = { method: 'POST', data: 'keep' };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: 'keep' });
    expect(result).not.toHaveProperty('method');
  });

  it('removes __agentspan_ctx__', () => {
    const input = { __agentspan_ctx__: { id: 1 }, data: 'keep' };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ data: 'keep' });
    expect(result).not.toHaveProperty('__agentspan_ctx__');
  });

  it('removes all internal keys at once', () => {
    const input = {
      _agent_state: 'state',
      method: 'POST',
      __agentspan_ctx__: {},
      arg1: 'value1',
      arg2: 42,
    };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ arg1: 'value1', arg2: 42 });
  });

  it('returns copy without modifying original', () => {
    const input = { _agent_state: 'state', data: 'keep' };
    const result = stripInternalKeys(input);
    expect(input._agent_state).toBe('state');
    expect(result).not.toHaveProperty('_agent_state');
  });

  it('handles input with no internal keys', () => {
    const input = { arg1: 'a', arg2: 'b' };
    const result = stripInternalKeys(input);
    expect(result).toEqual({ arg1: 'a', arg2: 'b' });
  });

  it('handles empty input', () => {
    const result = stripInternalKeys({});
    expect(result).toEqual({});
  });
});
