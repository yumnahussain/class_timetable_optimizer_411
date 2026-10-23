"""
backtracking.py

Constraint Satisfaction Problem (CSP) framework, standard backtracking search,
and heuristic improvements (MRV, Degree heuristic, LCV, Forward Checking, AC-3).

"""

from typing import Dict, List, Tuple, Set, Optional, Any, Callable


# =============================================================================
# 1. CSP Framework
# =============================================================================

class CSP:
    """
    Represent a Constraint Satisfaction Problem.
    - variables: list of variable names.
    - domains: dict mapping variable -> list of allowable values.
    - neighbors: dict mapping variable -> set of neighboring variables.
    - constraints: binary constraint function (var1, val1, var2, val2) -> bool.
    """
    def __init__(
        self,
        variables: List[str],
        domains: Dict[str, List[Any]],
        neighbors: Dict[str, Set[str]],
        constraints: Callable[[str, Any, str, Any], bool]
    ):
        self.variables = variables
        self.domains = {v: list(domains[v]) for v in variables}
        self.neighbors = {v: set(neighbors.get(v, [])) for v in variables}
        self.constraints = constraints
        self.initial_domains = {v: list(domains[v]) for v in variables}
        self.nassigns = 0
        self.nodes_expanded = 0
        self.backtracks = 0

    def assign(self, var: str, val: Any, assignment: Dict[str, Any]) -> None:
        """Assign a value to a variable and record assignment count."""
        assignment[var] = val
        self.nassigns += 1

    def unassign(self, var: str, assignment: Dict[str, Any]) -> None:
        """Remove a variable from assignment."""
        if var in assignment:
            del assignment[var]

    def nconflicts(self, var: str, val: Any, assignment: Dict[str, Any]) -> int:
        """Count how many assigned neighbors conflict with (var = val)."""
        count = 0
        for neighbor in self.neighbors.get(var, []):
            if neighbor in assignment:
                if not self.constraints(var, val, neighbor, assignment[neighbor]):
                    count += 1
        return count

    def is_consistent(self, var: str, val: Any, assignment: Dict[str, Any]) -> bool:
        """Return True if (var = val) satisfies all constraints with assigned neighbors."""
        return self.nconflicts(var, val, assignment) == 0

    def prune(self, var: str, value: Any, removals: Optional[List[Tuple[str, Any]]]) -> None:
        """Rule out value from domain of var and record removal."""
        if value in self.domains[var]:
            self.domains[var].remove(value)
            if removals is not None:
                removals.append((var, value))

    def restore(self, removals: List[Tuple[str, Any]]) -> None:
        """Undo all domain prunings in removals list."""
        while removals:
            var, val = removals.pop()
            self.domains[var].append(val)


# =============================================================================
# 2. Variable & Value Ordering Heuristics
# =============================================================================

def first_unassigned_variable(assignment: Dict[str, Any], csp: CSP) -> Optional[str]:
    """Default variable ordering: first unassigned variable in variable list."""
    for var in csp.variables:
        if var not in assignment:
            return var
    return None


def unordered_domain_values(var: str, assignment: Dict[str, Any], csp: CSP) -> List[Any]:
    """Default value ordering: return domain values as defined."""
    return list(csp.domains[var])


def mrv(assignment: Dict[str, Any], csp: CSP) -> Optional[str]:
    """
    Minimum Remaining Values (MRV / Most Constrained Variable) with Degree Heuristic tie-breaker.
    Selects unassigned variable with the fewest remaining legal values.
    """
    unassigned = [v for v in csp.variables if v not in assignment]
    if not unassigned:
        return None

    def num_legal_values(v: str) -> int:
        return sum(1 for val in csp.domains[v] if csp.is_consistent(v, val, assignment))

    def degree(v: str) -> int:
        return sum(1 for neighbor in csp.neighbors[v] if neighbor not in assignment)

    return min(unassigned, key=lambda v: (num_legal_values(v), -degree(v)))


def lcv(var: str, assignment: Dict[str, Any], csp: CSP) -> List[Any]:
    """
    Least Constraining Value (LCV) heuristic.
    Orders values by fewest conflicts caused in unassigned neighbors' domains.
    """
    def count_conflicts(val: Any) -> int:
        conflicts = 0
        for neighbor in csp.neighbors[var]:
            if neighbor not in assignment:
                for n_val in csp.domains[neighbor]:
                    if not csp.constraints(var, val, neighbor, n_val):
                        conflicts += 1
        return conflicts

    return sorted(csp.domains[var], key=count_conflicts)


# =============================================================================
# 3. Inference & Constraint Propagation (Forward Checking, AC-3)
# =============================================================================

def forward_checking(csp: CSP, var: str, value: Any, assignment: Dict[str, Any],
                     removals: Optional[List[Tuple[str, Any]]] = None) -> bool:
    """
    Forward Checking inference.
    Prunes incompatible values from unassigned neighbors.
    Returns False if any neighbor domain becomes empty.
    """
    for neighbor in csp.neighbors[var]:
        if neighbor not in assignment:
            for n_val in list(csp.domains[neighbor]):
                if not csp.constraints(var, value, neighbor, n_val):
                    csp.prune(neighbor, n_val, removals)

            if not csp.domains[neighbor]:
                return False
    return True


def revise(csp: CSP, Xi: str, Xj: str, removals: Optional[List[Tuple[str, Any]]] = None) -> bool:
    """Return True if we revise domain of Xi to make arc (Xi, Xj) consistent."""
    revised = False
    for x in list(csp.domains[Xi]):
        if not any(csp.constraints(Xi, x, Xj, y) for y in csp.domains[Xj]):
            csp.prune(Xi, x, removals)
            revised = True
    return revised


def ac3(csp: CSP, queue: Optional[List[Tuple[str, str]]] = None,
        removals: Optional[List[Tuple[str, Any]]] = None) -> bool:
    """
    AC-3 (Arc Consistency Algorithm #3).
    Enforces arc consistency across all constraint arcs in the queue.
    """
    if queue is None:
        queue = [(Xi, Xk) for Xi in csp.variables for Xk in csp.neighbors[Xi]]

    while queue:
        Xi, Xj = queue.pop(0)
        if revise(csp, Xi, Xj, removals):
            if not csp.domains[Xi]:
                return False
            for Xk in csp.neighbors[Xi]:
                if Xk != Xj:
                    queue.append((Xk, Xi))
    return True


# =============================================================================
# 4. Backtracking Search Solvers
# =============================================================================

def backtracking_search(
    csp: CSP,
    select_unassigned_variable: Callable[[Dict[str, Any], CSP], Optional[str]] = first_unassigned_variable,
    order_domain_values: Callable[[str, Dict[str, Any], CSP], List[Any]] = unordered_domain_values
) -> Optional[Dict[str, Any]]:
    """Standard recursive Backtracking Search."""
    csp.nodes_expanded = 0
    csp.backtracks = 0

    def backtrack(assignment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        csp.nodes_expanded += 1
        if len(assignment) == len(csp.variables):
            return assignment

        var = select_unassigned_variable(assignment, csp)
        if var is None:
            return assignment

        for val in order_domain_values(var, assignment, csp):
            if csp.is_consistent(var, val, assignment):
                csp.assign(var, val, assignment)
                result = backtrack(assignment)
                if result is not None:
                    return result
                csp.unassign(var, assignment)
                csp.backtracks += 1

        return None

    return backtrack({})


def backtracking_search_heuristics(
    csp: CSP,
    select_unassigned_variable: Callable = mrv,
    order_domain_values: Callable = lcv,
    inference: Callable = forward_checking
) -> Optional[Dict[str, Any]]:
    """
    Heuristic-enhanced Backtracking Search with MRV, LCV, and Forward Checking / AC-3.
    """
    csp.nodes_expanded = 0
    csp.backtracks = 0

    def backtrack(assignment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        csp.nodes_expanded += 1
        if len(assignment) == len(csp.variables):
            return assignment

        var = select_unassigned_variable(assignment, csp)
        if var is None:
            return assignment

        for val in order_domain_values(var, assignment, csp):
            if csp.is_consistent(var, val, assignment):
                csp.assign(var, val, assignment)
                removals: List[Tuple[str, Any]] = []
                if inference(csp, var, val, assignment, removals):
                    result = backtrack(assignment)
                    if result is not None:
                        return result
                csp.restore(removals)
                csp.unassign(var, assignment)
                csp.backtracks += 1

        return None

    return backtrack({})


