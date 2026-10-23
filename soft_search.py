"""
soft_search.py

Min-Conflicts-style local search that minimises the *soft* penalty (S1-S5 and the
room-preference terms) while never leaving the hard-feasible region.

localsearch.min_conflicts minimises the NUMBER OF HARD CONFLICTS and stops at 0,
so it cannot rank two feasible timetables.  This module keeps the same idea
(pick a "conflicted" variable, move it to its best value, random tie-breaking,
a little noise) but:

  * "conflicted" = a course contributing > 0 soft penalty,
  * a candidate value must be hard-feasible w.r.t. the current assignment
    (H1/H3/H5 checked via busy tables; H2/H4 are already enforced by the domain),
  * cost changes are computed incrementally (the course's unary penalty plus
    the cohort / instructor groups it belongs to),
  * the best assignment seen is returned.
"""

import random
import time
from collections import defaultdict
from typing import Dict, Tuple

Value = Tuple[int, int]
EPS = 1e-9


class SoftSearch:
    def __init__(self, problem, csp, rng: random.Random):
        self.P = problem
        self.csp = csp
        self.rng = rng
        self.groups = problem.groups()                    # [(is_cohort, members)]
        self.var_groups = defaultdict(list)
        for gi, (_, members) in enumerate(self.groups):
            for m in members:
                self.var_groups[m].append(gi)

    # ---------------------------------------------------------------- helpers
    def _group_value(self, gi, cur):
        is_c, members = self.groups[gi]
        return self.P.group_cost([self.P.session(cur[m]) for m in members], is_c)

    def _feasible(self, v, cur):
        """All domain values of v that clash with nobody in `cur` (v excluded)."""
        P = self.P
        tied = P.tied[v]
        person_busy = set()
        room_busy = defaultdict(set)
        for u, (s2, r2) in cur.items():
            if u == v:
                continue
            ovs = P.ovset[s2]
            room_busy[r2] |= ovs
            if u in tied:
                person_busy |= ovs
        return [(s, r) for (s, r) in self.csp.initial_domains[v]
                if s not in person_busy and s not in room_busy.get(r, ())]

    # -------------------------------------------------------------------- run
    def run(self, assignment: Dict[str, Value], time_limit: float = 10.0,
            max_steps: int = 200000, patience: int = 2500, noise: float = 0.03):
        P, rng = self.P, self.rng
        cur = dict(assignment)
        cost = P.soft_cost(cur)
        start_cost = cost
        best, best_cost = dict(cur), cost
        gcost = {gi: self._group_value(gi, cur) for gi in range(len(self.groups))}
        variables = list(self.csp.variables)
        deadline = time.time() + time_limit
        steps = stale = moves = 0

        while steps < max_steps and stale < patience and time.time() < deadline:
            steps += 1
            # --- pick a "conflicted" variable (positive soft contribution)
            cand = [v for v in variables
                    if P.unary[v][cur[v]] + sum(gcost[g] for g in self.var_groups[v]) > EPS]
            if not cand:
                break                                      # zero penalty: optimal
            v = rng.choice(cand)
            old = cur[v]
            gids = self.var_groups[v]
            old_total = P.unary[v][old] + sum(gcost[g] for g in gids)

            feasible = self._feasible(v, cur)
            others = [(g, self.groups[g][0],
                       [P.session(cur[u]) for u in self.groups[g][1] if u != v]) for g in gids]
            memo = {}
            un = P.unary[v]

            def group_part(val):
                s, r = val
                key = (s, P.room_building[r])
                hit = memo.get(key)
                if hit is None:
                    sess = (P.slot_day[s], P.slot_start[s], P.slot_end[s], P.room_building[r])
                    parts = [P.group_cost(oth + [sess], is_c) for _, is_c, oth in others]
                    hit = memo[key] = (sum(parts), parts)
                return hit

            best_val, best_score, ties = None, float("inf"), []
            for val in feasible:
                sc = un[val] + group_part(val)[0]
                if sc < best_score - EPS:
                    best_score, ties = sc, [val]
                elif abs(sc - best_score) <= EPS:
                    ties.append(val)
            if ties:
                best_val = rng.choice(ties)

            move = None
            if best_val is not None and best_score < old_total - EPS:
                move = best_val                            # strict improvement
            elif best_val is not None and abs(best_score - old_total) <= EPS \
                    and best_val != old and rng.random() < 0.3:
                move = best_val                            # sideways (plateau) move
            elif feasible and rng.random() < noise:
                move = rng.choice(feasible)                # random walk

            if move is None or move == old:
                stale += 1
                continue

            _, parts = group_part(move)
            new_total = un[move] + sum(parts)
            cost += new_total - old_total
            cur[v] = move
            for g, p in zip(gids, parts):
                gcost[g] = p
            moves += 1
            if cost < best_cost - EPS:
                best, best_cost, stale = dict(cur), cost, 0
            else:
                stale += 1

        # drift guard: recompute from scratch
        check = P.soft_cost(best)
        stats = {"steps": steps, "moves": moves, "start_cost": start_cost,
                 "end_cost": check, "tracked_cost": best_cost}
        return best, stats
