"""Hermes adapter + the observe/decide_only core primitives it uses."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Decision, Guard  # noqa: E402
from kiff_guard.adapters.hermes import hermes_pre_tool_call, register_kiff_guard  # noqa: E402


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


class _FakeCtx:
    """Mimics Hermes' PluginContext.register_hook for the adapter test."""

    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, cb):
        self.hooks.setdefault(name, []).append(cb)


# --- core primitives -------------------------------------------------------

def test_observe_primitive_records_without_decision():
    guard = Guard(mode="observe", agent="hermes")
    guard.observe("terminal", {"command": "ls"})
    r = guard.receipts[-1]
    assert r.state == "observed" and r.outcome == "observed"
    assert guard.catalog.tools["terminal"] == {"command"}


def test_decide_only_does_not_record():
    # #239 fix: decide_only decides + returns, but does NOT record — the
    # adapter records exactly once. So no receipt is written here.
    stub = _StubClient(outcome="approval_required", proposal_id="p9")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="hermes")
    d = guard.decide_only("write_file", {"path": "/etc/x"})
    assert stub.calls == 1
    assert d.outcome == "approval_required" and d.proposal_id == "p9"
    assert guard.receipts == []                 # decide_only records nothing


def test_decide_only_requires_client():
    guard = Guard(mode="observe")
    try:
        guard.decide_only("t", {})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_record_executed_writes_one_governed_receipt():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce")
    d = guard.decide_only("terminal", {"command": "ls"})
    guard.record_executed("terminal", {"command": "ls"}, d)
    assert len(guard.receipts) == 1            # exactly one, not two
    assert guard.receipts[-1].executed is True


def test_record_withheld_writes_one_governed_receipt():
    stub = _StubClient(outcome="blocked")
    guard = Guard(client=stub, tenant="t", mode="enforce")
    d = guard.decide_only("delete_account", {"account_id": "a9"})
    guard.record_withheld("delete_account", {"account_id": "a9"}, d)
    assert len(guard.receipts) == 1
    r = guard.receipts[-1]
    assert r.state == "governed" and r.executed is False


# --- Hermes adapter --------------------------------------------------------

def test_hermes_observe_never_blocks():
    guard = Guard(mode="observe", agent="hermes")
    hook = hermes_pre_tool_call(guard)
    out = hook("terminal", {"command": "rm -rf /"}, task_id="t1")
    assert out is None                       # observe never blocks
    assert guard.receipts[-1].state == "observed"


def test_hermes_enforce_allows_returns_none_and_records_one_receipt():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="hermes")
    hook = hermes_pre_tool_call(guard)
    out = hook("read_file", {"path": "x"}, task_id="t1")
    assert out is None                       # allowed -> Hermes runs the tool
    # exactly one governed receipt, executed=True (no double-receipt; #239)
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is True


def test_hermes_enforce_withheld_returns_block_directive_and_one_receipt():
    stub = _StubClient(outcome="blocked", reason="delete_account is blocked by policy")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="hermes")
    hook = hermes_pre_tool_call(guard)
    out = hook("delete_account", {"account_id": "a9"}, task_id="t1")
    assert isinstance(out, dict)
    assert out["action"] == "block"
    assert "blocked" in out["message"]
    # exactly one governed receipt, executed=False
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is False


def test_hermes_enforce_fail_closed_on_client_error():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="hermes")
    hook = hermes_pre_tool_call(guard, fail_closed=True)
    out = hook("terminal", {"command": "ls"}, task_id="t1")
    assert isinstance(out, dict) and out["action"] == "block"
    assert "fail-closed" in out["message"]


def test_hermes_enforce_fail_open_when_configured():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="hermes")
    hook = hermes_pre_tool_call(guard, fail_closed=False)
    out = hook("terminal", {"command": "ls"}, task_id="t1")
    assert out is None                       # fail open -> tool proceeds


def test_register_kiff_guard_wires_pre_tool_call():
    guard = Guard(mode="observe")
    ctx = _FakeCtx()
    register_kiff_guard(ctx, guard)
    assert "pre_tool_call" in ctx.hooks
    assert len(ctx.hooks["pre_tool_call"]) == 1
    # the registered callback works and accepts Hermes' kwargs
    cb = ctx.hooks["pre_tool_call"][0]
    assert cb("terminal", {"command": "ls"}, task_id="t", session_id="s", tool_call_id="tc") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
