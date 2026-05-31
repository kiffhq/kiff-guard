"""Pydantic AI adapter — before_tool_execute hook (vote shape)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Decision, Guard  # noqa: E402
from kiff_guard.adapters.pydantic_ai import kiff_before_tool_execute  # noqa: E402


class _StubClient:
    def __init__(self, outcome="allowed", reason="", proposal_id="prop_1", raises=False):
        self._d = Decision(outcome=outcome, reason=reason, proposal_id=proposal_id)
        self._raises = raises
        self.calls = 0

    def decide(self, tenant, agent, tool, args):
        self.calls += 1
        if self._raises:
            raise RuntimeError("transport down")
        return self._d


class _FakeSkip(Exception):
    """Stand-in for pydantic_ai.exceptions.SkipToolExecution so tests run
    without pydantic-ai installed."""


class _Call:
    def __init__(self, name):
        self.tool_name = name


def _hook(guard, **kw):
    return kiff_before_tool_execute(guard, skip_factory=lambda result: _FakeSkip(result), **kw)


def test_observe_never_blocks_and_records_observed():
    guard = Guard(mode="observe", agent="pyd")
    hook = _hook(guard)
    out = hook(ctx=None, call=_Call("send_email"), tool_def=None, args={"to": "x", "body": "y"})
    assert out == {"to": "x", "body": "y"}  # observe returns args (proceed)
    assert guard.receipts[-1].state == "observed"
    assert guard.catalog.tools["send_email"] == {"to", "body"}


def test_enforce_allowed_returns_args_and_records_one_receipt():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="pyd")
    hook = _hook(guard)
    out = hook(ctx=None, call=_Call("read_file"), tool_def=None, args={"path": "x"})
    assert out == {"path": "x"}  # allowed -> tool runs
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is True


def test_enforce_withheld_raises_skip_and_records_one_receipt():
    stub = _StubClient(outcome="blocked", reason="blocked by policy")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="pyd")
    hook = _hook(guard)
    raised = False
    try:
        hook(ctx=None, call=_Call("delete_account"), tool_def=None, args={"account_id": "a9"})
    except _FakeSkip as exc:
        raised = True
        assert "withheld" in str(exc)
    assert raised  # withheld -> SkipToolExecution
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is False


def test_enforce_fail_closed_on_client_error():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="pyd")
    hook = _hook(guard, fail_closed=True)
    raised = False
    try:
        hook(ctx=None, call=_Call("terminal"), tool_def=None, args={"cmd": "ls"})
    except _FakeSkip as exc:
        raised = True
        assert "fail-closed" in str(exc)
    assert raised


def test_enforce_fail_open_when_configured():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="pyd")
    hook = _hook(guard, fail_closed=False)
    out = hook(ctx=None, call=_Call("terminal"), tool_def=None, args={"cmd": "ls"})
    assert out == {"cmd": "ls"}  # fail open -> tool proceeds


def test_unknown_outcome_fails_safe():
    # E4: an unknown future outcome must withhold (raise skip).
    stub = _StubClient(outcome="quarantined", reason="unknown future outcome")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="pyd")
    hook = _hook(guard)
    raised = False
    try:
        hook(ctx=None, call=_Call("delete_account"), tool_def=None, args={"account_id": "a9"})
    except _FakeSkip:
        raised = True
    assert raised
    assert len(guard.receipts) == 1 and guard.receipts[-1].executed is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
