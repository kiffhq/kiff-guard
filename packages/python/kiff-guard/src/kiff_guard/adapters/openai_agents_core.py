"""SDK-independent core of the OpenAI Agents adapter.

The guardrail *callback* logic lives here so it can be unit-tested without
`openai-agents` installed: tests pass a fake `data` object and a fake
ToolGuardrailFunctionOutput factory. `openai_agents.py` wires this to the
real `@tool_input_guardrail` decorator + the real `ToolGuardrailFunctionOutput`.
"""

from __future__ import annotations

import json
from typing import Any, Callable


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _outputs():
    """Lazily import the SDK's ToolGuardrailFunctionOutput. Tests inject a
    fake via build_guardrail_callback(..., outputs=...)."""
    from agents import ToolGuardrailFunctionOutput  # lazy import
    return ToolGuardrailFunctionOutput


def build_guardrail_callback(
    guard: Any,
    fail_closed: bool = True,
    outputs: Any = None,
) -> Callable[[Any], Any]:
    """Build the tool-input-guardrail callback for `guard`.

    `outputs` is the ToolGuardrailFunctionOutput class (with .allow() /
    .reject_content(msg)). Defaults to the SDK's; tests inject a fake so
    the logic runs without openai-agents.
    """

    def _callback(data: Any) -> Any:
        out = outputs if outputs is not None else _outputs()
        ctx = getattr(data, "context", None)
        tool = getattr(ctx, "tool_name", "") or ""
        args = _parse_args(getattr(ctx, "tool_arguments", None))

        if guard.mode == "observe":
            try:
                guard.observe(tool, args)
            except Exception:
                pass  # observe never blocks
            return out.allow()

        # enforce
        try:
            decision = guard.decide_only(tool, args)
        except Exception as exc:
            if fail_closed:
                return out.reject_content(
                    f"KIFF guard unavailable; blocking {tool} (fail-closed): {exc}"
                )
            return out.allow()

        if decision.withheld:
            guard.record_withheld(tool, args, decision)
            return out.reject_content(
                f"KIFF withheld {tool}: {decision.outcome} — {decision.reason}"
            )
        # allowed: the SDK will run the tool next; record that it ran.
        guard.record_executed(tool, args, decision)
        return out.allow()

    return _callback
