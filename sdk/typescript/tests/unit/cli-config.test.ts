import { describe, it, expect, vi } from 'vitest';
import { execSync } from 'child_process';
import { makeCliTool } from '../../src/cli-config.js';
import { TerminalToolError } from '../../src/errors.js';

// Mock execSync
vi.mock('child_process', () => ({
  execSync: vi.fn(),
}));

const mockedExecSync = vi.mocked(execSync);

describe('makeCliTool', () => {
  it('returns success with exit_code on zero exit', async () => {
    mockedExecSync.mockReturnValue('hello world\n');

    const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
    const result = await tool.func!({ command: 'echo', args: ['hello'] });

    expect(result).toEqual({
      status: 'success',
      exit_code: 0,
      stdout: 'hello world\n',
      stderr: '',
    });
  });

  it('returns error result with output on non-zero exit code', async () => {
    const err = new Error('Command failed') as any;
    err.status = 1;
    err.stdout = 'some output';
    err.stderr = 'fatal: not a git repo';
    mockedExecSync.mockImplementation(() => { throw err; });

    const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
    const result = await tool.func!({ command: 'git', args: ['status'] });

    expect(result).toEqual({
      status: 'error',
      exit_code: 1,
      stdout: 'some output',
      stderr: 'fatal: not a git repo',
    });
  });

  it('throws TerminalToolError on timeout', async () => {
    const err = new Error('SIGTERM') as any;
    err.killed = true;
    err.signal = 'SIGTERM';
    mockedExecSync.mockImplementation(() => { throw err; });

    const tool = makeCliTool({ allowedCommands: [], timeout: 5 }, 'test_agent');

    await expect(tool.func!({ command: 'sleep', args: ['100'] }))
      .rejects.toThrow(TerminalToolError);
    await expect(tool.func!({ command: 'sleep', args: ['100'] }))
      .rejects.toThrow(/timed out/);
  });

  it('throws TerminalToolError on command not found', async () => {
    const err = new Error('ENOENT: no such file') as any;
    mockedExecSync.mockImplementation(() => { throw err; });

    const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');

    await expect(tool.func!({ command: 'nonexistent' }))
      .rejects.toThrow(TerminalToolError);
    await expect(tool.func!({ command: 'nonexistent' }))
      .rejects.toThrow(/not found/);
  });

  it('preserves stdout and stderr on non-zero exit', async () => {
    const err = new Error('Command failed') as any;
    err.status = 128;
    err.stdout = 'remote: Repository not found.\n';
    err.stderr = 'fatal: repository not found';
    mockedExecSync.mockImplementation(() => { throw err; });

    const tool = makeCliTool({ allowedCommands: [] }, 'test_agent');
    const result = await tool.func!({ command: 'git', args: ['push'] });

    expect(result).toEqual({
      status: 'error',
      exit_code: 128,
      stdout: 'remote: Repository not found.\n',
      stderr: 'fatal: repository not found',
    });
  });

  it('rejects disallowed commands', async () => {
    const tool = makeCliTool({ allowedCommands: ['git'] }, 'test_agent');

    await expect(tool.func!({ command: 'rm', args: ['-rf', '/'] }))
      .rejects.toThrow(/not allowed/);
  });

  it('blocks shell mode when disabled', async () => {
    const tool = makeCliTool({ allowedCommands: [], allowShell: false }, 'test_agent');

    await expect(tool.func!({ command: 'echo', shell: true }))
      .rejects.toThrow(/Shell mode is disabled/);
  });
});
