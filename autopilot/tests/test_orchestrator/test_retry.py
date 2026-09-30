"""Tests for error retry orchestration — RetryPolicy and retry_with_policy."""

from __future__ import annotations

import time

import pytest

from autopilot.orchestrator.retry import RetryPolicy, retry_with_policy


class TestRetrySucceeds:
    """Verify that successful calls don't trigger retries."""

    def test_retry_succeeds_first_try(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            return "success"

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)
        result = retry_with_policy(fn, policy)

        assert result == "success"
        assert call_count[0] == 1

    def test_return_value_is_passed_through(self):
        policy = RetryPolicy(max_retries=2, backoff_base=0.001)
        result = retry_with_policy(lambda: 42, policy)
        assert result == 42

    def test_return_none_is_valid(self):
        policy = RetryPolicy(max_retries=2, backoff_base=0.001)
        result = retry_with_policy(lambda: None, policy)
        assert result is None


class TestRetryAfterFailures:
    """Verify that the function is retried on failure and eventually succeeds."""

    def test_retry_succeeds_after_failures(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError(f"attempt {call_count[0]} failed")
            return "recovered"

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)
        result = retry_with_policy(fn, policy)

        assert result == "recovered"
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_retry_succeeds_on_last_attempt(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] <= 3:  # fails 3 times, succeeds on 4th (max_retries=3)
                raise ValueError("not yet")
            return "finally"

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)
        result = retry_with_policy(fn, policy)

        assert result == "finally"
        assert call_count[0] == 4  # 3 retries + 1 initial


class TestRetryExhausted:
    """Verify that all retries exhausted raises the last exception."""

    def test_retry_exhausted_raises(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise RuntimeError(f"fail #{call_count[0]}")

        policy = RetryPolicy(max_retries=2, backoff_base=0.001)

        with pytest.raises(RuntimeError, match="fail #3"):
            retry_with_policy(fn, policy)

        assert call_count[0] == 3  # 1 initial + 2 retries

    def test_zero_retries_raises_immediately(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise TypeError("no retries")

        policy = RetryPolicy(max_retries=0, backoff_base=0.001)

        with pytest.raises(TypeError, match="no retries"):
            retry_with_policy(fn, policy)

        assert call_count[0] == 1

    def test_non_retryable_exception_raises_immediately(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise KeyboardInterrupt("user abort")

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)

        with pytest.raises(KeyboardInterrupt):
            retry_with_policy(fn, policy, retryable_exceptions=(ValueError,))

        assert call_count[0] == 1  # no retries for non-matching exception


class TestExponentialBackoffDelays:
    """Verify exponential backoff delay calculation."""

    def test_exponential_backoff_delays(self):
        policy = RetryPolicy(
            max_retries=3,
            backoff_base=1.0,
            backoff_multiplier=5.0,
            max_backoff=60.0,
        )
        # attempt 0: 1.0 * 5^0 = 1.0
        assert policy.get_delay(0) == 1.0
        # attempt 1: 1.0 * 5^1 = 5.0
        assert policy.get_delay(1) == 5.0
        # attempt 2: 1.0 * 5^2 = 25.0
        assert policy.get_delay(2) == 25.0
        # attempt 3: 1.0 * 5^3 = 125.0, but capped at 60.0
        assert policy.get_delay(3) == 60.0

    def test_backoff_respects_max(self):
        policy = RetryPolicy(
            backoff_base=10.0,
            backoff_multiplier=10.0,
            max_backoff=50.0,
        )
        # 10 * 10^0 = 10
        assert policy.get_delay(0) == 10.0
        # 10 * 10^1 = 100, capped at 50
        assert policy.get_delay(1) == 50.0


class TestLinearBackoffDelays:
    """Verify linear backoff delay calculation (multiplier=1.0)."""

    def test_linear_backoff_delays(self):
        policy = RetryPolicy(
            max_retries=3,
            backoff_base=2.0,
            backoff_multiplier=1.0,
            max_backoff=60.0,
        )
        # With multiplier=1.0: delay = base * 1.0^attempt = base always
        assert policy.get_delay(0) == 2.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 2.0
        assert policy.get_delay(3) == 2.0


class TestFromAgentConfig:
    """Verify RetryPolicy.from_agent_config() parsing."""

    def test_from_agent_config_exponential(self):
        config = {"max_retries": 5, "backoff": "exponential"}
        policy = RetryPolicy.from_agent_config(config)
        assert policy.max_retries == 5
        assert policy.backoff_multiplier == 5.0  # default exponential multiplier

    def test_from_agent_config_linear(self):
        config = {"max_retries": 2, "backoff": "linear"}
        policy = RetryPolicy.from_agent_config(config)
        assert policy.max_retries == 2
        assert policy.backoff_multiplier == 1.0  # linear = multiplier 1

    def test_from_agent_config_unknown_backoff_uses_defaults(self):
        config = {"max_retries": 4, "backoff": "unknown"}
        policy = RetryPolicy.from_agent_config(config)
        assert policy.max_retries == 4
        # Unknown uses default constructor
        assert policy.backoff_multiplier == 5.0

    def test_from_agent_config_missing_keys_uses_defaults(self):
        config = {}
        policy = RetryPolicy.from_agent_config(config)
        assert policy.max_retries == 3
        assert policy.backoff_multiplier == 5.0

    def test_from_agent_config_partial_keys(self):
        config = {"max_retries": 1}
        policy = RetryPolicy.from_agent_config(config)
        assert policy.max_retries == 1
        assert policy.backoff_multiplier == 5.0  # default exponential


class TestOnRetryCallback:
    """Verify the on_retry callback fires on each retry."""

    def test_on_retry_callback_called(self):
        retry_log: list[tuple[int, str]] = []
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise IOError(f"fail-{call_count[0]}")
            return "done"

        def on_retry(attempt: int, exc: Exception) -> None:
            retry_log.append((attempt, str(exc)))

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)
        result = retry_with_policy(fn, policy, on_retry=on_retry)

        assert result == "done"
        assert len(retry_log) == 2
        assert retry_log[0] == (0, "fail-1")
        assert retry_log[1] == (1, "fail-2")

    def test_on_retry_not_called_on_success(self):
        retry_log: list = []

        def on_retry(attempt: int, exc: Exception) -> None:
            retry_log.append(attempt)

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)
        retry_with_policy(lambda: "ok", policy, on_retry=on_retry)

        assert retry_log == []

    def test_on_retry_called_for_each_attempt_before_exhaustion(self):
        retry_log: list[int] = []
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise OSError(f"always fails {call_count[0]}")

        def on_retry(attempt: int, exc: Exception) -> None:
            retry_log.append(attempt)

        policy = RetryPolicy(max_retries=3, backoff_base=0.001)

        with pytest.raises(OSError):
            retry_with_policy(fn, policy, on_retry=on_retry)

        # on_retry called before each retry (attempts 0, 1, 2 = 3 retries)
        assert retry_log == [0, 1, 2]


class TestRetryTimingReal:
    """Verify that actual time.sleep delays are applied (real, not mocked)."""

    def test_retry_takes_real_time(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("not yet")
            return "ok"

        policy = RetryPolicy(
            max_retries=3,
            backoff_base=0.05,  # 50ms
            backoff_multiplier=1.0,  # linear
        )

        start = time.monotonic()
        result = retry_with_policy(fn, policy)
        elapsed = time.monotonic() - start

        assert result == "ok"
        # 2 retries * 0.05s = 0.1s minimum
        assert elapsed >= 0.08, f"Expected at least 80ms, got {elapsed:.3f}s"
