"""Google ADK adapter — before_tool_callback (vote shape)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Decision, Guard  # noqa: E402
from kiff_guard.adapters.google_adk import kiff_before_tool_callback  # noqa: E402


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


class _Tool:
    def __init__(self, name):
        self.name = name


def test_observe_never_blocks_and_records_observed():
    guard = Guard(mode="observe", agent="adk")
    cb = kiff_before_tool_callback(guard)
    out = cb(tool=_Tool("delete_account"), args={"account_id": "a9"}, tool_context=None)
    assert out is None  # observe always proceeds
    assert guard.receipts[-1].state == "observed"
    assert guard.catalog.tools["delete_account"] == {"account_id"}


def test_enforce_allowed_returns_none_and_records_one_receipt():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="adk")
    cb = kiff_before_tool_callback(guard)
    out = cb(tool=_Tool("read_file"), args={"path": "x"}, tool_context=None)
    assert out is None  # allowed -> ADK runs the tool
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is True


def test_enforce_withheld_returns_block_dict_and_one_receipt():
    stub = _StubClient(outcome="blocked", reason="not allowed in this state")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="adk")
    cb = kiff_before_tool_callback(guard)
    out = cb(tool=_Tool("refund"), args={"order_id": "o1"}, tool_context=None)
    assert isinstance(out, dict)  # dict -> ADK skips the tool
    assert "error" in out and "withheld" in out["error"]
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is False


def test_enforce_fail_closed_on_client_error():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="adk")
    cb = kiff_before_tool_callback(guard, fail_closed=True)
    out = cb(tool=_Tool("terminal"), args={"cmd": "ls"}, tool_context=None)
    assert isinstance(out, dict) and "fail-closed" in out["error"]


def test_enforce_fail_open_when_configured():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="adk")
    cb = kiff_before_tool_callback(guard, fail_closed=False)
    out = cb(tool=_Tool("terminal"), args={"cmd": "ls"}, tool_context=None)
    assert out is None  # fail open -> tool proceeds


def test_unknown_outcome_fails_safe():
    # E4: an outcome the SDK has never heard of must withhold (block).
    stub = _StubClient(outcome="quarantined", reason="unknown future outcome")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="adk")
    cb = kiff_before_tool_callback(guard)
    out = cb(tool=_Tool("delete_account"), args={"account_id": "a9"}, tool_context=None)
    assert isinstance(out, dict)  # blocked, not allowed
    assert len(guard.receipts) == 1 and guard.receipts[-1].executed is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
