import { describe, it, expect, vi } from 'vitest';
import {
  LocalCodeExecutor,
  CodeExecutor,
} from '../../src/code-execution.js';
import type { ExecutionResult, } from '../../src/code-execution.js';
import * as childProcess from 'child_process';

// Mock child_process.execSync
vi.mock('child_process', () => ({
  execSync: vi.fn(),
}));

const mockedExecSync = vi.mocked(childProcess.execSync);

// ── LocalCodeExecutor ───────────────────────────────────

describe('LocalCodeExecutor', () => {
  it('is an instance of CodeExecutor', () => {
    const executor = new LocalCodeExecutor();
    expect(executor).toBeInstanceOf(CodeExecutor);
  });

  it('defaults timeout to 30 seconds', () => {
    const executor = new LocalCodeExecutor();
    expect(executor.timeout).toBe(30_000);
  });

  it('accepts custom timeout', () => {
    const executor = new LocalCodeExecutor({ timeout: 60 });
    expect(executor.timeout).toBe(60_000);
  });

  describe('execute()', () => {
    it('executes JavaScript code successfully', () => {
      mockedExecSync.mockReturnValue('42');

      const executor = new LocalCodeExecutor();
      const result = executor.execute('console.log(42)', 'javascript');

      expect(result.output).toBe('42');
      expect(result.error).toBe('');
      expect(result.exitCode).toBe(0);
      expect(result.timedOut).toBe(false);
      expect(result.success).toBe(true);
    });

    it('executes Python code', () => {
      mockedExecSync.mockReturnValue('hello');

      const executor = new LocalCodeExecutor();
      const result = executor.execute('print("hello")', 'python');

      expect(result.output).toBe('hello');
      expect(result.success).toBe(true);
      // Verify the command used python3
      expect(mockedExecSync).toHaveBeenCalledWith(
        expect.stringContaining('python3'),
        expect.any(Object),
      );
    });

    it('executes bash code', () => {
      mockedExecSync.mockReturnValue('test output');

      const executor = new LocalCodeExecutor();
      const result = executor.execute('echo "test output"', 'bash');

      expect(result.output).toBe('test output');
      expect(result.success).toBe(true);
      expect(mockedExecSync).toHaveBeenCalledWith(
        expect.stringContaining('bash'),
        expect.any(Object),
      );
    });

    it('defaults to JavaScript when no language specified', () => {
      mockedExecSync.mockReturnValue('default');

      const executor = new LocalCodeExecutor();
      executor.execute('console.log("default")');

      expect(mockedExecSync).toHaveBeenCalledWith(
        expect.stringContaining('node'),
        expect.any(Object),
      );
    });

    it('handles execution errors', () => {
      const error = Object.assign(new Error('command failed'), {
        status: 1,
        killed: false,
        stdout: '',
        stderr: 'SyntaxError: Unexpected token',
        signal: null,
      });
      mockedExecSync.mockImplementation(() => {
        throw error;
      });

      const executor = new LocalCodeExecutor();
      const result = executor.execute('invalid syntax ///');

      expect(result.success).toBe(false);
      expect(result.exitCode).toBe(1);
      expect(result.error).toBe('SyntaxError: Unexpected token');
      expect(result.timedOut).toBe(false);
    });

    it('detects timeout via killed flag', () => {
      const error = Object.assign(new Error('timed out'), {
        status: null,
        killed: true,
        stdout: '',
        stderr: '',
        signal: 'SIGTERM',
      });
      mockedExecSync.mockImplementation(() => {
        throw error;
      });

      const executor = new LocalCodeExecutor();
      const result = executor.execute('while(true){}');

      expect(result.timedOut).toBe(true);
      expect(result.success).toBe(false);
    });
  });

  describe('asTool()', () => {
    it('returns a ToolDef', () => {
      const executor = new LocalCodeExecutor();
      const toolDef = executor.asTool();

      expect(toolDef.name).toBe('execute_code');
      expect(toolDef.description).toBe('Execute code and return the result');
      expect(toolDef.toolType).toBe('worker');
      expect(toolDef.inputSchema).toBeDefined();
      expect(typeof toolDef.func).toBe('function');
    });

    it('accepts custom tool name', () => {
      const executor = new LocalCodeExecutor();
      const toolDef = executor.asTool('my_executor');

      expect(toolDef.name).toBe('my_executor');
    });

    it('tool func calls execute', async () => {
      mockedExecSync.mockReturnValue('result');

      const executor = new LocalCodeExecutor();
      const toolDef = executor.asTool();
      const result = (await toolDef.func!({ code: 'console.log("result")', language: 'javascript' })) as ExecutionResult;

      expect(result.output).toBe('result');
      expect(result.success).toBe(true);
    });

    it('tool inputSchema has required code field', () => {
      const executor = new LocalCodeExecutor();
      const toolDef = executor.asTool();
      const schema = toolDef.inputSchema as Record<string, unknown>;

      expect(schema.type).toBe('object');
      const props = schema.properties as Record<string, unknown>;
      expect(props.code).toBeDefined();
      expect(props.language).toBeDefined();
      expect(schema.required).toContain('code');
    });
  });
});
