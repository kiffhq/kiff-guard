"""conformance — the contract every guard adapter must satisfy.

This is the durability mechanism for the (soon public, multi-language)
guard SDK: a `storetest`-style suite that pins the invariants an adapter
must uphold, so a community-contributed adapter can be accepted by
passing it rather than by a line-by-line audit, and CI catches drift when
a framework changes upstream.

An adapter is conformant if, driven through its own seam, it upholds:

  OBSERVE (decide-independent, #244):
    O1  observe mode never calls the client (decide_calls == 0)
    O2  observe always lets the tool run (never withholds)
    O3  observe records exactly ONE receipt per call, state="observed"
    O4  observe learns the catalog (tool name + arg keys)
    O5  observe works with no client and no tenant

  ENFORCE (vote or middleware shape):
    E1  allowed -> tool runs; exactly ONE governed receipt, executed=True
    E2  withheld -> tool does NOT run; exactly ONE governed receipt,
        executed=False  (the #239 one-receipt rule)
    E3  the client's roles are never asserted by the guard (trust boundary)
    E4  an UNKNOWN outcome fails SAFE — withholds (does NOT run), one
        governed executed=False receipt (RFC 017; old SDK + new cloud
        outcome must never fail open)
    E5  a guard/transport ERROR (decide raises) fails SAFE — the tool
        does NOT run (fail-closed is the default; fail-open is opt-in)

To run the suite against an adapter, provide an `AdapterDriver`: a small
shim that knows how to invoke ONE tool call through the adapter and report
whether the underlying tool ran. The driver isolates the only
framework-specific part; the invariants live here, once.

Usage (in an adapter's test file):

    from kiff_guard.conformance import AdapterDriver, run_conformance

    def drive(guard, tool, args, *, will_run):
        # invoke the adapter's seam for one call; return whether the
        # tool's body executed.
        ...
    run_conformance(AdapterDriver(name="agno", drive=drive))

`run_conformance` raises AssertionError on the first violated invariant,
with a message naming the adapter + the invariant id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .catalog import Catalog
from .decision import Decision, Receipt
from .guard import Guard


# --- a recording fake client the suite drives adapters with ----------------

class ConformanceClient:
    """A decide() stub the suite controls. Counts calls (to prove observe
    never decides) and returns a scripted outcome. Records the args it was
    given so E3 can assert no authority/roles field is injected."""

    def __init__(self, outcome: str = "allowed", reason: str = "", proposal_id: str = "p_conf",
                 raises: bool = False):
        self.calls = 0
        self.seen_args: List[Dict[str, Any]] = []
        self._d = Decision(outcome=outcome, reason=reason, proposal_id=proposal_id)
        self._raises = raises

    def decide(self, tenant: str, agent: str, tool: str, args: Dict[str, Any]) -> Decision:
        self.calls += 1
        self.seen_args.append(dict(args) if isinstance(args, dict) else {})
        if self._raises:
            raise RuntimeError("decide transport error (conformance E5)")
        return self._d


@dataclass
class AdapterDriver:
    """Wraps the one framework-specific operation the suite needs:
    invoke the adapter for a single tool call.

    name  — adapter name, for assertion messages.
    drive — callable(guard, tool, args, *, will_run) -> bool.
            Invokes the adapter's seam once and returns True iff the
            underlying tool body executed. `will_run` tells the driver
            what the scripted decision is (so it can prepare a tool whose
            execution it can detect); the driver must NOT use it to decide
            anything itself — it only runs the adapter and reports reality.
    """

    name: str
    drive: Callable[..., bool]


def _fresh(client=None, mode="observe", agent="conf"):
    return Guard(client=client, tenant="t" if client else "", agent=agent, mode=mode)


def run_conformance(driver: AdapterDriver) -> None:
    """Run every invariant against `driver`. Raises AssertionError naming
    the adapter + invariant id on the first failure."""
    n = driver.name

    # --- OBSERVE ----------------------------------------------------------
    # O5 + O1: observe works with NO client, and never decides.
    guard = _fresh(client=None, mode="observe")
    ran = driver.drive(guard, "send_email", {"to": "x", "body": "y"}, will_run=True)
    assert ran is True, f"[{n}] O2: observe must let the tool run"
    assert len(guard.receipts) == 1, f"[{n}] O3: observe must record exactly one receipt"
    assert guard.receipts[0].state == "observed", f"[{n}] O3: observe receipt state must be 'observed'"
    assert guard.catalog.tools.get("send_email") == {"to", "body"}, f"[{n}] O4: observe must learn the catalog"

    # O1 explicitly: even with a client present, observe must not call it.
    spy = ConformanceClient(outcome="blocked")
    guard = _fresh(client=spy, mode="observe")
    driver.drive(guard, "refund", {"order_id": "o1"}, will_run=True)
    assert spy.calls == 0, f"[{n}] O1: observe must NOT call the client"

    # --- ENFORCE: allowed -------------------------------------------------
    client = ConformanceClient(outcome="allowed")
    guard = _fresh(client=client, mode="enforce")
    ran = driver.drive(guard, "refund", {"order_id": "o1", "amount_cents": 5}, will_run=True)
    assert ran is True, f"[{n}] E1: allowed must run the tool"
    gov = [r for r in guard.receipts if r.state == "governed"]
    assert len(gov) == 1, f"[{n}] E1: allowed must record exactly one governed receipt (got {len(gov)})"
    assert gov[0].executed is True, f"[{n}] E1: allowed receipt must be executed=True"
    assert client.calls == 1, f"[{n}] E1: enforce must call the client exactly once"

    # --- ENFORCE: withheld ------------------------------------------------
    client = ConformanceClient(outcome="blocked", reason="blocked by policy")
    guard = _fresh(client=client, mode="enforce")
    ran = driver.drive(guard, "delete_account", {"account_id": "a9"}, will_run=False)
    assert ran is False, f"[{n}] E2: withheld must NOT run the tool"
    gov = [r for r in guard.receipts if r.state == "governed"]
    assert len(gov) == 1, f"[{n}] E2: withheld must record exactly one governed receipt (got {len(gov)})"
    assert gov[0].executed is False, f"[{n}] E2: withheld receipt must be executed=False"

    # --- E3: roles are never asserted by the guard ------------------------
    client = ConformanceClient(outcome="allowed")
    guard = _fresh(client=client, mode="enforce")
    driver.drive(guard, "refund", {"order_id": "o1", "actor_roles": ["admin"]}, will_run=True)
    for seen in client.seen_args:
        assert "roles" not in seen, f"[{n}] E3: guard must never inject a top-level 'roles' field"

    # --- E4: an UNKNOWN outcome must fail SAFE (withhold), never run ------
    # The cloud may add outcomes the SDK has never heard of (e.g.
    # "quarantined", "rate_limited"). An old adapter must withhold, not
    # run an ungoverned tool. (RFC 017.)
    client = ConformanceClient(outcome="quarantined", reason="unknown future outcome")
    guard = _fresh(client=client, mode="enforce")
    ran = driver.drive(guard, "delete_account", {"account_id": "a9"}, will_run=False)
    assert ran is False, f"[{n}] E4: unknown outcome must NOT run the tool (fail-safe)"
    gov = [r for r in guard.receipts if r.state == "governed"]
    assert len(gov) == 1, f"[{n}] E4: unknown outcome must record exactly one governed receipt"
    assert gov[0].executed is False, f"[{n}] E4: unknown-outcome receipt must be executed=False"

    # --- E5: a guard/transport ERROR must fail SAFE (withhold), never run -
    # If decide() itself raises (transport down, timeout, a bug), enforce
    # must NOT run the tool. The adapter may raise Hold, withhold, or let
    # the error propagate — the invariant is only that the tool body does
    # not execute. (E1/E2 already establish that adapters decide BEFORE
    # running, so a raised decide() means the tool cannot have run; a drive
    # that raises is therefore a "did not run" outcome.) fail-open is an
    # opt-in per-adapter setting and is not exercised here — the default,
    # which conformance pins, is fail-closed.
    client = ConformanceClient(raises=True)
    guard = _fresh(client=client, mode="enforce")
    try:
        ran = driver.drive(guard, "delete_account", {"account_id": "a9"}, will_run=False)
    except Exception:
        ran = False  # adapter raised on the guard error -> tool did not run
    assert ran is False, f"[{n}] E5: a guard/transport error must NOT run the tool (fail-closed)"
