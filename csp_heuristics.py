"""
csp_heuristics.py

Timetable-specific, drop-in replacements for the generic `mrv`, `lcv` and
`forward_checking` in backtracking.py. They keep the exact same call signatures
so they plug straight into `backtracking_search_heuristics(...)`.

Why replace them?  The generic versions re-test every (value, neighbour-value)
pair through the constraint callback.  Here a domain is ~50 slots x ~15 rooms and
almost every pair of courses is a neighbour (they may compete for a room), so
that is billions of callbacks.  The versions below compute the *same* quantities
with set / counter look-ups:

  select_variable : MRV, degree heuristic as tie-breaker.  Because forward
                    checking keeps every domain exactly equal to its set of legal
                    values, len(domain) IS the MRV count.
  order_values    : LCV - number of neighbour values each candidate would remove,
                    counted in O(domain) with counters instead of O(domain^2).
  forward_checking: removes (in one pass per neighbour) every value that clashes
                    in time with the assigned value on the same room or the same
                    instructor / cohort; wipe-out => return False.
"""

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


class SearchTimeout(Exception):
    pass


class TimetableHeuristics:
    def __init__(self, problem, deadline: float, rng, randomize: bool = False):
        self.P = problem
        self.deadline = deadline
        self.rng = rng
        self.randomize = randomize
        self.ovset = problem.ovset

    def _check_time(self):
        if time.time() > self.deadline:
            raise SearchTimeout()

    # ---- MRV + Degree ----------------------------------------------------
    def select_variable(self, assignment: Dict[str, Any], csp) -> Optional[str]:
        self._check_time()
        best, best_key = None, None
        for v in csp.variables:
            if v in assignment:
                continue
            degree = sum(1 for n in csp.neighbors[v] if n not in assignment)
            key = (len(csp.domains[v]), -degree, self.rng.random() if self.randomize else 0.0)
            if best_key is None or key < best_key:
                best, best_key = v, key
        return best

    # ---- LCV -------------------------------------------------------------
    def order_values(self, var: str, assignment: Dict[str, Any], csp) -> List[Any]:
        tied_v = csp.tied[var]
        agg_slot: Dict[int, int] = defaultdict(int)             # tied neighbours: any room conflicts
        agg_room_slot: Dict[Tuple[int, int], int] = defaultdict(int)  # others: same room only
        for n in csp.neighbors[var]:
            if n in assignment:
                continue
            if n in tied_v:
                for s2, _ in csp.domains[n]:
                    agg_slot[s2] += 1
            else:
                for s2, r2 in csp.domains[n]:
                    agg_room_slot[(r2, s2)] += 1
        unary = self.P.unary[var]
        ovset = self.ovset

        def score(val):
            s, r = val
            t = 0
            for s2 in ovset[s]:
                t += agg_slot.get(s2, 0) + agg_room_slot.get((r, s2), 0)
            return t

        # primary: least constraining; tie-break: lowest soft penalty
        keyed = [(score(v), unary[v], self.rng.random() if self.randomize else 0.0, v)
                 for v in csp.domains[var]]
        keyed.sort(key=lambda x: x[:3])
        return [k[3] for k in keyed]

    # ---- Forward checking ------------------------------------------------
    def forward_checking(self, csp, var: str, value, assignment: Dict[str, Any],
                         removals: Optional[List[Tuple[str, Any]]] = None) -> bool:
        s, r = value
        ovs = self.ovset[s]
        tied_v = csp.tied[var]
        for n in csp.neighbors[var]:
            if n in assignment:
                continue
            dom = csp.domains[n]
            keep = []
            if n in tied_v:
                for x in dom:
                    if x[0] in ovs:
                        removals.append((n, x))
                    else:
                        keep.append(x)
            else:
                for x in dom:
                    if x[1] == r and x[0] in ovs:
                        removals.append((n, x))
                    else:
                        keep.append(x)
            if len(keep) != len(dom):
                csp.domains[n] = keep
                if not keep:
                    return False
        return True
