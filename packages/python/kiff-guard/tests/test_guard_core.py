"""Core guard behaviour: observe (decide-independent, #244) and enforce."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Catalog, Decision, Guard, Hold, Receipt  # noqa: E402


class _SpyClient:
    """Records decide() calls and returns a scripted outcome."""

    def __init__(self, outcome="allowed", reason="", proposal_id="prop_1"):
        self.calls = 0
        self._d = Decision(outcome=outcome, reason=reason, proposal_id=proposal_id)

    def decide(self, tenant, agent, tool, args):
        self.calls += 1
        return self._d


def _runner(box):
    def run():
        box.append(True)
        return "ran"
    return run


def test_observe_does_not_call_decide():
    spy = _SpyClient(outcome="blocked")
    guard = Guard(client=spy, mode="observe", agent="a")
    box = []
    out = guard.evaluate("refund_order", {"amount_cents": 5}, _runner(box))
    assert out == "ran"
    assert box == [True]          # tool ran
    assert spy.calls == 0         # the load-bearing #244 assertion
    r = guard.receipts[-1]
    assert r.state == "observed" and r.outcome == "observed" and r.executed is True


def test_observe_needs_no_client():
    guard = Guard(mode="observe", agent="a")
    out = guard.evaluate("send_email", {"to": "x", "body": "y"}, lambda: "ok")
    assert out == "ok"
    assert guard.receipts[-1].state == "observed"
    assert guard.catalog.tools["send_email"] == {"to", "body"}


def test_enforce_requires_client():
    try:
        Guard(mode="enforce")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "enforce" in str(e)


def test_enforce_allowed_runs_and_labels_governed():
    spy = _SpyClient(outcome="allowed")
    guard = Guard(client=spy, tenant="t", mode="enforce", agent="a")
    box = []
    out = guard.evaluate("refund_order", {"order_id": "o1"}, _runner(box))
    assert out == "ran" and box == [True]
    assert spy.calls == 1
    r = guard.receipts[-1]
    assert r.state == "governed" and r.outcome == "allowed"


def test_enforce_withheld_holds_and_does_not_run():
    spy = _SpyClient(outcome="approval_required", proposal_id="prop_42")
    guard = Guard(client=spy, tenant="t", mode="enforce", agent="a")
    box = []
    try:
        guard.evaluate("refund_order", {"order_id": "o1"}, _runner(box))
        assert False, "expected Hold"
    except Hold as h:
        assert h.decision.outcome == "approval_required"
        assert h.decision.proposal_id == "prop_42"
    assert box == []              # tool did NOT run
    r = guard.receipts[-1]
    assert r.state == "governed" and r.executed is False


def test_shared_catalog_and_ledger_across_agents():
    a = Guard(mode="observe", agent="support")
    b = Guard(mode="observe", agent="ops", catalog=a.catalog, ledger=a.receipts)
    a.evaluate("refund_order", {"amount_cents": 1}, lambda: None)
    b.evaluate("delete_account", {"account_id": "x"}, lambda: None)
    assert len(a.receipts) == 2
    assert {r.agent for r in a.receipts} == {"support", "ops"}
    assert {t for t in a.catalog.tools} == {"refund_order", "delete_account"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
