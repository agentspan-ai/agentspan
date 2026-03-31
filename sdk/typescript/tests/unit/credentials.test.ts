import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  extractExecutionToken,
  resolveCredentials,
  getCredential,
  setCredentialContext,
  clearCredentialContext,
  injectCredentials,
} from '../../src/credentials.js';
import {
  CredentialNotFoundError,
  CredentialAuthError,
  CredentialRateLimitError,
  CredentialServiceError,
} from '../../src/errors.js';

// ── extractExecutionToken ────────────────────────────────

describe('extractExecutionToken', () => {
  it('extracts token from primary path (camelCase)', () => {
    const input = {
      arg1: 'value',
      __agentspan_ctx__: {
        executionToken: 'tok-primary',
        executionId: 'wf-123',
      },
    };
    expect(extractExecutionToken(input)).toBe('tok-primary');
  });

  it('extracts token from primary path (snake_case)', () => {
    const input = {
      __agentspan_ctx__: {
        execution_token: 'tok-snake',
      },
    };
    expect(extractExecutionToken(input)).toBe('tok-snake');
  });

  it('falls back to workflowInput path (camelCase)', () => {
    const input = {
      arg1: 'value',
      workflowInput: {
        __agentspan_ctx__: {
          executionToken: 'tok-fallback',
        },
      },
    };
    expect(extractExecutionToken(input)).toBe('tok-fallback');
  });

  it('falls back to workflowInput path (snake_case)', () => {
    const input = {
      workflowInput: {
        __agentspan_ctx__: {
          execution_token: 'tok-fallback-snake',
        },
      },
    };
    expect(extractExecutionToken(input)).toBe('tok-fallback-snake');
  });

  it('prefers primary path over fallback', () => {
    const input = {
      __agentspan_ctx__: {
        executionToken: 'tok-primary',
      },
      workflowInput: {
        __agentspan_ctx__: {
          executionToken: 'tok-fallback',
        },
      },
    };
    expect(extractExecutionToken(input)).toBe('tok-primary');
  });

  it('returns null when no context present', () => {
    expect(extractExecutionToken({})).toBeNull();
    expect(extractExecutionToken({ arg1: 'value' })).toBeNull();
  });

  it('returns null when context has no token', () => {
    const input = {
      __agentspan_ctx__: {
        executionId: 'wf-123',
      },
    };
    expect(extractExecutionToken(input)).toBeNull();
  });

  it('returns null for invalid context types', () => {
    expect(extractExecutionToken({ __agentspan_ctx__: 'not-object' })).toBeNull();
    expect(extractExecutionToken({ __agentspan_ctx__: null })).toBeNull();
    expect(extractExecutionToken({ __agentspan_ctx__: 42 })).toBeNull();
  });
});

// ── resolveCredentials ───────────────────────────────────

describe('resolveCredentials', () => {
  const serverUrl = 'https://api.agentspan.test';
  const headers = { Authorization: 'Bearer test-key' };
  const token = 'exec-tok-123';

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves credentials on success', async () => {
    const mockResponse = { GITHUB_TOKEN: 'ghp_secret', AWS_KEY: 'aws-secret' };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }),
    );

    const result = await resolveCredentials(serverUrl, headers, token, [
      'GITHUB_TOKEN',
      'AWS_KEY',
    ]);

    expect(result).toEqual(mockResponse);
    expect(fetch).toHaveBeenCalledWith(`${serverUrl}/credentials/resolve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({ token, names: ['GITHUB_TOKEN', 'AWS_KEY'] }),
    });
  });

  it('sends token field (not executionToken) matching server contract', async () => {
    const mockResponse = { MY_CRED: 'val' };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }),
    );

    await resolveCredentials(serverUrl, headers, token, ['MY_CRED']);

    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(call[1].body);
    // Server expects "token", not "executionToken"
    expect(body).toHaveProperty('token');
    expect(body).not.toHaveProperty('executionToken');
    expect(body.token).toBe(token);
  });

  it('throws CredentialNotFoundError on 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => JSON.stringify({ credentialName: 'MISSING_KEY' }),
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MISSING_KEY']),
    ).rejects.toThrow(CredentialNotFoundError);
  });

  it('throws CredentialAuthError on 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => 'Token expired',
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialAuthError);
  });

  it('throws CredentialRateLimitError on 429', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        text: async () => 'Rate limit exceeded',
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialRateLimitError);
  });

  it('throws CredentialServiceError on 500', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => 'Internal server error',
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialServiceError);
  });

  it('throws CredentialServiceError on 503', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => 'Service unavailable',
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialServiceError);
  });

  it('throws CredentialServiceError on network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('ECONNREFUSED')),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialServiceError);
  });

  it('throws CredentialServiceError on unexpected status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        text: async () => 'Forbidden',
      }),
    );

    await expect(
      resolveCredentials(serverUrl, headers, token, ['MY_CRED']),
    ).rejects.toThrow(CredentialServiceError);
  });
});

// ── getCredential ────────────────────────────────────────

describe('getCredential', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCredentialContext();
  });

  afterEach(() => {
    clearCredentialContext();
  });

  it('throws when no context is set', async () => {
    await expect(getCredential('MY_CRED')).rejects.toThrow(CredentialAuthError);
    await expect(getCredential('MY_CRED')).rejects.toThrow(
      'No credential context available',
    );
  });

  it('resolves a single credential using context', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ MY_CRED: 'secret-value' }),
      }),
    );

    setCredentialContext('https://api.test', { Authorization: 'Bearer tok' }, 'exec-tok');
    const value = await getCredential('MY_CRED');
    expect(value).toBe('secret-value');
  });

  it('throws CredentialNotFoundError when credential missing in response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({}), // Credential not in response
      }),
    );

    setCredentialContext('https://api.test', {}, 'exec-tok');
    await expect(getCredential('MISSING')).rejects.toThrow(CredentialNotFoundError);
  });
});

// ── injectCredentials ────────────────────────────────────

describe('injectCredentials', () => {
  const serverUrl = 'https://api.test';
  const headers = { Authorization: 'Bearer key' };
  const token = 'exec-tok';

  afterEach(() => {
    clearCredentialContext();
    // Clean up any env vars
    delete process.env.TEST_CRED_A;
    delete process.env.TEST_CRED_B;
  });

  it('sets credentials as env vars in isolated mode (default)', () => {
    const creds = { TEST_CRED_A: 'val-a', TEST_CRED_B: 'val-b' };
    const cleanup = injectCredentials(serverUrl, headers, token, creds);

    expect(process.env.TEST_CRED_A).toBe('val-a');
    expect(process.env.TEST_CRED_B).toBe('val-b');

    cleanup();

    expect(process.env.TEST_CRED_A).toBeUndefined();
    expect(process.env.TEST_CRED_B).toBeUndefined();
  });

  it('restores previous env var values on cleanup', () => {
    process.env.TEST_CRED_A = 'original';
    const creds = { TEST_CRED_A: 'overridden' };
    const cleanup = injectCredentials(serverUrl, headers, token, creds, true);

    expect(process.env.TEST_CRED_A).toBe('overridden');

    cleanup();

    expect(process.env.TEST_CRED_A).toBe('original');
    delete process.env.TEST_CRED_A;
  });

  it('sets credential context in non-isolated mode', () => {
    const creds = { MY_KEY: 'secret' };
    const cleanup = injectCredentials(serverUrl, headers, token, creds, false);

    // In non-isolated mode, env vars should NOT be set
    expect(process.env.MY_KEY).toBeUndefined();

    // Credential context should be available (we test indirectly via getCredential)
    // Clean up
    cleanup();
  });

  it('clears credential context on cleanup in non-isolated mode', async () => {
    const creds = { MY_KEY: 'secret' };
    const cleanup = injectCredentials(serverUrl, headers, token, creds, false);

    // Context should be set — getCredential should not throw "no context"
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ MY_KEY: 'resolved' }),
      }),
    );
    const val = await getCredential('MY_KEY');
    expect(val).toBe('resolved');

    cleanup();

    // After cleanup, context cleared — getCredential should throw
    await expect(getCredential('MY_KEY')).rejects.toThrow(
      'No credential context available',
    );

    vi.restoreAllMocks();
  });

  it('isolated mode explicitly set to true works same as default', () => {
    const creds = { TEST_CRED_A: 'val-a' };
    const cleanup = injectCredentials(serverUrl, headers, token, creds, true);

    expect(process.env.TEST_CRED_A).toBe('val-a');

    cleanup();

    expect(process.env.TEST_CRED_A).toBeUndefined();
  });
});
