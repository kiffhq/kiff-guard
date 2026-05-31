"""OpenAI Agents SDK adapter (tool input guardrail, vote shape).

openai-agents is not installed in CI, so we test the SDK-independent
callback in openai_agents_core with a fake ToolGuardrailFunctionOutput
and a fake guardrail `data` object."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Decision, Guard  # noqa: E402
from kiff_guard.adapters.openai_agents_core import build_guardrail_callback  # noqa: E402


class _FakeOutputs:
    """Stand-in for the SDK's ToolGuardrailFunctionOutput."""

    @staticmethod
    def allow(output_info=None):
        return {"behavior": "allow"}

    @staticmethod
    def reject_content(message, output_info=None):
        return {"behavior": "reject_content", "message": message}


class _Ctx:
    def __init__(self, tool_name, tool_arguments, tool_call_id="tc1"):
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments
        self.tool_call_id = tool_call_id


class _Data:
    """Mimics ToolInputGuardrailData: a .context (ToolContext) + .agent."""

    def __init__(self, tool_name, tool_arguments, tool_call_id="tc1"):
        self.context = _Ctx(tool_name, tool_arguments, tool_call_id)
        self.agent = None


class _StubClient:
    def __init__(self, outcome="allowed", reason="", proposal_id="p1", raises=False):
        self._d = Decision(outcome=outcome, reason=reason, proposal_id=proposal_id)
        self._raises = raises
        self.calls = 0

    def decide(self, tenant, agent, tool, args):
        self.calls += 1
        if self._raises:
            raise RuntimeError("transport down")
        return self._d


def _cb(guard, fail_closed=True):
    return build_guardrail_callback(guard, fail_closed=fail_closed, outputs=_FakeOutputs)


def test_observe_allows_and_audits_parsing_json_args():
    guard = Guard(mode="observe", agent="oai")
    cb = _cb(guard)
    # tool_arguments arrives as a raw JSON string (SDK contract).
    out = cb(_Data("refund_order", '{"order_id": "o1", "amount_cents": 5}'))
    assert out["behavior"] == "allow"
    assert guard.receipts[-1].state == "observed"
    assert guard.catalog.tools["refund_order"] == {"order_id", "amount_cents"}


def test_observe_tolerates_malformed_args():
    guard = Guard(mode="observe", agent="oai")
    cb = _cb(guard)
    out = cb(_Data("noisy", "not json"))
    assert out["behavior"] == "allow"
    assert guard.catalog.tools["noisy"] == set()


def test_enforce_allowed_records_one_receipt_and_allows():
    stub = _StubClient(outcome="allowed")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="oai")
    cb = _cb(guard)
    out = cb(_Data("read_file", '{"path": "x"}'))
    assert out["behavior"] == "allow"
    assert stub.calls == 1
    # exactly one governed receipt, executed=True (no double-receipt; #239)
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is True


def test_enforce_withheld_rejects_content_without_running():
    stub = _StubClient(outcome="blocked", reason="delete_account is blocked by policy")
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="oai")
    cb = _cb(guard)
    out = cb(_Data("delete_account", '{"account_id": "a9"}'))
    assert out["behavior"] == "reject_content"
    assert "blocked" in out["message"]
    # exactly one governed receipt, executed=False
    assert len(guard.receipts) == 1
    assert guard.receipts[-1].state == "governed" and guard.receipts[-1].executed is False


def test_enforce_fail_closed_on_client_error():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="oai")
    cb = _cb(guard, fail_closed=True)
    out = cb(_Data("terminal", '{"command": "ls"}'))
    assert out["behavior"] == "reject_content"
    assert "fail-closed" in out["message"]


def test_enforce_fail_open_when_configured():
    stub = _StubClient(raises=True)
    guard = Guard(client=stub, tenant="t", mode="enforce", agent="oai")
    cb = _cb(guard, fail_closed=False)
    out = cb(_Data("terminal", '{"command": "ls"}'))
    assert out["behavior"] == "allow"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
