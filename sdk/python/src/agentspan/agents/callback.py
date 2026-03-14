# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CallbackHandler — composable lifecycle hooks for agents.

Provides a base class for hooking into agent, model, and tool lifecycle
events.  Multiple handlers can be chained on the same agent; they run
in list order with first-non-empty-dict-wins short-circuit semantics.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agentspan.agents.callback")

# Maps server callback positions to CallbackHandler method names.
POSITION_TO_METHOD: Dict[str, str] = {
    "before_agent": "on_agent_start",
    "after_agent": "on_agent_end",
    "before_model": "on_model_start",
    "after_model": "on_model_end",
    "before_tool": "on_tool_start",
    "after_tool": "on_tool_end",
}

# Reverse mapping: legacy Agent attribute name → position.
_LEGACY_ATTR_TO_POSITION: Dict[str, str] = {
    "before_agent_callback": "before_agent",
    "after_agent_callback": "after_agent",
    "before_model_callback": "before_model",
    "after_model_callback": "after_model",
}


class CallbackHandler:
    """Base class for agent lifecycle callbacks.

    Subclass and override any of the six hook methods.  Each method
    receives keyword arguments from the server and returns either
    ``None`` (continue to next handler) or a non-empty ``dict``
    (short-circuit remaining handlers and use as override).

    Example::

        class TimingHandler(CallbackHandler):
            def on_agent_start(self, **kwargs):
                self.t0 = time.time()

            def on_agent_end(self, **kwargs):
                print(f"Took {time.time() - self.t0:.2f}s")
    """

    def on_agent_start(self, **kwargs: Any) -> Optional[dict]:
        """Called before the agent begins processing."""
        return None

    def on_agent_end(self, **kwargs: Any) -> Optional[dict]:
        """Called after the agent finishes processing."""
        return None

    def on_model_start(self, **kwargs: Any) -> Optional[dict]:
        """Called before each LLM call."""
        return None

    def on_model_end(self, **kwargs: Any) -> Optional[dict]:
        """Called after each LLM call."""
        return None

    def on_tool_start(self, **kwargs: Any) -> Optional[dict]:
        """Called before each tool execution."""
        return None

    def on_tool_end(self, **kwargs: Any) -> Optional[dict]:
        """Called after each tool execution."""
        return None


def _handler_overrides(handler: CallbackHandler, method_name: str) -> bool:
    """Return True if *handler* actually overrides *method_name*."""
    return getattr(type(handler), method_name) is not getattr(CallbackHandler, method_name)


def _chain_callbacks_for_position(
    position: str,
    handlers: List[CallbackHandler],
    legacy_fn: Optional[Callable[..., Any]] = None,
) -> Optional[Callable[..., Any]]:
    """Build a single callable that chains legacy + handler-list callbacks.

    Returns ``None`` when nothing is registered for *position* (no worker
    should be created).

    Execution order:
    1. Legacy callable (if provided) — runs first for backward compat.
    2. Each handler in list order whose method is overridden.

    First non-empty dict return short-circuits remaining handlers.
    """
    method_name = POSITION_TO_METHOD[position]

    # Filter to handlers that actually override this method.
    active_handlers = [h for h in handlers if _handler_overrides(h, method_name)]

    if legacy_fn is None and not active_handlers:
        return None

    def chained(**kwargs: Any) -> dict:
        # Legacy callable first.
        if legacy_fn is not None:
            try:
                result = legacy_fn(**kwargs)
                if isinstance(result, dict) and result:
                    return result
            except Exception as e:
                logger.error("Legacy callback for %s failed: %s", position, e)

        # Handler chain.
        for handler in active_handlers:
            try:
                result = getattr(handler, method_name)(**kwargs)
                if isinstance(result, dict) and result:
                    return result
            except Exception as e:
                logger.error(
                    "%s.%s failed: %s",
                    type(handler).__name__,
                    method_name,
                    e,
                )

        return {}

    return chained
