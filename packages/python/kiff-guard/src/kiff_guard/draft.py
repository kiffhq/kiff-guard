"""draft — turn an observed Catalog into a starter KIFF domain.

This is the instrument-first authoring payoff: the same integration the
developer added for runtime governance also drafts the domain that the
authoring tools were trying to produce from a blank page.

Honesty boundary:
  - DERIVED from traffic: the action catalog + parameter shapes.
  - NOT derivable from tool signatures: the entity, the state machine
    (states + transitions), per-action risk, and approval policy. These
    are emitted as schema-valid placeholders for a human / a template to
    fill in.

The rendered YAML matches the KIFF domain schema (the same shape the cloud
validator and the framework's domain builder accept), so a draft can be
pasted into a domain file, validated, and refined — not reshaped first.
"""

from __future__ import annotations

from typing import List

from .catalog import Catalog


def export_yaml(domain_name: str, catalog: Catalog) -> str:
    """Render the observed catalog as a starter domain YAML string.

    The output is schema-shaped: top-level ``domain`` / ``entity`` /
    ``events`` / ``states`` / ``transitions`` / ``actions`` / ``permissions``,
    and each action carries ``allowed_states`` / ``required_parameters`` /
    ``required_permissions`` / ``risk`` / ``approval``. Fields that cannot be
    derived from traffic are emitted as conservative, valid defaults with a
    ``TODO(human)`` marker (empty lists, ``risk: low``, ``approval: never``).
    """
    lines: List[str] = []
    lines.append(f"# KIFF domain draft for '{domain_name}'")
    lines.append("# Auto-derived from observed agent traffic (instrument-first).")
    lines.append("# The action catalog + parameter shapes are derived; the entity,")
    lines.append("# state machine, risk, and approval policy are TODO(human).")
    lines.append("")
    lines.append(f"domain: {domain_name}")
    lines.append("entity: Entity   # TODO(human): the entity type these actions govern")
    lines.append("")
    if catalog.agents:
        lines.append("# Agents observed acting in this tenant:")
        for agent in sorted(catalog.agents):
            lines.append(f"#   - {agent}")
        lines.append("")
    lines.append("# TODO(human): the lifecycle events that drive state transitions.")
    lines.append("events: []")
    lines.append("")
    lines.append("# TODO(human): the entity states. Derived traffic cannot tell us")
    lines.append("# the lifecycle (e.g. CREATED -> PAID -> REFUNDED).")
    lines.append("states: []")
    lines.append("")
    lines.append("# TODO(human): event -> state transitions (on / from / to).")
    lines.append("transitions: []")
    lines.append("")
    if catalog.tools:
        lines.append("actions:")
        for tool in sorted(catalog.tools):
            params = sorted(catalog.tools[tool])
            params_yaml = "[" + ", ".join(params) + "]" if params else "[]"
            lines.append(f"  - name: {tool}")
            lines.append("    allowed_states: []          # TODO(human): which states allow this")
            lines.append(f"    required_parameters: {params_yaml}")
            lines.append("    required_permissions: []    # TODO(human)")
            lines.append("    risk: low                   # TODO(human): low | medium | high")
            lines.append("    approval: never             # TODO(human): never | required")
            lines.append("")
    else:
        lines.append("actions: []")
        lines.append("")
    lines.append("permissions:")
    lines.append("  roles:")
    lines.append("    admin: []   # TODO(human): map roles to proposing/approving permissions")
    return "\n".join(lines).rstrip() + "\n"


# save_draft(client, catalog) — write the derived draft to the cloud draft
# store (PUT /v1/me/domain/draft) when a credential is present, so it shows up
# in the authoring UI automatically — lands when the client gains the draft
# write surface. export_yaml is the credential-less fallback.
