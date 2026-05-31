"""OpenAI Agents SDK adapter — tool input guardrail (vote shape).

Verified against the OpenAI Agents SDK (openai-agents-python v0.17.4):

The synchronous pre-tool-execution seam is the **tool input guardrail**,
not `needs_approval`. Per the guardrails docs, "tool input guardrails run
before the tool executes and can skip the call, replace the output with a
message, or raise a tripwire." That is the policy gate; `needs_approval`
is the heavyweight human-pause path (the run pauses and surfaces
`interruptions`, resumed via RunState) — the right tool for a human, not
for a millisecond machine decision.

So OpenAI Agents SDK is a **vote shape** (like Hermes), not a wrap shape
(Agno/LangGraph): the guardrail returns a verdict and the SDK runs or
skips the tool. The adapter therefore uses the guard's `observe()` /
`decide_only()` primitives, not `evaluate(run=...)`.

The contract (verified in the reference):

    @tool_input_guardrail
    def gd(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        # data.context.tool_name      -> str
        # data.context.tool_arguments -> raw JSON args string
        # data.context.tool_call_id   -> str
        ...
        return ToolGuardrailFunctionOutput.allow()                  # run
        return ToolGuardrailFunctionOutput.reject_content("...")    # block

    @function_tool(tool_input_guardrails=[gd])
    def my_tool(...): ...

Usage:

    from kiff_guard import Guard
    from kiff_guard.adapters.openai_agents import kiff_tool_input_guardrail

    guard = Guard(mode="observe")                 # zero-config audit
    gd = kiff_tool_input_guardrail(guard)         # a ToolInputGuardrail

    @function_tool(tool_input_guardrails=[gd])
    def refund_order(order_id: str, amount_cents: int): ...

This module imports the OpenAI SDK lazily (only when actually building a
guardrail / a reject result), so importing kiff_guard never requires
`openai-agents`. The `openai` extra (maps to the `openai-agents` package)
pulls it in for real use.
"""

from __future__ import annotations

from typing import Any

from .openai_agents_core import build_guardrail_callback


def kiff_tool_input_guardrail(guard: Any, fail_closed: bool = True) -> Any:
    """Return a `ToolInputGuardrail` wired to the given Guard, ready to
    pass to `@function_tool(tool_input_guardrails=[...])`.

    observe mode: records + learns every tool call, always allows.
    enforce mode: a withheld KIFF decision returns reject_content(reason)
      so the SDK skips the tool and hands the reason to the model; an
      allowed decision records execution and allows.
    fail_closed (enforce, default True): on a guard/transport error,
      reject — a control tower shouldn't wave traffic through when its
      decision path is down. observe always allows.

    Requires `openai-agents` installed (the SDK provides the
    `tool_input_guardrail` decorator + `ToolGuardrailFunctionOutput`)."""
    from agents import tool_input_guardrail  # lazy import

    return tool_input_guardrail(build_guardrail_callback(guard, fail_closed=fail_closed))
