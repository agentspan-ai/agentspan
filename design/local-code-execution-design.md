# Local Code Execution — Cross-SDK Design

This document defines the local code execution architecture so it can be
implemented consistently across SDKs (Python, JavaScript/TypeScript, Java,
Go, etc.).

## Overview

Local code execution lets an agent's LLM run code on the user's machine
(or in a sandbox) via an `execute_code` tool.  The LLM sends code + language;
a **worker** on the SDK side executes it and returns stdout/stderr/exit code.

```
LLM  ──tool_call──►  Conductor  ──task──►  SDK Worker  ──subprocess──►  Result
     (execute_code)               (SIMPLE)              (temp file)
```

## Components

### 1. ExecutionResult

A data object returned by every executor.

| Field       | Type    | Description                                 |
|-------------|---------|---------------------------------------------|
| `output`    | string  | Captured stdout                             |
| `error`     | string  | Captured stderr                             |
| `exit_code` | int     | Process exit code (0 = success)             |
| `timed_out` | bool    | Whether execution hit the timeout           |

**Derived property:** `success` = `exit_code == 0 && !timed_out`

### 2. CodeExecutor (interface / abstract base)

Every SDK must implement this interface:

```
interface CodeExecutor {
    execute(code: string) -> ExecutionResult
}
```

**Constructor parameters:**

| Param         | Type   | Default    | Description                           |
|---------------|--------|------------|---------------------------------------|
| `language`    | string | `"python"` | Target interpreter language            |
| `timeout`     | int    | `30`       | Max execution time in seconds          |
| `working_dir` | string | `null`     | Working directory for the subprocess   |

### 3. Executor Implementations

#### 3a. LocalCodeExecutor

Runs code in a local subprocess via a temp file.

**Algorithm:**

1. If `code` is empty/null, return `ExecutionResult(output="No code provided. Nothing to execute.", exit_code=0)`.
2. Map `language` to interpreter command using the interpreter table (below).
3. Write `code` to a temp file with the appropriate extension.
4. Run `subprocess(interpreter, temp_file)` with:
   - `timeout` applied
   - `working_dir` as cwd (if set)
   - stdout and stderr captured separately
5. Return `ExecutionResult(stdout, stderr, exit_code)`.
6. On timeout: return `ExecutionResult(error="...", exit_code=-1, timed_out=true)`.
7. **Always** delete the temp file in a finally block.

**Interpreter table:**

| Language       | Command(s)      | File Extension |
|----------------|-----------------|----------------|
| `python`       | `python3`       | `.py`          |
| `python3`      | `python3`       | `.py`          |
| `bash`         | `bash`          | `.sh`          |
| `sh`           | `sh`            | `.sh`          |
| `node`         | `node`          | `.js`          |
| `javascript`   | `node`          | `.js`          |
| `ruby`         | `ruby`          | `.rb`          |

> **Portability note:** On Windows, `python3` may not exist; fall back to
> `python`.  For Node.js, use `node` on all platforms.

#### 3b. DockerCodeExecutor

Runs code inside a Docker container for isolation.

**Algorithm:**

1. Build Docker command:
   ```
   docker run --rm -i [--network=none] [--memory LIMIT]
     [-v host:container:ro ...] IMAGE INTERPRETER -c CODE
   ```
2. Pass code via stdin (not a temp file — avoids volume mounts for code).
3. Capture stdout/stderr from the container.
4. Add extra timeout buffer (e.g. +10s) for container startup.
5. Default: `--network=none` (disable network).

**Constructor extras:**

| Param             | Type              | Default             |
|-------------------|-------------------|---------------------|
| `image`           | string            | `"python:3.12-slim"`|
| `network_enabled` | bool              | `false`             |
| `memory_limit`    | string            | `null`              |
| `volumes`         | map<string,string>| `{}`                |

#### 3c. JupyterCodeExecutor

Uses a Jupyter kernel for stateful execution (state persists between calls).

> **Note:** This is the exception to the "isolated per call" rule.  Only
> include this executor in SDKs where Jupyter kernels are available
> (Python, potentially JS via Deno kernel).

#### 3d. ServerlessCodeExecutor

Delegates execution to an HTTP endpoint.

**Request:**
```json
POST /execute
{
  "code": "...",
  "language": "python",
  "timeout": 30
}
```

**Response:**
```json
{
  "output": "...",   // or "stdout"
  "error": "...",    // or "stderr"
  "exit_code": 0
}
```

This is the most portable executor — any SDK can implement an HTTP client.

### 4. CodeExecutionConfig

Declarative configuration attached to an Agent.

| Field               | Type           | Default      | Description                        |
|---------------------|----------------|--------------|------------------------------------|
| `enabled`           | bool           | `true`       | Whether code execution is active   |
| `allowed_languages` | list\<string\> | `["python"]` | Languages the LLM may use          |
| `allowed_commands`  | list\<string\> | `[]`         | Allowed shell commands (empty = no restriction) |
| `executor`          | CodeExecutor   | `null`       | Executor instance (null = auto-create LocalCodeExecutor) |
| `timeout`           | int            | `30`         | Seconds                            |
| `working_dir`       | string         | `null`       | Working directory                  |

### 5. CommandValidator

Best-effort regex-based validator that checks code for shell command
invocations against an allowed-command whitelist.

**Important:** This is NOT a security boundary.  For untrusted code, use
DockerCodeExecutor or ServerlessCodeExecutor.

**Validation rules per language:**

- **Python:** Scan for `subprocess.run/call(["CMD"...])`, `os.system("CMD")`,
  `os.popen("CMD")`, Jupyter `!CMD` syntax.
- **Bash/sh:** Extract command names from the script (skip builtins like
  `if`, `echo`, `export`, etc.), check each against the whitelist.
- **Other languages:** Skip validation (no patterns defined).

### 6. The `execute_code` Tool

A tool function registered as a Conductor SIMPLE worker.

**Tool schema:**

```json
{
  "name": "execute_code",
  "description": "Execute code in a sandboxed environment. Supported languages: {langs}. Timeout: {timeout}s.",
  "parameters": {
    "code": { "type": "string", "description": "The code to execute" },
    "language": { "type": "string", "default": "python", "description": "Programming language" }
  }
}
```

**Output format:**

The tool always returns structured JSON (never raises on code errors):

```json
{"status": "success", "stdout": "hello world\n", "stderr": ""}
{"status": "error",   "stdout": "",              "stderr": "NameError: name 'x' is not defined\nExit code: 1"}
```

When the tool returns a `dict`, the worker sets it directly as
`task_result.output_data` — the server passes `outputData` straight
through to the LLM as the tool result.

**Execution flow:**

```
1. Receive task with { code, language }
2. If code is empty/null → COMPLETE with {"status":"success","stdout":"No code provided...","stderr":""}
3. If language not in allowed_languages → raise ValueError (FAILED — tool misconfiguration)
4. If allowed_commands is set → CommandValidator.validate(code, language)
   If violation → raise ValueError (FAILED — tool misconfiguration)
5. Create executor for the language (LocalCodeExecutor per invocation,
   since each language needs its own interpreter)
6. result = executor.execute(code)
7. If result.success → COMPLETE with {"status":"success","stdout":"...","stderr":"..."}
8. If !result.success → COMPLETE with {"status":"error","stdout":"...","stderr":"..."}
```

**Key behavior:** Code execution errors always complete the task so the
LLM receives the error as a normal tool result and can self-correct
without wasting Conductor retries. Only tool misconfiguration errors
(invalid language, disallowed commands) fail the task.

## Agent Integration

### Shorthand API

Every SDK should support a simple boolean flag:

```python
# Python
Agent(name="coder", model="...", local_code_execution=True)

// JavaScript
new Agent({ name: "coder", model: "...", localCodeExecution: true })

// Java
Agent.builder().name("coder").model("...").localCodeExecution(true).build()
```

This auto-creates a `CodeExecutionConfig` with defaults and attaches the
`execute_code` tool to the agent.

### Extended API

For fine-grained control:

```python
# Python
Agent(
    name="coder",
    model="...",
    code_execution=CodeExecutionConfig(
        allowed_languages=["python", "bash"],
        allowed_commands=["pip", "ls"],
        executor=DockerCodeExecutor(image="python:3.12-slim"),
        timeout=60,
    ),
)
```

### Serialization

When the agent config is sent to the server for compilation, the code
execution config is serialized as:

```json
{
  "codeExecution": {
    "enabled": true,
    "allowedLanguages": ["python", "bash"],
    "allowedCommands": ["pip", "ls"],
    "timeout": 60
  }
}
```

The `executor` field is NOT serialized — it lives only on the SDK side.
The server uses this config to inject instructions into the LLM system
prompt (see below).

## Server-Side (Java)

The server does not execute code.  It:

1. Reads `codeExecution` from the agent config.
2. Injects instructions into the LLM system prompt via
   `AgentCompiler.buildCodeExecInstructions()`:
   ```
   You have code execution capabilities. Use the execute_code tool to write
   and run code. Supported languages: python, bash.
   Each execution runs in an isolated environment — no state, variables, or
   imports persist between calls.
   Always include all necessary imports at the top of every code block
   (e.g. import subprocess, import os, import json).
   Allowed shell commands: pip, ls. Do not use other commands.
   ```
3. The `execute_code` tool appears in the LLM's tool spec as a SIMPLE
   Conductor task.  The SDK-side worker picks it up and executes it.

## Worker Registration

Each SDK must:

1. Detect agents that have code execution enabled.
2. Register the `execute_code` function as a Conductor worker (SIMPLE task).
3. Start polling for tasks.

The worker must handle:
- Empty/null code (return success with message)
- Language validation
- Command validation (if configured)
- Execution via the configured executor
- Timeout handling
- Error formatting for LLM consumption

## Implementation Checklist for New SDKs

- [ ] `ExecutionResult` data class with `output`, `error`, `exit_code`, `timed_out`, `success`
- [ ] `CodeExecutor` interface with `execute(code) -> ExecutionResult`
- [ ] `LocalCodeExecutor` — subprocess + temp file, interpreter table, cleanup
- [ ] `DockerCodeExecutor` — Docker container execution (optional)
- [ ] `ServerlessCodeExecutor` — HTTP endpoint delegation (optional)
- [ ] `CodeExecutionConfig` data class
- [ ] `CommandValidator` with Python and Bash patterns
- [ ] `execute_code` tool function with the execution flow above
- [ ] Agent shorthand: `localCodeExecution: true` flag
- [ ] Config serialization to JSON for server compilation
- [ ] Conductor worker registration and polling
- [ ] Tests: empty code, language validation, command validation, execution success/failure/timeout
