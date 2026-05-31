"""Pydantic AI adapter — tool execution hook (vote shape).

Verified against the Pydantic AI hooks reference (ai.pydantic.dev/hooks,
confirmed against docs/hooks.md on the pydantic/pydantic-ai repo):

  - The pre-execution seam is the **tool execution hook**, registered on
    a ``Hooks`` capability via ``@hooks.on.before_tool_execute`` (or the
    ``before_tool_execute=`` constructor kwarg). It fires when the tool
    function is about to run, after the model's JSON args are validated;
    ``args`` is always the validated ``dict[str, Any]``.
  - The hook receives ``ctx`` (RunContext) plus keyword-only ``call``
    (ToolCallPart, carrying ``tool_name`` + ``args``), ``tool_def``, and
    ``args``.
  - To **skip execution**, raise ``SkipToolExecution(result)`` — the
    tool body never runs and ``result`` is used as the tool's result.
    To allow, return ``args`` unchanged.

So Pydantic AI is a **vote shape**: the framework runs the tool; the
hook votes by returning args (allow) or raising ``SkipToolExecution``
(block). The adapter uses the guard's ``observe()`` / ``decide_only()``
primitives + ``record_executed`` / ``record_withheld`` — one receipt per
call — never ``evaluate(run=...)``.

Pydantic AI hooks may be sync or async (sync are auto-wrapped); this
adapter is sync, matching the guard's sync client.

This module imports ``pydantic_ai`` **lazily** (only when raising the
SDK's ``SkipToolExecution``), so importing ``kiff_guard`` never requires
pydantic-ai. The ``pydantic-ai`` extra pulls it in for real use.
"""

from __future__ import annotations

from typing import Any, Callable, Dict


def _skip_execution(result: Any) -> Exception:
    """Build the SDK's SkipToolExecution exception. Imported lazily so
    the module loads without pydantic-ai installed (for tests)."""
    from pydantic_ai.exceptions import SkipToolExecution  # lazy import

    return SkipToolExecution(result)


def kiff_before_tool_execute(
    guard: Any, fail_closed: bool = True, skip_factory: Callable[[Any], Exception] = _skip_execution
) -> Callable[..., Dict[str, Any]]:
    """Return a ``before_tool_execute`` hook callable backed by the given
    Guard, ready to register on a ``Hooks`` capability:

        from pydantic_ai import Agent
        from pydantic_ai.capabilities import Hooks
        from kiff_guard import Guard
        from kiff_guard.adapters.pydantic_ai import kiff_before_tool_execute

        guard = Guard(mode="observe")        # zero-config audit
        hooks = Hooks(before_tool_execute=kiff_before_tool_execute(guard))
        agent = Agent("...", tools=[...], capabilities=[hooks])

    observe mode: records + learns every call, returns ``args`` (never
      blocks).
    enforce mode: on a withheld KIFF decision raises ``SkipToolExecution``
      so the tool never runs; on allowed, records execution and returns
      ``args``.
    fail_closed (enforce, default True): on a guard/transport error,
      skip the tool — a control tower shouldn't wave traffic through when
      its decision path is down. observe always allows.

    ``skip_factory`` is injectable so tests can run without pydantic-ai
    installed; it defaults to raising the SDK's ``SkipToolExecution``.
    """

    def _hook(ctx: Any = None, *, call: Any = None, tool_def: Any = None, args: Any = None, **kwargs: Any) -> Dict[str, Any]:
        tool_name = getattr(call, "tool_name", "") or ""
        args = args if isinstance(args, dict) else {}

        if guard.mode == "observe":
            try:
                guard.observe(tool_name, args)
            except Exception:
                pass  # observe never blocks
            return args

        # enforce
        try:
            decision = guard.decide_only(tool_name, args)
        except Exception as exc:
            if fail_closed:
                raise skip_factory(
                    f"KIFF guard unavailable; blocking {tool_name} (fail-closed): {exc}"
                )
            return args
        if decision.withheld:
            guard.record_withheld(tool_name, args, decision)
            raise skip_factory(
                f"KIFF withheld {tool_name}: {decision.outcome} — {decision.reason}"
            )
        # allowed: the framework will run the tool next; record that.
        guard.record_executed(tool_name, args, decision)
        return args

    return _hook
