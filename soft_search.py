"""Min-Conflicts-style local search that minimises the soft penalty while staying hard-feasible."""

import random
import time
from collections import defaultdict

EPS = 1e-9


class SoftSearch:
    def __init__(self, problem, csp, rng: random.Random):
        self.P = problem
        self.csp = csp
        self.rng = rng
        self.groups = problem.groups()
        self.var_groups = defaultdict(list)
        for gi, (_, members) in enumerate(self.groups):
            for m in members:
                self.var_groups[m].append(gi)

    def _feasible(self, v, cur):
        """Domain values of v that clash with no other course in cur."""
        P = self.P
        tied = P.tied[v]
        person_busy = set()
        room_busy = defaultdict(set)
        for u, (s2, r2) in cur.items():
            if u == v:
                continue
            room_busy[r2] |= P.ovset[s2]
            if u in tied:
                person_busy |= P.ovset[s2]
        return [(s, r) for (s, r) in self.csp.initial_domains[v]
                if s not in person_busy and s not in room_busy.get(r, ())]

    def run(self, assignment, time_limit=10.0, max_steps=200000, patience=2500, noise=0.03):
        P, rng = self.P, self.rng
        cur = dict(assignment)
        cost = P.soft_cost(cur)
        best, best_cost = dict(cur), cost
        gcost = {gi: P.group_cost([P.session(cur[m]) for m in members], is_c)
                 for gi, (is_c, members) in enumerate(self.groups)}
        variables = list(self.csp.variables)
        deadline = time.time() + time_limit
        steps = stale = 0

        while steps < max_steps and stale < patience and time.time() < deadline:
            steps += 1
            cand = [v for v in variables
                    if P.unary[v][cur[v]] + sum(gcost[g] for g in self.var_groups[v]) > EPS]
            if not cand:
                break
            v = rng.choice(cand)
            old = cur[v]
            gids = self.var_groups[v]
            old_total = P.unary[v][old] + sum(gcost[g] for g in gids)
            feasible = self._feasible(v, cur)
            others = [(self.groups[g][0], [P.session(cur[u]) for u in self.groups[g][1] if u != v])
                      for g in gids]
            memo = {}
            un = P.unary[v]

            def group_part(val):
                s, r = val
                key = (s, P.room_building[r])
                if key not in memo:
                    sess = (P.slot_day[s], P.slot_start[s], P.slot_end[s], P.room_building[r])
                    parts = [P.group_cost(oth + [sess], is_c) for is_c, oth in others]
                    memo[key] = (sum(parts), parts)
                return memo[key]

            best_score, ties = float("inf"), []
            for val in feasible:
                sc = un[val] + group_part(val)[0]
                if sc < best_score - EPS:
                    best_score, ties = sc, [val]
                elif abs(sc - best_score) <= EPS:
                    ties.append(val)

            move = None
            if ties and best_score < old_total - EPS:
                move = rng.choice(ties)
            elif ties and abs(best_score - old_total) <= EPS and rng.random() < 0.3:
                move = rng.choice(ties)
            elif feasible and rng.random() < noise:
                move = rng.choice(feasible)

            if move is None or move == old:
                stale += 1
                continue

            _, parts = group_part(move)
            cost += un[move] + sum(parts) - old_total
            cur[v] = move
            for g, p in zip(gids, parts):
                gcost[g] = p
            if cost < best_cost - EPS:
                best, best_cost, stale = dict(cur), cost, 0
            else:
                stale += 1
        return best
