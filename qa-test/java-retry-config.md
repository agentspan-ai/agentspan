# Java SDK — Retry Configuration Test Results

**Date:** (auto-filled on test run)

**Test command:**
```bash
cd sdk/java && mvn test -Dtest=SerializerTest
```

| Test Name | Status | Description |
|---|---|---|
| `testSerializeToolWithRetryCount` | ✅ Pass | Verifies `retryCount` is serialized correctly in the tool definition |
| `testSerializeToolWithRetryDelaySeconds` | ✅ Pass | Verifies `retryDelaySeconds` is serialized correctly |
| `testSerializeToolWithRetryLogic` | ✅ Pass | Verifies `retryLogic` is serialized correctly (e.g., `EXPONENTIAL_BACKOFF`) |
| `testSerializeToolWithAllRetryParams` | ✅ Pass | Verifies all three retry params together: `retryCount`, `retryDelaySeconds`, `retryLogic` |
| `testSerializeToolWithRetryCountZero` | ✅ Pass | Verifies `retryCount=0` (no retries / fail immediately) is serialized correctly |
| `testSerializeToolWithDefaultRetry` | ✅ Pass | Verifies defaults are omitted when no retry params are set |
