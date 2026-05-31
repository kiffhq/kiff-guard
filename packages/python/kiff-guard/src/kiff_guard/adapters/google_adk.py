"""Google ADK (Agent Development Kit) adapter — before_tool_callback
(vote shape).

Verified against the ADK callbacks reference
(google.github.io/adk-docs → "Types of Callbacks" → Before Tool
Callback), confirmed against the docs source on GitHub:

  - ADK invokes ``before_tool_callback(tool, args, tool_context)`` just
    before a tool's ``run_async``, after the model emits the function
    call. ADK passes these **by keyword**, so the parameter names are
    significant.
  - Return ``None``  → the tool runs with the (possibly modified) args.
  - Return a ``dict`` → the tool is **skipped** and the dict is used
    directly as the tool result. This is the block path.

So ADK is a **vote shape** (like Hermes / OpenAI Agents), not a wrap
shape (Agno / LangGraph): ADK runs the tool itself; the callback only
*votes* by returning a dict (block) or ``None`` (allow). The adapter
therefore uses the guard's ``observe()`` / ``decide_only()`` primitives
plus ``record_executed`` / ``record_withheld`` — one receipt per call —
never ``evaluate(run=...)``.

This module imports nothing from ``google-adk`` — it only matches the
callback signature and returns plain ``dict`` / ``None`` — so importing
``kiff_guard`` never requires google-adk. The ``google-adk`` extra
(``pip install "kiff-guard[google-adk]"``) pulls it in for real use.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..guard import Guard


def kiff_before_tool_callback(
    guard: Guard, fail_closed: bool = True
) -> Callable[..., Optional[Dict[str, Any]]]:
    """Return a callable for ADK's ``before_tool_callback``, backed by
    the given Guard.

    observe mode: records + learns every tool call, never blocks
      (returns ``None`` so the tool proceeds).
    enforce mode: calls KIFF; on a withheld decision returns a dict so
      ADK skips the tool and feeds that dict back to the model as the
      result; on an allowed decision records execution and returns
      ``None`` so the tool runs.

    ``fail_closed`` (enforce only): if the guard errors (e.g. transport
    failure to KIFF), block the tool with an explanatory result dict. A
    governance layer should not wave traffic through when its decision
    path is down. observe mode always fails open — it never blocks
    anyway. Set ``fail_closed=False`` to fail open in enforce too (not
    recommended).
    """

    def _callback(
        tool: Any = None,
        args: Optional[Dict[str, Any]] = None,
        tool_context: Any = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        tool_name = getattr(tool, "name", "") or ""
        args = args if isinstance(args, dict) else {}

        if guard.mode == "observe":
            try:
                guard.observe(tool_name, args)
            except Exception:
                pass  # observe never blocks; swallow audit/learn errors
            return None  # proceed

        # enforce
        try:
            decision = guard.decide_only(tool_name, args)
        except Exception as exc:
            if fail_closed:
                return {
                    "error": f"KIFF guard unavailable; blocking {tool_name} (fail-closed): {exc}"
                }
            return None
        if decision.withheld:
            guard.record_withheld(tool_name, args, decision)
            return {
                "error": f"KIFF withheld {tool_name}: {decision.outcome} — {decision.reason}"
            }
        # allowed: ADK will run the tool next. Record that it ran so the
        # audit reflects execution, not just the decision.
        guard.record_executed(tool_name, args, decision)
        return None  # proceed

    return _callback
