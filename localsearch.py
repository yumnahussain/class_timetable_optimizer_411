"""
localsearch.py

Generic Local Search algorithms for Constraint Satisfaction Problems (CSP).
Self-contained with no domain-specific logic.
"""

import random
from typing import Dict, Any, Optional, List
from backtracking import CSP


def min_conflicts(csp: CSP, max_steps: int = 1000, initial_assignment: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Min-Conflicts Local Search Algorithm for generic CSPs.

    Arguments:
        csp: A CSP instance with variables, domains, neighbors, and constraints.
        max_steps: Maximum number of repair steps to attempt.
        initial_assignment: Optional starting complete assignment (dict mapping var -> val).

    Returns:
        A complete assignment satisfying all constraints if found, or the current state upon reaching max_steps.
    """
    current: Dict[str, Any] = {}
    if initial_assignment:
        current = dict(initial_assignment)
    else:
        for var in csp.variables:
            current[var] = random.choice(csp.domains[var])

    for step in range(max_steps):
        conflicted = [var for var in csp.variables if csp.nconflicts(var, current[var], current) > 0]
        if not conflicted:
            return current

        var = random.choice(conflicted)
        min_conf = float("inf")
        best_vals: List[Any] = []
        for val in csp.domains[var]:
            conf = csp.nconflicts(var, val, current)
            if conf < min_conf:
                min_conf = conf
                best_vals = [val]
            elif conf == min_conf:
                best_vals.append(val)

        current[var] = random.choice(best_vals)

    return current
