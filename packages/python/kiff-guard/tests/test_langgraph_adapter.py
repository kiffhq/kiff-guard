"""LangGraph adapter (wrap_tool_call shape). langchain is not installed in
CI, so the block path's ToolMessage construction is monkeypatched; the
observe / allowed paths need no langchain at all."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import kiff_guard.adapters.langgraph as lg  # noqa: E402
from kiff_guard import Decision, Guard  # noqa: E402


class _Req:
    """Mimics LangChain's ToolCallRequest: a .tool_call dict."""

    def __init__(self, name, args, call_id="tc1"):
        self.tool_call = {"name": name, "args": args, "id": call_id}


class _StubClient:
    def __init__(self, outcome="allowed", reason="", proposal_id="p1"):
        self._d = Decision(outcome=outcome, reason=reason, proposal_id=proposal_id)
        self.calls = 0

    def decide(self, tenant, agent, tool, args):
        self.calls += 1
        return self._d


def _handler_factory(box):
    def handler(request):
        box.append(request.tool_call["name"])
        return f"ran:{request.tool_call['name']}"
    return handler


def test_observe_runs_via_handler_and_audits():
    guard = Guard(mode="observe", agent="lg")
    wrap = lg.kiff_wrap_tool_call(guard)
    box = []
    out = wrap(_Req("refund_order", {"order_id": "o1", "amount_cents": 5}), _handler_factory(box))
    assert out == "ran:refund_order"
    assert box == ["refund_order"]                       # tool ran via handler
    assert guard.receipts[-1].state == "observed"
    assert guard.catalog.tools["refund_order"] == {"order_id", "amount_cents"}


def test_enforce_allowed_runs_via_handler():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="lg")
    wrap = lg.kiff_wrap_tool_call(guard)
    box = []
    out = wrap(_Req("read_file", {"path": "x"}), _handler_factory(box))
    assert out == "ran:read_file"
    assert box == ["read_file"]
    assert stub.calls == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is True


def test_enforce_withheld_returns_block_message_without_running(monkeypatch):
    # Monkeypatch the lazy ToolMessage builder so the test needs no langchain.
    captured = {}

    def fake_block(tool_name, tool_call_id, decision):
        captured["tool"] = tool_name
        captured["id"] = tool_call_id
        captured["outcome"] = decision.outcome
        return {"__toolmessage__": True, "content": decision.reason, "tool_call_id": tool_call_id}

    monkeypatch.setattr(lg, "_block_message", fake_block)

    stub = _StubClient(outcome="blocked", reason="delete_account is blocked by policy")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="lg")
    wrap = lg.kiff_wrap_tool_call(guard)
    box = []
    out = wrap(_Req("delete_account", {"account_id": "a9"}, call_id="tc9"), _handler_factory(box))

    assert box == []                                     # tool never ran
    assert out["__toolmessage__"] is True
    assert captured["tool"] == "delete_account"
    assert captured["id"] == "tc9"
    assert captured["outcome"] == "blocked"
    # a governed, not-executed receipt was recorded
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is False


def test_handles_missing_tool_call_fields():
    # A malformed request (no args) should not crash; observe records it.
    guard = Guard(mode="observe", agent="lg")
    wrap = lg.kiff_wrap_tool_call(guard)

    class _Bare:
        tool_call = {"name": "noargs"}  # no "args", no "id"

    out = wrap(_Bare(), lambda req: "ok")
    assert out == "ok"
    assert guard.catalog.tools["noargs"] == set()


if __name__ == "__main__":
    # Minimal monkeypatch shim for dependency-free run (no pytest).
    class _MP:
        def setattr(self, obj, name, val):
            setattr(obj, name, val)

    fns = []
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            fns.append((k, v))
    for name, fn in fns:
        if "monkeypatch" in fn.__code__.co_varnames:
            fn(_MP())
        else:
            fn()
        print(f"ok  {name}")
    print(f"\n{len(fns)} passed")
