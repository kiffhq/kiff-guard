"""Agno adapter — middleware shape.

Agno invokes each tool hook as middleware:

    hook(function_name: str, func: callable, args: dict)

The hook calls func(**args) to let the call proceed. We translate that
directly into Guard.evaluate, closing over func as the continuation:

    from kiff_guard import Guard
    from kiff_guard.adapters.agno import agno_hook

    guard = Guard(mode="observe")                 # zero-config audit
    agent = Agent(model=..., tools=[...], tool_hooks=[agno_hook(guard)])

In enforce mode, a withheld decision raises Hold; Agno surfaces it as the
tool not executing. Map Hold onto Agno's human-in-the-loop / approval flow
in the app if you want the agent to see why.

This module imports nothing from Agno — it only matches Agno's hook
signature, so it works without agno installed (useful for tests). The
`agno` extra pulls the framework in for real use.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..guard import Guard


def agno_hook(guard: Guard) -> Callable[[str, Callable, Dict[str, Any]], Any]:
    """Return a callable matching Agno's tool_hooks signature, backed by
    the given Guard. Attach one hook per agent; share the guard's catalog
    + ledger across agents for one tower over the whole org."""

    def hook(function_name: str, func: Callable, args: Dict[str, Any]) -> Any:
        return guard.evaluate(function_name, args, run=lambda: func(**args))

    return hook
