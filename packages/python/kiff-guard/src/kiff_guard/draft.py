"""draft — turn an observed Catalog into a starter KIFF domain.

This is the instrument-first authoring payoff: the same integration the
developer added for runtime governance also drafts the domain Studio /
the MCP authoring path were trying to produce from a blank page.

Honesty boundary:
  - DERIVED from traffic: the action catalog + parameter shapes.
  - NOT derivable from tool signatures: the state machine, per-action
    risk, approval policy. Left as explicit TODO for a human / a Template.

Two outputs, switched on credential presence (the fork resolved on #239):
  - export_yaml() — for credential-less / framework-only adopters: emit
    the draft for the user to paste.
  - (save_draft to the cloud draft store, #220, lands with the cloud
    client once the SDK is wired to a tenant — see TODO below.)
"""

from __future__ import annotations

from typing import List

from .catalog import Catalog


def export_yaml(domain_name: str, catalog: Catalog) -> str:
    """Render the observed catalog as a starter domain YAML string."""
    lines: List[str] = []
    lines.append(f"# KIFF domain draft for '{domain_name}'")
    lines.append("# Auto-derived from observed agent traffic (instrument-first).")
    lines.append("# Catalog + parameter shapes are derived; risk, states, and")
    lines.append("# approval policy are TODO — the human's judgment goes here.")
    lines.append("")
    lines.append(f"domain: {domain_name}")
    lines.append("")
    lines.append("# Agents observed acting in this tenant:")
    for agent in sorted(catalog.agents):
        lines.append(f"#   - {agent}")
    lines.append("")
    lines.append("# TODO(human): define the entity state machine. Derived")
    lines.append("# traffic cannot tell us the lifecycle (e.g. CREATED ->")
    lines.append("# PAID -> REFUNDED). Studio or a template seeds this.")
    lines.append("states: []   # TODO")
    lines.append("")
    lines.append("actions:")
    for tool in sorted(catalog.tools):
        params = sorted(catalog.tools[tool])
        lines.append(f"  - name: {tool}")
        lines.append("    parameters:")
        for p in params:
            lines.append(f"      - {p}")
        lines.append("    risk: low            # TODO(human): low | medium | high")
        lines.append("    requires_approval: false   # TODO(human)")
        lines.append("    allowed_states: []   # TODO(human): which states allow this")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# TODO(#239): save_draft(client, catalog) -> writes the derived draft to
# the cloud draft store (PUT /v1/me/domain/draft, #220) when a credential
# is present, so it shows up in Studio automatically. export_yaml is the
# credential-less fallback. Lands when the cloud client gains the draft
# write surface.
