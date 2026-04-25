# Test Plan — PR #159 / Issue #150
## Credentials + Retry Config Merge in `serializeTool()`

---

## 1. Change Under Test

**File:** `sdk/typescript/src/serializer.ts`
**Method:** `AgentConfigSerializer.serializeTool()`

Two new merge blocks were added:

1. **Credentials block (lines 292–300):** Filters `toolDef.credentials` to plain strings only (`typeof c === "string"`), then spread-merges them into `config.config` as `credentials: string[]`. CredentialFile objects are excluded. Empty/undefined arrays produce no key.

2. **Retry block (lines 302–315):** Merges `retryCount`, `retryDelaySeconds`, `retryLogic` into `config.config` using `!== undefined` guards (handles `retryCount=0` correctly). Spread-merges on top of the credentials block output so both coexist.

---

## 2. Test Quality Criteria

All tests are **pure unit tests** (vitest):
- ✅ **No mocks** — no server, no network, no `vi.mock()` on the serializer
- ✅ **No LLM parsing** — no assertions on LLM text output
- ✅ **Algorithmic** — assert on plain object keys, values, and presence/absence
- ✅ **Counterfactual** — each test would fail if the fix were reverted

---

## 3. New Test File: `sdk/typescript/tests/unit/tool-retry-credentials.test.ts`

### 3.1 `describe("AgentConfigSerializer.serializeTool() — credentials in config")`

| Test | Assertion | Counterfactual |
|---|---|---|
| emits credentials into config.config for a worker tool | `config.credentials` deeply equals `["MY_KEY"]` | Fails if credentials block removed |
| emits multiple credentials into config.config | `config.credentials` deeply equals `["KEY_A", "KEY_B"]` | Fails if credentials block removed |
| omits credentials key from config when credentials array is empty | `config` does NOT have property `credentials` | Fails if empty array produces key |
| omits credentials key from config when credentials is undefined | `config` does NOT have property `credentials` | Fails if undefined produces key |
| excludes CredentialFile objects from config.credentials | `config` does NOT have property `credentials` | Fails if CredentialFile objects are included |
| includes only string credentials when mixed with CredentialFile | `config.credentials` deeply equals `["API_KEY"]` | Fails if CredentialFile not filtered |
| credentials-only tool has no retry keys in config | `credentials` present, `retryCount/retryDelaySeconds/retryLogic` absent | Fails if retry block pollutes output |

### 3.2 `describe("AgentConfigSerializer.serializeTool() — retry fields + credentials coexistence")`

| Test | Assertion | Counterfactual |
|---|---|---|
| credentials do not overwrite pre-existing config keys | `config.url`, `config.method`, `config.credentials` all present | Fails if spread-merge clobbers existing keys |
| retry fields do not overwrite credentials in config | `config.credentials` and `config.retryCount` both present | Fails if retry block overwrites credentials |
| all three retry fields plus credentials all coexist | All four keys present with correct values | Fails if any merge is destructive |
| retryCount=0 coexists with credentials | `config.retryCount === 0` (not skipped as falsy), `config.credentials` present | Fails if `if (retryCount)` used instead of `!== undefined` |
| coexists with credentials in config (retryCount + retryLogic + credentials) | `retryCount=2`, `retryLogic="LINEAR_BACKOFF"`, `credentials=["MY_API_KEY"]` all present | Fails if fix reverted (was the originally-failing CI test) |

### 3.3 `describe("AgentConfigSerializer.serializeTool() — httpTool credentials")`

| Test | Assertion | Counterfactual |
|---|---|---|
| httpTool with credentials emits credentials inside config | `config.credentials` equals `["API_KEY"]` AND `config.url` survives | Fails if credentials block removed or clobbers url |
| httpTool without credentials has no credentials key in config | `config` does NOT have property `credentials` | Fails if undefined credentials produce key |

---

## 4. Regression Tests

### 4.1 `sdk/typescript/tests/unit/tool-retry.test.ts` (17 tests)

The **originally-failing test** that blocked CI:
- `coexists with credentials in config` — asserts `config.retryCount===2`, `config.retryLogic==="LINEAR_BACKOFF"`, `config.credentials` deeply equals `["MY_API_KEY"]`

All 17 tests must pass without modification.

### 4.2 `sdk/typescript/tests/unit/serializer.test.ts` (103 tests)

Key regression assertions:
- `serializes httpTool` — `tc.credentials` equals `["API_KEY"]` (line 215)
- `serializes agent-level credentials` — agent-level credentials array passes through unchanged (line 660)

### 4.3 `sdk/typescript/tests/unit/credentials.test.ts` (25 tests)

Covers credential resolution, injection, context lifecycle — must all pass.

### 4.4 `sdk/typescript/tests/unit/agent.test.ts` (13 tests)

Agent construction, pipe, scatterGather — must all pass.

### 4.5 `sdk/typescript/tests/unit/config.test.ts` (16 tests)

Config normalization — must all pass.

### 4.6 `sdk/typescript/tests/unit/kitchen-sink-structural.test.ts` (19 tests)

Full pipeline serialization — must all pass.

---

## 5. Key Invariants Verified

1. **String credentials → `config.config.credentials`**: `typeof c === "string"` filter applied; only strings land in `config.credentials`.
2. **CredentialFile objects → NOT in `config.config.credentials`**: Objects with `envVar` are excluded from the merge.
3. **Spread-merge is non-destructive**: Pre-existing `config` keys (e.g., `url`, `method` from `httpTool`) survive the credentials merge.
4. **Retry merge is non-destructive**: Credentials survive the retry merge (credentials block runs first, retry block spreads on top).
5. **Empty/undefined credentials → no key emitted**: `credentials: []` and `credentials: undefined` must NOT produce a `credentials` key in `config.config`.
6. **`retryCount=0` is not falsy-skipped**: `0 !== undefined`, so it appears in `config.config`.
7. **All three retry values accepted**: `"FIXED"`, `"LINEAR_BACKOFF"`, `"EXPONENTIAL_BACKOFF"` all serialize correctly.

---

## 6. E2E Coverage

The Python e2e suite (`sdk/python/e2e/test_suite2_tool_calling.py`) exercises the full credential lifecycle end-to-end. No Python SDK files were modified in this PR. The Python e2e job was green in CI before and after the fix.

TypeScript e2e was previously skipped in CI because `typescript-unit-tests` was failing. With all 207 unit tests now passing, the `typescript-e2e` job will unblock automatically.
