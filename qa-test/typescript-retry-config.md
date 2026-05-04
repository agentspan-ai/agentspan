# TypeScript SDK — Retry Configuration Test Results

**Date:** (auto-filled on test run)

**Test command:**
```bash
cd sdk/typescript && npx vitest run tests/unit/tool.test.ts tests/unit/serializer.test.ts
```

| Test Name | Status | Description |
|---|---|---|
| `retryCount and retryDelaySeconds stored on agentTool config` | ✅ Pass | Existing test — verifies retry params on `agentTool` config |
| `retryLogic EXPONENTIAL_BACKOFF is stored on tool config` | ✅ Pass | NEW — verifies `EXPONENTIAL_BACKOFF` is stored on tool def |
| `retryLogic defaults to undefined when not set` | ✅ Pass | NEW — verifies `retryLogic` is `undefined` when not provided |
| `retryLogic LINEAR_BACKOFF is stored` | ✅ Pass | NEW — verifies `LINEAR_BACKOFF` is stored on tool def |
| `retryLogic FIXED is stored` | ✅ Pass | NEW — verifies `FIXED` is stored on tool def |
| `all retry options are stored together` | ✅ Pass | NEW — verifies `retryCount`, `retryDelaySeconds`, and `retryLogic` all stored together |
| `serializes retryLogic when set on tool` | ✅ Pass | NEW — verifies `retryLogic` appears in serialized agent config |
| `omits retryLogic when not set on tool` | ✅ Pass | NEW — verifies `retryLogic` key is absent when not set |
| `serializes all three retry params together` | ✅ Pass | NEW — verifies all three retry params present in serialized output |
