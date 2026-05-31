"""Hermes (Nous Research) adapter — inverted-control / plugin-hook shape.

Hermes runs the tool itself after its `pre_tool_call` plugin hook
returns; the hook only votes allow/block. So this adapter does NOT use
`Guard.evaluate`'s run-callback — it uses the `observe` / `decide_only`
primitives and returns Hermes' block directive.

Verified against the hermes-agent source on main (see
docs/integration/frameworks/hermes.md):

  - The hook is invoked as `cb(tool_name, args, task_id, **kwargs)`.
  - To block, return `{"action": "block", "message": "<reason>"}`;
    Hermes short-circuits the tool and hands `message` to the model.
  - Any other return / None lets the tool proceed.

Usage — ship a Hermes plugin whose __init__.py does:

    from kiff_guard import Guard
    from kiff_guard.adapters.hermes import register_kiff_guard

    _GUARD = Guard(mode="observe")            # or enforce with a client
    def register(ctx):
        register_kiff_guard(ctx, _GUARD)

This module imports nothing from Hermes — it only matches the hook
signature and the block-directive shape, so it works (and tests) without
hermes-agent installed.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def hermes_pre_tool_call(guard, fail_closed: bool = True) -> Callable[..., Optional[Dict[str, Any]]]:
    """Return a callback for Hermes' `pre_tool_call` hook, backed by the
    given Guard.

    observe mode: records + learns every call, never blocks (returns None).
    enforce mode: calls KIFF; on a withheld decision returns a Hermes block
      directive so the tool never runs; on allowed, records that the tool
      ran and returns None.

    `fail_closed` (enforce only): if the guard errors (e.g. transport
    failure to KIFF), block the tool with an explanatory message. A
    governance layer should not wave traffic through when its decision
    path is down. observe mode always fails open — it never blocks
    anyway. Set fail_closed=False to fail open in enforce too (not
    recommended)."""

    def _hook(tool_name: str, args: Dict[str, Any], task_id: str = "", **kwargs: Any) -> Optional[Dict[str, Any]]:
        args = args if isinstance(args, dict) else {}
        if guard.mode == "observe":
            try:
                guard.observe(tool_name, args)
            except Exception:
                pass  # observe never blocks; swallow audit/learn errors
            return None

        # enforce
        try:
            decision = guard.decide_only(tool_name, args)
        except Exception as exc:
            if fail_closed:
                return {
                    "action": "block",
                    "message": f"KIFF guard unavailable; blocking {tool_name} (fail-closed): {exc}",
                }
            return None
        if decision.withheld:
            guard.record_withheld(tool_name, args, decision)
            return {
                "action": "block",
                "message": f"KIFF withheld {tool_name}: {decision.outcome} — {decision.reason}",
            }
        # allowed: Hermes will run the tool next. Record that it ran so the
        # audit reflects execution, not just the decision.
        guard.record_executed(tool_name, args, decision)
        return None

    return _hook


def register_kiff_guard(ctx, guard, fail_closed: bool = True) -> None:
    """Register the KIFF guard on a Hermes PluginContext. Call this from
    your plugin's `register(ctx)`:

        def register(ctx):
            register_kiff_guard(ctx, my_guard)
    """
    ctx.register_hook("pre_tool_call", hermes_pre_tool_call(guard, fail_closed=fail_closed))
