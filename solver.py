"""
solver.py

Pipeline
--------
  Phase 0  (optional) AC-3 pre-processing           -> backtracking.ac3
  Phase 1  CSP backtracking: MRV + degree, LCV, forward checking
                                                    -> backtracking.backtracking_search_heuristics
           (a few randomised restarts under a time budget)
  Phase 1b fallback if Phase 1 finds nothing (infeasible / timeout):
           Min-Conflicts repair of hard conflicts   -> localsearch.min_conflicts
  Phase 2  soft-penalty Min-Conflicts local search  -> soft_search.SoftSearch
"""

import random
import sys
import time
from typing import Dict, Optional

from backtracking import ac3, backtracking_search_heuristics
from csp_heuristics import SearchTimeout, TimetableHeuristics
from localsearch import min_conflicts
from soft_search import SoftSearch

AC3_MAX_WORK = 3_000_000     # skip AC-3 if sum(|Di|*|Dj|) over arcs exceeds this


def _count_conflicts(csp, assignment) -> int:
    return sum(csp.nconflicts(v, val, assignment) for v, val in assignment.items()) // 2


def _snapshot(csp):
    return {v: list(d) for v, d in csp.domains.items()}


def _greedy_initial(csp, rng, sample=150):
    """Cheap complete start for min-conflicts: most constrained first, least-conflict value."""
    order = sorted(csp.variables, key=lambda v: len(csp.domains[v]))
    cur = {}
    for v in order:
        dom = csp.domains[v]
        pool = dom if len(dom) <= sample else rng.sample(dom, sample)
        scored = [(csp.nconflicts(v, x, cur), rng.random(), x) for x in pool]
        cur[v] = min(scored)[2]
    return cur


def solve(problem, hard_time: float = 30.0, soft_time: float = 10.0, seed: int = 42,
          verbose: bool = True):
    t0 = time.time()
    rng = random.Random(seed)
    random.seed(seed)                       # localsearch.min_conflicts uses the global RNG
    sys.setrecursionlimit(max(10000, 4 * len(problem.courses) + 1000))
    log = print if verbose else (lambda *a, **k: None)

    csp = problem.build_csp()
    info: Dict = {"courses": len(csp.variables)}

    # ---- Phase 0: AC-3 (only when cheap enough to be worthwhile) ----------
    work = sum(len(csp.domains[a]) * len(csp.domains[b]) for a in csp.variables for b in csp.neighbors[a])
    info["ac3"] = "skipped (too large)"
    if work <= AC3_MAX_WORK:
        removals = []
        ok = ac3(csp, removals=removals)
        info["ac3"] = f"ran, pruned {len(removals)} values" + ("" if ok else " (domain wipe-out!)")
    base = _snapshot(csp)
    log(f"[phase 0] AC-3: {info['ac3']}")

    # ---- Phase 1: backtracking -------------------------------------------
    assignment: Optional[dict] = None
    status = "none"
    for attempt in range(3):
        csp.domains = {v: list(d) for v, d in base.items()}
        left = t0 + hard_time - time.time()
        if left <= 0:
            break
        deadline = time.time() + (left if attempt == 2 else left * 0.5)
        h = TimetableHeuristics(problem, deadline, rng, randomize=attempt > 0)
        try:
            res = backtracking_search_heuristics(
                csp, select_unassigned_variable=h.select_variable,
                order_domain_values=h.order_values, inference=h.forward_checking)
        except SearchTimeout:
            res = None
            log(f"[phase 1] attempt {attempt + 1}: timed out")
            continue
        if res is not None:
            assignment, status = dict(res), "backtracking"
            info.update(nodes=csp.nodes_expanded, backtracks=csp.backtracks, attempt=attempt + 1)
            break
        status = "infeasible"
        log("[phase 1] search space exhausted: no conflict-free timetable exists")
        break
    csp.domains = {v: list(d) for v, d in base.items()}
    if assignment is not None:
        log(f"[phase 1] backtracking solved it: {info['nodes']} nodes, {info['backtracks']} backtracks")

    # ---- Phase 1b: min-conflicts fallback --------------------------------
    if assignment is None:
        log("[phase 1b] falling back to Min-Conflicts repair")
        best, best_conf = None, None
        for restart in range(5):
            init = _greedy_initial(csp, rng)
            cand = min_conflicts(csp, max_steps=1500, initial_assignment=init)
            conf = _count_conflicts(csp, cand)
            if best is None or conf < best_conf:
                best, best_conf = cand, conf
            if conf == 0 or time.time() - t0 > hard_time:
                break
        assignment = dict(best)
        status = "min-conflicts" if best_conf == 0 else f"min-conflicts ({best_conf} hard conflicts remain)"
        info["residual_conflicts"] = best_conf

    # ---- Phase 2: soft optimisation --------------------------------------
    info["status"] = status
    hard_ok = _count_conflicts(csp, assignment) == 0
    if hard_ok:
        search = SoftSearch(problem, csp, rng)
        assignment, stats = search.run(assignment, time_limit=soft_time)
        info["soft"] = stats
        log(f"[phase 2] soft penalty {stats['start_cost']:.1f} -> {stats['end_cost']:.1f} "
            f"({stats['moves']} moves / {stats['steps']} steps)")
    else:
        log("[phase 2] skipped: hard conflicts remain")

    info["seconds"] = time.time() - t0
    return assignment, info
