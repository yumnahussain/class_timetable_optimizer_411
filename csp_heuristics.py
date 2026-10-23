"""Faster MRV / LCV / forward-checking callables with the same signatures as backtracking.py."""

from collections import defaultdict


class TimetableHeuristics:
    def __init__(self, problem):
        self.ovset = problem.ovset
        self.unary = problem.unary

    def select_variable(self, assignment, csp):
        """MRV with the degree heuristic as tie-breaker."""
        best, best_key = None, None
        for v in csp.variables:
            if v in assignment:
                continue
            degree = sum(1 for n in csp.neighbors[v] if n not in assignment)
            key = (len(csp.domains[v]), -degree)
            if best_key is None or key < best_key:
                best, best_key = v, key
        return best

    def order_values(self, var, assignment, csp):
        """LCV: fewest values removed from unassigned neighbours; ties by soft penalty."""
        tied_v = csp.tied[var]
        by_slot = defaultdict(int)
        by_room_slot = defaultdict(int)
        for n in csp.neighbors[var]:
            if n in assignment:
                continue
            if n in tied_v:
                for s2, _ in csp.domains[n]:
                    by_slot[s2] += 1
            else:
                for s2, r2 in csp.domains[n]:
                    by_room_slot[(r2, s2)] += 1
        unary = self.unary[var]

        def removed(val):
            s, r = val
            return sum(by_slot.get(s2, 0) + by_room_slot.get((r, s2), 0) for s2 in self.ovset[s])

        return sorted(csp.domains[var], key=lambda v: (removed(v), unary[v]))

    def forward_checking(self, csp, var, value, assignment, removals=None):
        s, r = value
        ovs = self.ovset[s]
        tied_v = csp.tied[var]
        for n in csp.neighbors[var]:
            if n in assignment:
                continue
            dom = csp.domains[n]
            if n in tied_v:
                bad = [x for x in dom if x[0] in ovs]
            else:
                bad = [x for x in dom if x[1] == r and x[0] in ovs]
            if bad:
                removals.extend((n, x) for x in bad)
                bad_set = set(bad)
                csp.domains[n] = [x for x in dom if x not in bad_set]
                if not csp.domains[n]:
                    return False
        return True
