"""Prioritisation under a daily outreach budget (spec section 7.6).

    risk_only   : priority = severity_weight × p_dropoff
    uplift      : priority = severity_weight × uplift              (default "WASL")
    uplift_fair : uplift, subject to a fairness floor per language group

Fairness-constrained allocation (greedy, documented):
  1. need_share[g] = share of open high/urgent loops that belong to language group g.
  2. Each group gets a floor of floor(budget × need_share[g] × (1 − ε)) contacts.
  3. Fill every group's floor with that group's highest-priority loops.
  4. Fill the remaining budget with the highest-priority loops overall.
Greedy is optimal for this problem: with per-group floors and a single linear objective,
taking each group's top items for its floor and then the global top items maximises
total priority among all allocations that satisfy the floors.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

# ILLUSTRATIVE: mild weights so the ranking is driven by uplift, with severity as a tie-breaker
# that still lifts urgent results. Configure with a clinical lead.
SEVERITY_WEIGHT = {"routine": 1.0, "high": 1.25, "urgent": 1.5}
POLICIES = ("risk_only", "uplift", "uplift_fair")


@dataclass
class Candidate:
    key: str
    group: str
    severity: str
    p_dropoff: float
    uplift: float

    def priority(self, policy: str) -> float:
        w = SEVERITY_WEIGHT.get(self.severity, 1.0)
        if policy == "risk_only":
            return w * self.p_dropoff
        return w * self.uplift


def need_shares(cands: list[Candidate]) -> dict[str, float]:
    high = [c for c in cands if c.severity in ("high", "urgent")] or cands
    counts: dict[str, int] = defaultdict(int)
    for c in high:
        counts[c.group] += 1
    total = sum(counts.values()) or 1
    return {g: n / total for g, n in counts.items()}


def allocate(cands: list[Candidate], budget: int, policy: str = "uplift", epsilon: float = 0.1) -> list[Candidate]:
    """Return the selected candidates, in priority order."""
    ranked = sorted(cands, key=lambda c: (-c.priority(policy), c.key))
    if policy != "uplift_fair":
        return ranked[:budget]
    shares = need_shares(cands)
    floors = {g: math.floor(budget * s * (1 - epsilon)) for g, s in shares.items()}
    chosen: list[Candidate] = []
    chosen_keys: set[str] = set()
    by_group: dict[str, list[Candidate]] = defaultdict(list)
    for c in ranked:
        by_group[c.group].append(c)
    for g, floor in floors.items():
        for c in by_group.get(g, [])[:floor]:
            chosen.append(c)
            chosen_keys.add(c.key)
    for c in ranked:
        if len(chosen) >= budget:
            break
        if c.key not in chosen_keys:
            chosen.append(c)
            chosen_keys.add(c.key)
    return sorted(chosen[:budget], key=lambda c: (-c.priority("uplift"), c.key))


def floors_for(cands: list[Candidate], budget: int, epsilon: float = 0.1) -> dict[str, int]:
    return {g: math.floor(budget * s * (1 - epsilon)) for g, s in need_shares(cands).items()}
