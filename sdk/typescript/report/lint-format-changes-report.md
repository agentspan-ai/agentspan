# Lint & Format Changes Report

**Date:** 2026-04-07
**Branch:** `bugfix/use-lint`
**Scope:** TypeScript SDK (`sdk/typescript/`)

---

## Summary

Added ESLint, Prettier, Husky, and lint-staged to the TypeScript SDK. Applied all auto-fixes and resolved all blocking lint errors. Formatting applied to all source and test files.

| Metric | Value |
|--------|-------|
| Files changed | 85 |
| Lines added | 8,429 |
| Lines removed | 6,554 |
| Net change | +1,875 |
| ESLint errors remaining | 0 |
| ESLint warnings remaining | 297 |
| Prettier violations remaining | 0 |
| Tests passing | 35/36 (1 pre-existing server-dependent failure) |
| Type-check | Clean |

---

## New Tooling Installed

### Root (`/`)

| Package | Version | Purpose |
|---------|---------|---------|
| husky | ^9.1.7 | Git hooks manager |
| lint-staged | ^16.4.0 | Run linters on staged files only |

### SDK (`sdk/typescript/`)

| Package | Version | Purpose |
|---------|---------|---------|
| eslint | ^10.2.0 | JavaScript/TypeScript linter |
| @eslint/js | ^10.0.1 | ESLint core rules |
| typescript-eslint | ^8.58.0 | TypeScript-specific lint rules |
| prettier | ^3.8.1 | Code formatter |
| eslint-config-prettier | ^10.1.8 | Disables ESLint rules that conflict with Prettier |
| eslint-plugin-prettier | ^5.5.5 | Runs Prettier as an ESLint rule |

---

## New Config Files

| File | Description |
|------|-------------|
| `package.json` (root) | Minimal root package.json for husky `prepare` script |
| `package-lock.json` (root) | Root lockfile for husky/lint-staged deps |
| `.husky/pre-commit` | Runs `lint-staged` in `sdk/typescript/` on commit |
| `sdk/typescript/eslint.config.js` | ESLint flat config with typescript-eslint + Prettier compat |
| `sdk/typescript/.prettierrc` | Prettier config: semi, double quotes, trailing commas, 100 char width |
| `sdk/typescript/.prettierignore` | Excludes dist, node_modules, examples, validation |

---

## Script Changes (`sdk/typescript/package.json`)

| Script | Before | After |
|--------|--------|-------|
| `lint` | `tsc --noEmit` | `eslint src/ tests/` |
| `lint:fix` | _(new)_ | `eslint src/ tests/ --fix` |
| `format` | _(new)_ | `prettier --write "src/**/*.ts" "tests/**/*.ts"` |
| `format:check` | _(new)_ | `prettier --check "src/**/*.ts" "tests/**/*.ts"` |
| `typecheck` | _(new)_ | `tsc --noEmit` (moved from old `lint`) |

---

## Source File Changes (`src/`) — 38 files

| File | + | - | Tags | Description | Risk |
|------|---|---|------|-------------|------|
| `agent.ts` | +31 | -57 | FORMAT, DEAD CODE | Removed unused `PromptTemplateInterface` import | None |
| `callback.ts` | +7 | -7 | FORMAT | Prettier only | None |
| `claude-code.ts` | +9 | -9 | FORMAT | Prettier only | None |
| `cli-config.ts` | +39 | -43 | FORMAT, DEAD CODE | Removed unused `execSync` import | None |
| `code-execution.ts` | +116 | -76 | FORMAT, SEMANTIC | Removed `const executor = this` alias, used `this` directly | None |
| `config.ts` | +21 | -37 | FORMAT | Prettier only | None |
| `credentials.ts` | +19 | -34 | FORMAT | Prettier only | None |
| `discovery.ts` | +4 | -4 | FORMAT | Prettier only | None |
| `errors.ts` | +15 | -15 | FORMAT | Prettier only | None |
| `ext.ts` | +3 | -3 | FORMAT | Prettier only | None |
| `frameworks/detect.ts` | +29 | -31 | FORMAT | Prettier only | None |
| `frameworks/langchain-serializer.ts` | +57 | -46 | FORMAT | Prettier only | None |
| `frameworks/langgraph-serializer.ts` | +309 | -260 | FORMAT, SEMANTIC, DEAD CODE | `hasOwnProperty` → `Object.hasOwn` (2x), removed unused catch binding | None |
| `frameworks/serializer.ts` | +47 | -59 | FORMAT, DEAD CODE, SUPPRESSED | Removed unused import, eslint-disable on `require()` | None |
| `guardrail.ts` | +26 | -37 | FORMAT | Prettier only | None |
| `handoff.ts` | +9 | -9 | FORMAT | Prettier only | None |
| `index.ts` | +46 | -77 | FORMAT | Prettier only | None |
| `memory.ts` | +13 | -15 | FORMAT | Prettier only | None |
| `result.ts` | +36 | -36 | FORMAT | Prettier only | None |
| `runtime.ts` | +214 | -186 | FORMAT, DEAD CODE | Removed unused `OnToolResult`, `OnTextMention`, `OnCondition` imports | None |
| `serializer.ts` | +36 | -51 | FORMAT | Prettier only | None |
| `skill.ts` | +110 | -121 | FORMAT | Prettier only | None |
| `stream.ts` | +46 | -54 | FORMAT | Prettier only | None |
| `termination.ts` | +17 | -16 | FORMAT | Prettier only | None |
| `testing/assertions.ts` | +11 | -30 | FORMAT | Prettier only | None |
| `testing/eval.ts` | +16 | -36 | FORMAT | Prettier only | None |
| `testing/expect.ts` | +9 | -23 | FORMAT | Prettier only | None |
| `testing/index.ts` | +10 | -15 | FORMAT | Prettier only | None |
| `testing/mock.ts` | +12 | -13 | FORMAT, DEAD CODE | Removed unused `ConfigurationError` import | None |
| `testing/recording.ts` | +8 | -8 | FORMAT | Prettier only | None |
| `testing/strategy.ts` | +3 | -5 | FORMAT | Prettier only | None |
| `tool.ts` | +182 | -195 | FORMAT, DEAD CODE | Removed unused `zodSchemaToJson` function & unused type params | Low |
| `tracing.ts` | +1 | -1 | FORMAT | Prettier only | None |
| `types.ts` | +54 | -59 | FORMAT | Prettier only | None |
| `worker.ts` | +58 | -54 | FORMAT, DEAD CODE | Prefixed unused params with `_` | None |
| `wrappers/ai.ts` | +66 | -44 | FORMAT, SEMANTIC | Dead assignment removed: `let provider = "openai"` → `let provider: string` | None |
| `wrappers/langchain.ts` | +46 | -33 | FORMAT, SEMANTIC | Same dead assignment fix | None |
| `wrappers/langgraph.ts` | +39 | -29 | FORMAT, SEMANTIC | Same dead assignment fix | None |

---

## Test File Changes (`tests/`) — 38 files

| File | + | - | Tags | Description | Risk |
|------|---|---|------|-------------|------|
| `_subgraph-debug.ts` | +57 | -40 | FORMAT | Prettier only | None |
| `_worker-harness.ts` | +75 | -42 | FORMAT, SEMANTIC | Added comments to 7 empty catch blocks | None |
| `cli-bin/deploy.test.ts` | +26 | -20 | FORMAT | Prettier only | None |
| `cli-bin/discover.test.ts` | +10 | -10 | FORMAT | Prettier only | None |
| `compare-wire-format.ts` | +149 | -151 | FORMAT | Prettier only | None |
| `count-workers.ts` | +25 | -18 | FORMAT | Prettier only | None |
| `dump-agent-configs.ts` | +233 | -238 | FORMAT | Prettier only | None |
| `unit/agent.test.ts` | +120 | -116 | FORMAT | Prettier only | None |
| `unit/callback.test.ts` | +31 | -35 | FORMAT | Prettier only | None |
| `unit/cli-config.test.ts` | +156 | -104 | FORMAT | Prettier only | None |
| `unit/code-execution.test.ts` | +59 | -59 | FORMAT | Prettier only | None |
| `unit/config.test.ts` | +102 | -112 | FORMAT | Prettier only | None |
| `unit/context-passing.test.ts` | +7 | -7 | FORMAT | Prettier only | None |
| `unit/credentials.test.ts` | +126 | -136 | FORMAT | Prettier only | None |
| `unit/frameworks/detect.test.ts` | +92 | -92 | FORMAT | Prettier only | None |
| `unit/frameworks/langchain.test.ts` | +123 | -108 | FORMAT | Prettier only | None |
| `unit/frameworks/langgraph.test.ts` | +425 | -303 | FORMAT | Prettier only | None |
| `unit/frameworks/serializer.test.ts` | +157 | -142 | FORMAT | Prettier only | None |
| `unit/guardrail.test.ts` | +153 | -160 | FORMAT | Prettier only | None |
| `unit/handoff.test.ts` | +58 | -64 | FORMAT | Prettier only | None |
| `unit/kitchen-sink-structural.test.ts` | +189 | -178 | FORMAT | Prettier only | None |
| `unit/memory.test.ts` | +124 | -124 | FORMAT | Prettier only | None |
| `unit/result.test.ts` | +159 | -159 | FORMAT | Prettier only | None |
| `unit/runtime.test.ts` | +177 | -162 | FORMAT | Prettier only | None |
| `unit/serializer.test.ts` | +392 | -380 | FORMAT | Prettier only | None |
| `unit/skill.test.ts` | +99 | -99 | FORMAT | Prettier only | None |
| `unit/stream.test.ts` | +91 | -189 | FORMAT | Prettier only | None |
| `unit/swarm-workers.test.ts` | +267 | -252 | FORMAT | Prettier only | None |
| `unit/termination.test.ts` | +81 | -81 | FORMAT | Prettier only | None |
| `unit/testing/assertions.test.ts` | +69 | -80 | FORMAT | Prettier only | None |
| `unit/testing/expect.test.ts` | +73 | -87 | FORMAT | Prettier only | None |
| `unit/testing/mock.test.ts` | +77 | -86 | FORMAT | Prettier only | None |
| `unit/testing/strategy.test.ts` | +36 | -36 | FORMAT | Prettier only | None |
| `unit/tool.test.ts` | +266 | -275 | FORMAT | Prettier only | None |
| `unit/worker.test.ts` | +314 | -290 | FORMAT | Prettier only | None |
| `unit/wrappers/ai.test.ts` | +89 | -89 | FORMAT | Prettier only | None |
| `unit/wrappers/langchain.test.ts` | +82 | -82 | FORMAT | Prettier only | None |
| `unit/wrappers/langgraph.test.ts` | +115 | -108 | FORMAT, SEMANTIC | Fixed constant condition: `typeof 123` → `typeof prompt` | None |

---

## Manual Code Fixes Detail

### 1. Removed unused imports/variables — 8 files, 14 instances

| File | What was removed |
|------|-----------------|
| `src/agent.ts` | Unused `PromptTemplateInterface` import |
| `src/cli-config.ts` | Unused `execSync` import |
| `src/frameworks/langgraph-serializer.ts` | Unused `e` catch binding, prefixed unused `nodeName` with `_` |
| `src/frameworks/serializer.ts` | Unused `ConfigurationError` import |
| `src/runtime.ts` | Unused `OnToolResult`, `OnTextMention`, `OnCondition` imports |
| `src/testing/mock.ts` | Unused `ConfigurationError` import |
| `src/tool.ts` | Removed unused `zodSchemaToJson` async function, removed unused type params `TInput`/`TOutput` from `ToolOptions` |
| `src/worker.ts` | Prefixed unused `taskName` and `config` params with `_` |

**Risk:** None. Static analysis confirmed zero usage.

### 2. Replaced `hasOwnProperty` with `Object.hasOwn` — 1 file, 2 instances

| File | Line | Change |
|------|------|--------|
| `src/frameworks/langgraph-serializer.ts` | 685 | `proto.hasOwnProperty("invoke")` → `Object.hasOwn(proto, "invoke")` |
| `src/frameworks/langgraph-serializer.ts` | 1058 | Same pattern |

**Risk:** None. Functionally identical, Node 16+ supported.

### 3. Removed dead assignments — 3 files, 3 instances

| File | Change |
|------|--------|
| `src/wrappers/ai.ts` | `let provider = "openai"` → `let provider: string` |
| `src/wrappers/langchain.ts` | Same |
| `src/wrappers/langgraph.ts` | Same |

**Risk:** None. All branches assign before read.

### 4. Removed `this` alias — 1 file, 1 instance

| File | Change |
|------|--------|
| `src/code-execution.ts` | Removed `const executor = this`, used `this.execute(...)` directly (arrow function) |

**Risk:** None.

### 5. Added eslint-disable for `require()` — 1 file, 1 instance

| File | Reason |
|------|--------|
| `src/frameworks/serializer.ts` | `require("zod-to-json-schema")` in sync context — `import()` would cascade async |

**Risk:** None. Comment-only.

### 6. Fixed empty catch blocks — 1 test file, 7 instances

| File | Change |
|------|--------|
| `tests/_worker-harness.ts` | Added descriptive comments inside 7 empty `catch {}` blocks |

**Risk:** None. Comment-only.

### 7. Fixed constant condition — 1 test file, 1 instance

| File | Change |
|------|--------|
| `tests/unit/wrappers/langgraph.test.ts` | `typeof 123 === "string"` → `typeof prompt === "string"` (extracted to variable) |

**Risk:** None. Same test behavior.

---

## Formatting-Only Changes

**76 files** total (38 src + 38 tests) reformatted by Prettier:
- Consistent double quotes (was mixed)
- Trailing commas added
- Line wrapping at 100 characters
- Consistent semicolons and indentation

No logic changes.

---

## Remaining Warnings (297)

| Rule | Count | Effort |
|------|-------|--------|
| `@typescript-eslint/no-explicit-any` | ~130 | High |
| `@typescript-eslint/no-unsafe-function-type` | ~57 | Medium |
| Other | ~110 | Various |

---

## Verification

| Check | Result |
|-------|--------|
| `npm run lint` | 0 errors, 297 warnings |
| `npm run format:check` | All files pass |
| `npm run typecheck` | Clean |
| `npm test` | 35/36 pass (1 pre-existing server-dependent failure) |
