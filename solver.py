"""Pipeline: AC-3 -> backtracking (MRV, LCV, forward checking) -> soft-penalty local search.
If backtracking finds nothing, Min-Conflicts repairs a greedy assignment instead."""

import random
import sys

from backtracking import ac3, backtracking_search_heuristics
from csp_heuristics import TimetableHeuristics
from localsearch import min_conflicts
from soft_search import SoftSearch

AC3_MAX_WORK = 3_000_000
SOFT_TIME = 10.0


def _conflicts(csp, assignment):
    return sum(csp.nconflicts(v, val, assignment) for v, val in assignment.items()) // 2


def _greedy_initial(csp, rng, sample=150):
    cur = {}
    for v in sorted(csp.variables, key=lambda v: len(csp.domains[v])):
        dom = csp.domains[v]
        pool = dom if len(dom) <= sample else rng.sample(dom, sample)
        cur[v] = min((csp.nconflicts(v, x, cur), rng.random(), x) for x in pool)[2]
    return cur


def solve(problem, seed=42):
    rng = random.Random(seed)
    random.seed(seed)
    sys.setrecursionlimit(max(10000, 4 * len(problem.courses) + 1000))

    csp = problem.build_csp()

    work = sum(len(csp.domains[a]) * len(csp.domains[b]) for a in csp.variables for b in csp.neighbors[a])
    if work <= AC3_MAX_WORK:
        ac3(csp)
    base = {v: list(d) for v, d in csp.domains.items()}

    h = TimetableHeuristics(problem)
    assignment = backtracking_search_heuristics(
        csp, select_unassigned_variable=h.select_variable,
        order_domain_values=h.order_values, inference=h.forward_checking)
    csp.domains = {v: list(d) for v, d in base.items()}

    if assignment is None:
        best, best_conf = None, None
        for _ in range(5):
            cand = min_conflicts(csp, max_steps=1500, initial_assignment=_greedy_initial(csp, rng))
            conf = _conflicts(csp, cand)
            if best is None or conf < best_conf:
                best, best_conf = cand, conf
            if conf == 0:
                break
        return dict(best)

    return SoftSearch(problem, csp, rng).run(dict(assignment), time_limit=SOFT_TIME)
