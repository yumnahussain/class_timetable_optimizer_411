"""
UIC CS 411 Project 2: University Class Scheduling (CSP) - Main Entry Point

Instructions for Students:
1. You have complete flexibility in how you design your project folder structure, classes, and helper modules.
2. Implement your scheduling logic inside or called from `studentscheduler()`.
3. Your scheduler should read data dynamically from `data_dir` (default: 'data').
   - If we change or replace the datasets in `data/`, your solution should still work dynamically.
4. Your scheduler must generate the final timetable and save it as `<studentid>_timetable.csv` inside `output_dir` (default: 'data').
5. The function `studentscheduler()` must return the path to the created CSV file.
6. In your report and video presentation, explain how your project directory and architecture are built.
"""

import os
import re
import csv

# TODO: Import your custom modules, solvers, or constraint models here.
# Example: from my_scheduler.csp import CSPSolver

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

def studentscheduler(data_dir="data", output_dir="data", student_id=None):
    """
    Main entry point for generating university course schedule.

    Args:
        data_dir (str): Directory containing input CSV files (e.g. courses.csv, rooms.csv, instructors.csv, time_slots.csv, student_cohorts.csv).
        output_dir (str): Directory where the output '<studentid>_timetable.csv' will be saved.
        student_id (str, optional): The student ID to use in filename. Defaults to student ID in report.md.

    Returns:
        str: Path to the generated '<studentid>_timetable.csv' file.
    """
    if student_id is None:
        student_id = get_student_id()

    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{student_id}_timetable.csv"
    output_path = os.path.join(output_dir, output_filename)

    # =========================================================================
    # TODO: Implement your CSP / Local Search scheduling solution below.
    #
    # 1. Load data from data_dir (e.g., courses.csv, instructors.csv, rooms.csv, time_slots.csv, student_cohorts.csv).
    # 2. Formulate CSP variables, domains, hard constraints, and soft constraints.
    # 3. Solve the schedule using Backtracking (MRV, LCV, Forward Checking) and/or Local Search.
    # 4. Save the resulting schedule to `output_path`.
    #
    # Expected CSV columns (recommended):
    # course_id, room_id, slot_id, instructor_id, cohort_id, day, start_time, end_time
    # =========================================================================

    return output_path

if __name__ == "__main__":
    generated_file = studentscheduler()
    print(f"Timetable generation completed. Output file: {generated_file}")
