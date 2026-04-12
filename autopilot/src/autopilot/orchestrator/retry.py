"""Error retry orchestration — configurable retry policies for agent operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple, Type


@dataclass
class RetryPolicy:
    """Configurable retry policy for agent operations.

    Attributes:
        max_retries: Maximum number of retry attempts (does not count the initial try).
        backoff_base: Base delay in seconds for the first retry.
        backoff_multiplier: Multiplier for exponential backoff (delay = base * multiplier^attempt).
        max_backoff: Maximum delay cap in seconds.
    """

    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_multiplier: float = 5.0
    max_backoff: float = 60.0

    @classmethod
    def from_agent_config(cls, error_handling: dict) -> RetryPolicy:
        """Create a RetryPolicy from an agent's error_handling config.

        Args:
            error_handling: Dict from agent.yaml ``error_handling`` section.
                Expected keys: ``max_retries`` (int), ``backoff`` (str: "exponential" or "linear").

        Returns:
            A RetryPolicy configured according to the agent's settings.
        """
        max_retries = error_handling.get("max_retries", 3)
        backoff = error_handling.get("backoff", "exponential")
        if backoff == "exponential":
            return cls(max_retries=max_retries)
        elif backoff == "linear":
            return cls(max_retries=max_retries, backoff_multiplier=1.0)
        else:
            return cls(max_retries=max_retries)

    def get_delay(self, attempt: int) -> float:
        """Calculate the delay for a given attempt number (0-indexed).

        Args:
            attempt: The retry attempt number (0 for first retry, 1 for second, etc.).

        Returns:
            Delay in seconds, capped at max_backoff.
        """
        delay = self.backoff_base * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_backoff)


def retry_with_policy(
    fn: Callable[[], Any],
    policy: RetryPolicy,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Any:
    """Execute a function with retry policy.

    The function is called up to ``policy.max_retries + 1`` times total
    (one initial call plus retries). On each retryable failure, the policy's
    backoff delay is applied before the next attempt.

    Args:
        fn: The function to call (no args).
        policy: The retry policy controlling attempts and backoff.
        retryable_exceptions: Exception types that trigger retries.
        on_retry: Optional callback(attempt, exception) called before each retry sleep.

    Returns:
        The function's return value on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_error: Optional[Exception] = None
    for attempt in range(policy.max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as e:
            last_error = e
            if attempt < policy.max_retries:
                if on_retry:
                    on_retry(attempt, e)
                delay = policy.get_delay(attempt)
                time.sleep(delay)
    raise last_error  # type: ignore[misc]
