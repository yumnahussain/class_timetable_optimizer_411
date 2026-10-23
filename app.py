"""
UIC CS 411 Project 2: University Class Scheduling (CSP) - Main Entry Point

Architecture (flat modules, all importable from this folder):

  app.py              studentscheduler() entry point + CSV export        (this file)
  data_loader.py      CSV -> dataclasses; tolerant of missing/extra columns
  timetable_model.py  problem formulation: variables, domains, hard/soft
                      constraints, soft-cost function, independent validator
  backtracking.py     generic CSP + backtracking, MRV/Degree/LCV, FC, AC-3
  csp_heuristics.py   fast timetable-specific MRV / LCV / forward-checking callables
  localsearch.py      generic Min-Conflicts (hard-conflict repair / fallback)
  soft_search.py      Min-Conflicts-style search that minimises soft penalties
  solver.py           pipeline: AC-3 -> backtracking -> (fallback) -> soft search

The scheduler reads everything from `data_dir` at call time, so replacing the CSVs
is enough to get a new timetable.
"""

import csv
import os
import re
import sys

# Make sibling modules importable no matter where the caller's cwd is.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from data_loader import load_dataset                      # noqa: E402
from timetable_model import Problem, validate             # noqa: E402
from solver import solve                                  # noqa: E402

CSV_COLUMNS = ["course_id", "room_id", "slot_id", "instructor_id",
               "cohort_id", "day", "start_time", "end_time"]


def get_student_id():
    """
    Helper function to extract your UID (netID) from report.md.
    Alternatively, you may specify your student ID directly.
    """
    report_path = os.path.join(os.path.dirname(__file__), 'report.md')
    if os.path.exists(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Check for UID (netID) or NetID or UIN
                match = re.search(r'-\s*\*\*UID \(netID\):\*\*\s*(.*)', content, re.IGNORECASE)
                if not match:
                    match = re.search(r'-\s*\*\*UIN:\*\*\s*(.*)', content, re.IGNORECASE)
                if match:
                    val = match.group(1).strip()
                    if val and not (val.startswith('[') and val.endswith(']')):
                        return re.sub(r'[^a-zA-Z0-9_-]', '_', val)
        except Exception:
            pass
    return "student"


def _resolve_dirs(data_dir, output_dir):
    """Relative paths are tried against the cwd first, then against this file's folder."""
    fell_back = False
    if not os.path.isabs(data_dir) and not os.path.isdir(data_dir):
        alt = os.path.join(_HERE, data_dir)
        if os.path.isdir(alt):
            data_dir, fell_back = alt, True
    if fell_back and not os.path.isabs(output_dir):
        output_dir = os.path.join(_HERE, output_dir)
    return data_dir, output_dir


def studentscheduler(data_dir="data", output_dir="data", student_id=None,
                     seed=42, hard_time=30.0, soft_time=10.0, verbose=True):
    """
    Main entry point for generating university course schedule.

    Args:
        data_dir (str): Directory containing input CSV files (courses.csv, rooms.csv,
            instructors.csv, time_slots.csv, student_cohorts.csv, constraints.csv).
        output_dir (str): Directory where '<studentid>_timetable.csv' will be saved.
        student_id (str, optional): ID used in the filename. Defaults to the one in report.md.
        seed (int): RNG seed (results are reproducible for a given dataset + seed).
        hard_time (float): seconds allowed for the feasibility phase.
        soft_time (float): seconds allowed for soft-penalty optimisation.
        verbose (bool): print a short progress / quality summary.

    Returns:
        str: Path to the generated '<studentid>_timetable.csv' file.
    """
    if student_id is None:
        student_id = get_student_id()

    data_dir, output_dir = _resolve_dirs(data_dir, output_dir)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{student_id}_timetable.csv")
    log = print if verbose else (lambda *a, **k: None)

    # 1. load  2. formulate  3. solve
    data = load_dataset(data_dir)
    problem = Problem(data)
    for w in problem.warnings:
        log(f"[warning] {w}")
    assignment, info = solve(problem, hard_time=hard_time, soft_time=soft_time,
                             seed=seed, verbose=verbose)

    # 4. export (one row per course; co-instructors / shared cohorts joined with ';')
    rows = []
    for c in problem.courses:
        if c.id not in assignment:
            continue
        s, r = assignment[c.id]
        slot, room = problem.slots[s], problem.rooms[r]
        rows.append({
            "course_id": c.id, "room_id": room.id, "slot_id": slot.id,
            "instructor_id": ";".join(c.instructors), "cohort_id": ";".join(c.cohorts),
            "day": slot.day, "start_time": slot.start, "end_time": slot.end,
            "_k": (slot.day_idx, slot.start_min, c.id)})
    rows.sort(key=lambda x: x["_k"])
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)

    # quality report
    if verbose:
        viol = validate(problem, assignment)
        total_hard = sum(len(v) for v in viol.values())
        from collections import defaultdict
        acc = defaultdict(float)
        soft = problem.soft_cost(assignment, acc)
        print(f"[result] {len(rows)}/{len(problem.courses)} courses scheduled via {info['status']} "
              f"in {info['seconds']:.1f}s")
        print(f"[result] hard violations: {total_hard} "
              + "(" + ", ".join(f"{k}={len(v)}" for k, v in viol.items()) + ")")
        print(f"[result] soft penalty: {soft:.1f}  "
              + str({k: round(v, 1) for k, v in sorted(acc.items())}))
        for k, v in viol.items():
            for m in v[:5]:
                print(f"   {k}: {m}")

    return output_path


if __name__ == "__main__":
    generated_file = studentscheduler()
    print(f"Timetable generation completed. Output file: {generated_file}")
