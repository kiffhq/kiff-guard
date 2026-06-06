"""draft export_yaml — schema conformance.

The derived YAML must match the KIFF domain schema (the shape the cloud
validator and the framework's domain builder accept), so an instrument-first
draft can be validated and refined, not reshaped first.

These tests parse the rendered YAML and assert the field names, types, and
value domains line up with that schema:

  top level:  domain, entity, events, states, transitions, actions, permissions
  action:     name, allowed_states, required_parameters, required_permissions,
              risk (low|medium|high), approval (never|required)
"""

from __future__ import annotations

import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kiff_guard import Guard, export_yaml  # noqa: E402
from kiff_guard.catalog import Catalog  # noqa: E402


def _catalog(*calls):
    cat = Catalog()
    for agent, tool, args in calls:
        cat.record(agent, tool, args)
    return cat


def _render(*calls, name="acme"):
    return yaml.safe_load(export_yaml(name, _catalog(*calls)))


def test_top_level_keys_match_schema():
    doc = _render(("support", "refund_order", {"order_id": "o1", "amount_cents": 1}))
    for key in ("domain", "entity", "events", "states", "transitions", "actions", "permissions"):
        assert key in doc, f"missing top-level key: {key}"


def test_top_level_types_match_schema():
    doc = _render(("support", "refund_order", {"order_id": "o1"}))
    assert isinstance(doc["domain"], str)
    assert isinstance(doc["entity"], str) and doc["entity"]
    assert isinstance(doc["events"], list)
    assert isinstance(doc["states"], list)
    assert isinstance(doc["transitions"], list)
    assert isinstance(doc["actions"], list)
    assert isinstance(doc["permissions"], dict) and "roles" in doc["permissions"]


def test_action_uses_schema_field_names():
    doc = _render(("support", "refund_order", {"order_id": "o1", "amount_cents": 1}))
    action = next(a for a in doc["actions"] if a["name"] == "refund_order")
    # The cloud schema (domain/spec.go) uses these exact keys.
    for key in ("name", "allowed_states", "required_parameters", "required_permissions", "risk", "approval"):
        assert key in action, f"action missing schema key: {key}"
    # NOT the old hand-rolled names.
    assert "parameters" not in action, "must use required_parameters, not parameters"
    assert "requires_approval" not in action, "must use approval (string), not requires_approval (bool)"


def test_action_value_domains():
    doc = _render(("support", "refund_order", {"order_id": "o1", "amount_cents": 1}))
    action = doc["actions"][0]
    assert action["risk"] in ("low", "medium", "high")
    assert action["approval"] in ("never", "required")
    assert isinstance(action["approval"], str)  # not a bool
    assert isinstance(action["required_parameters"], list)


def test_required_parameters_carry_observed_args():
    doc = _render(("support", "refund_order", {"order_id": "o1", "amount_cents": 1}))
    action = next(a for a in doc["actions"] if a["name"] == "refund_order")
    assert set(action["required_parameters"]) == {"order_id", "amount_cents"}


def test_empty_catalog_still_schema_valid():
    doc = _render()  # no observed calls
    assert doc["actions"] == []
    for key in ("domain", "entity", "events", "states", "transitions", "permissions"):
        assert key in doc


def test_observe_to_draft_end_to_end():
    guard = Guard(mode="observe", agent="support")
    guard.observe("issue_refund", {"order_id": "o1"})
    doc = yaml.safe_load(export_yaml("refunds", guard.catalog))
    assert doc["domain"] == "refunds"
    assert any(a["name"] == "issue_refund" for a in doc["actions"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
