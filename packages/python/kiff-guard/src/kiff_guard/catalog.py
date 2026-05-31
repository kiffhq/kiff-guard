"""Catalog — the action surface derived from observed agent traffic.

The honest half of instrument-first authoring: tool names and argument
shapes can be *derived* from real calls. Risk level, the state machine,
and approval policy cannot — they are human judgment, left as TODO in the
draft (see draft.py). We never infer what we cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass
class Catalog:
    """One entry per distinct tool, accumulating the argument keys seen
    across calls, plus the set of agents observed. Shared across every
    guard on one tenant: one tower, one learned surface."""

    tools: Dict[str, Set[str]] = field(default_factory=dict)
    agents: Set[str] = field(default_factory=set)

    def record(self, agent: str, tool: str, args: Dict[str, Any]) -> None:
        self.agents.add(agent)
        self.tools.setdefault(tool, set()).update(args.keys())
