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

from data_loader import load_dataset
from timetable_model import Problem
from solver import solve

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

    problem = Problem(load_dataset(data_dir))
    assignment = solve(problem)

    rows = []
    for c in problem.courses:
        s, r = assignment[c.id]
        slot, room = problem.slots[s], problem.rooms[r]
        rows.append({
            "course_id": c.id, "room_id": room.id, "slot_id": slot.id,
            "instructor_id": ";".join(c.instructors), "cohort_id": ";".join(c.cohorts),
            "day": slot.day, "start_time": slot.start, "end_time": slot.end,
            "_k": (slot.day_idx, slot.start_min, c.id)})
    rows.sort(key=lambda x: x["_k"])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    return output_path

if __name__ == "__main__":
    generated_file = studentscheduler()
    print(f"Timetable generation completed. Output file: {generated_file}")
