# Design Doc — Issue #150: Retry Configuration on `@tool` Decorator

**Status:** Implemented  
**Author:** agentspan-ai  
**Issue:** [#150](https://github.com/agentspan-ai/agentspan/issues/150)  
**Date:** 2026-04-24

---

## Overview

Previously, every `@tool` function was registered with a hardcoded Conductor `TaskDef` using `retry_count=2`, `retry_delay_seconds=2`, and `retry_logic="LINEAR_BACKOFF"`. Users had no way to override these values from the Python SDK.

This feature adds three optional parameters to the `@tool` decorator — `retry_count`, `retry_delay_seconds`, and `retry_logic` — that flow through to the Conductor `TaskDef` when the tool is registered.

---

## Motivation

Different tools have very different reliability profiles:

- **Idempotent, flaky APIs** (e.g., third-party REST calls) benefit from aggressive retries with backoff.
- **Payment or mutation operations** should fail immediately (`retry_count=0`) to avoid double-execution.
- **Internal microservices** may warrant a fixed short delay rather than linear backoff.

The existing hardcoded defaults (`retry_count=2`, `retry_delay_seconds=2`) are a reasonable middle ground but cannot satisfy all use cases.

---

## API Surface

### `@tool` decorator — new parameters

```python
@tool(
    retry_count: Optional[int] = None,          # None → default (2)
    retry_delay_seconds: Optional[int] = None,  # None → default (2)
    retry_logic: Optional[str] = None,          # None → default ("LINEAR_BACKOFF")
)
```

All three parameters are **optional** and default to `None`, which preserves the existing behaviour (backward-compatible).

#### `retry_count`
Number of times Conductor will retry the task on failure. `0` means fail immediately with no retries.

#### `retry_delay_seconds`
Delay between retry attempts (in seconds). Interpretation depends on `retry_logic`.

#### `retry_logic`
Strategy used to space out retries. Valid values (from [Conductor `TaskDef`](https://github.com/conductor-oss/conductor/blob/main/common/src/main/java/com/netflix/conductor/common/metadata/tasks/TaskDef.java)):

| Value | Behaviour |
|-------|-----------|
| `"FIXED"` | Fixed delay of `retry_delay_seconds` between every retry |
| `"LINEAR_BACKOFF"` | Delay grows linearly: `retry_delay_seconds × attempt` (default) |
| `"EXPONENTIAL_BACKOFF"` | Delay doubles each attempt: `retry_delay_seconds × 2^attempt` |

### `ToolDef` dataclass — new fields

```python
@dataclass
class ToolDef:
    ...
    retry_count: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    retry_logic: Optional[str] = None
```

---

## Usage Examples

### Aggressive retries for a flaky external API

```python
@tool(retry_count=10, retry_delay_seconds=5, retry_logic="EXPONENTIAL_BACKOFF")
def call_flaky_api(query: str) -> str:
    """Call an unreliable third-party API."""
    return requests.get(f"https://flaky.example.com/search?q={query}").text
```

### No retries for a payment operation

```python
@tool(retry_count=0)
def process_payment(amount: float, card_token: str) -> dict:
    """Charge a card. Must not be retried to avoid double-charges."""
    return payment_gateway.charge(amount, card_token)
```

### Fixed delay for an internal service

```python
@tool(retry_count=3, retry_delay_seconds=2, retry_logic="FIXED")
def query_internal_service(user_id: str) -> dict:
    """Query an internal microservice with a fixed retry delay."""
    return internal_client.get_user(user_id)
```

### Default behaviour (unchanged)

```python
@tool
def get_weather(city: str) -> dict:
    """Uses the existing defaults: retry_count=2, retry_delay_seconds=2, LINEAR_BACKOFF."""
    ...
```

---

## Implementation Details

### Files Changed

| File | Change |
|------|--------|
| `sdk/python/src/agentspan/agents/tool.py` | Added `retry_count`, `retry_delay_seconds`, `retry_logic` to `ToolDef` dataclass and `@tool` decorator signature |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | `_default_task_def()` now accepts optional retry override kwargs |
| `sdk/python/src/agentspan/agents/runtime/tool_registry.py` | `register_tool_workers()` passes per-tool retry config to `_default_task_def()` |
| `sdk/python/src/agentspan/agents/config_serializer.py` | `_serialize_tool()` emits `retryCount`, `retryDelaySeconds`, `retryLogic` into the tool config dict |

### Data Flow

```
@tool(retry_count=10, retry_delay_seconds=5)
        │
        ▼
  ToolDef.retry_count = 10
  ToolDef.retry_delay_seconds = 5
        │
        ├──► tool_registry.register_tool_workers()
        │         │
        │         ▼
        │    _default_task_def(name, retry_count=10, retry_delay_seconds=5)
        │         │
        │         ▼
        │    TaskDef.retry_count = 10
        │    TaskDef.retry_delay_seconds = 5
        │    (registered with Conductor worker)
        │
        └──► config_serializer._serialize_tool()
                  │
                  ▼
             config["retryCount"] = 10
             config["retryDelaySeconds"] = 5
             (sent to server-side ToolCompiler)
```

### Backward Compatibility

All three new parameters default to `None`. When `None`, `_default_task_def()` falls back to the existing hardcoded defaults (`retry_count=2`, `retry_delay_seconds=2`, `retry_logic="LINEAR_BACKOFF"`). No existing code is affected.

### Scope Boundaries

- **`_passthrough_task_def`** (used for LangGraph/LangChain framework workers) is **not** changed — it has its own retry semantics.
- **System workers** (guardrails, stop_when, callbacks) call `_default_task_def()` without retry overrides and continue to receive the defaults.

---

## Sensible Defaults

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `retry_count` | 2 | Handles transient failures without excessive retries |
| `retry_delay_seconds` | 2 | Short enough to not stall the agent, long enough for transient issues to clear |
| `retry_logic` | `"LINEAR_BACKOFF"` | Avoids thundering-herd on shared services |

---

## Testing

Unit tests added in `sdk/python/tests/unit/test_tool_retry.py` (17 tests):

- Decorator stores `None` by default for all three fields
- Each field is stored correctly when set
- `retry_count=0` is stored as `0` (not treated as falsy/None)
- All three fields together
- `_default_task_def()` uses overrides when provided
- `_default_task_def()` falls back to defaults when `None`
- `config_serializer` emits `retryCount`, `retryDelaySeconds`, `retryLogic` in config dict
- Serializer omits retry keys when fields are `None`
