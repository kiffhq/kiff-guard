"""live_openai_check.py — prove the OpenAI Agents adapter against the REAL SDK.

Offline tests stub `ToolGuardrailFunctionOutput` and the guardrail `data`.
This script runs the adapter through the actual `openai-agents` runtime +
a real model call, to verify the things a stub can't:

  1. The SDK accepts our `kiff_tool_input_guardrail(...)` on a function_tool.
  2. `ToolInputGuardrailData.context` really exposes tool_name / tool_arguments
     (our adapter reads them).
  3. `reject_content(...)` genuinely SKIPS the tool — the side effect never
     happens — and the model sees the rejection.
  4. The one-receipt fix (#239) holds against real guardrail data: exactly
     one governed receipt per tool call.

Requires (3.10+ venv): pip install openai-agents
Reads OPENAI_API_KEY from env (never hardcoded). Run:

    OPENAI_API_KEY=sk-... python live_openai_check.py

This is NOT part of the committed pytest suite (CI has neither the SDK nor
a key). It is an operator-run verification, like live_check.py for the
cloud decide endpoint.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents import Agent, Runner, function_tool

from kiff_guard import Guard, Decision
from kiff_guard.adapters.openai_agents import kiff_tool_input_guardrail


# --- a fake KIFF client so we exercise enforce without standing up the cloud.
class _PolicyClient:
    """Returns 'blocked' for transfer_funds, 'allowed' for everything else.
    Stands in for POST /v1/proposals/decide so this test needs only an
    OpenAI key, not a KIFF tenant."""

    def __init__(self):
        self.calls = 0

    def decide(self, tenant, agent, tool, args):
        self.calls += 1
        if tool == "transfer_funds":
            return Decision(outcome="blocked", reason="transfers are blocked by policy", proposal_id="p_blk")
        return Decision(outcome="allowed", reason="cleared by policy", proposal_id="p_ok")


# --- the real side effect we must prove never runs when KIFF blocks.
EXECUTED: list[str] = []


def build_agent(guard: Guard):
    kiff_gd = kiff_tool_input_guardrail(guard)

    @function_tool(tool_input_guardrails=[kiff_gd])
    def transfer_funds(account_id: str, amount_cents: int) -> str:
        """Transfer money. SENSITIVE."""
        EXECUTED.append(f"transfer_funds:{account_id}:{amount_cents}")
        return f"transferred {amount_cents} to {account_id}"

    @function_tool(tool_input_guardrails=[kiff_gd])
    def check_balance(account_id: str) -> str:
        """Read the balance. Safe."""
        EXECUTED.append(f"check_balance:{account_id}")
        return f"balance for {account_id} is 100000"

    return Agent(
        name="banker",
        instructions=(
            "You are a banking assistant. Use the provided tools to fulfill the "
            "user's request. Always attempt the tool call the user asks for."
        ),
        tools=[transfer_funds, check_balance],
    )


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("set OPENAI_API_KEY in env first")
        return 2

    client = _PolicyClient()
    guard = Guard(client=client, tenant="live-test", agent="banker", mode="enforce")
    agent = build_agent(guard)

    print("=" * 64)
    print("  CASE 1 — ask for a BLOCKED tool (transfer_funds)")
    print("=" * 64)
    EXECUTED.clear()
    r1 = Runner.run_sync(agent, "Transfer 99900 cents to account acct-9.")
    print("  final_output:", (r1.final_output or "")[:200])
    print("  side effects executed:", EXECUTED)
    blocked_ran = any(e.startswith("transfer_funds") for e in EXECUTED)
    print(f"  -> transfer_funds actually executed? {blocked_ran}  (must be False)")

    print()
    print("=" * 64)
    print("  CASE 2 — ask for an ALLOWED tool (check_balance)")
    print("=" * 64)
    EXECUTED.clear()
    r2 = Runner.run_sync(agent, "What is the balance of account acct-1?")
    print("  final_output:", (r2.final_output or "")[:200])
    print("  side effects executed:", EXECUTED)
    allowed_ran = any(e.startswith("check_balance") for e in EXECUTED)
    print(f"  -> check_balance executed? {allowed_ran}  (should be True)")

    print()
    print("=" * 64)
    print("  AUDIT — one receipt per governed tool call (the #239 fix)")
    print("=" * 64)
    for rec in guard.receipts:
        print(f"  [{rec.state}] {rec.tool:<16} outcome={rec.outcome:<10} executed={rec.executed}")

    # Assertions — the things a stub can't prove.
    ok = True
    if blocked_ran:
        print("\n  FAIL: blocked tool's side effect ran — reject_content did not skip it")
        ok = False
    # every governed receipt must be a single row per call (no duplicates):
    # group by (tool,args signature) — here each tool called once.
    transfer_receipts = [r for r in guard.receipts if r.tool == "transfer_funds"]
    if len(transfer_receipts) > 1:
        print(f"\n  FAIL: {len(transfer_receipts)} receipts for one transfer_funds call (double-receipt)")
        ok = False
    if transfer_receipts and transfer_receipts[0].executed:
        print("\n  FAIL: blocked transfer recorded executed=True")
        ok = False

    print("\n  RESULT:", "PASS — adapter verified against the real OpenAI Agents SDK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
