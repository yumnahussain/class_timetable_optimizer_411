# Project 2 Report: University Class Scheduling & Timetable Optimization

> [!IMPORTANT]
> **AUTOGRADER COMPLIANCE INSTRUCTIONS:**
> This report is parsed automatically by the autograder. To ensure you receive full credit for your work:
> 1. **Do not modify** the section headers (`## ...`) or bold field keys (e.g., `**Name:**`, `**Total Courses Configured:**`, `**Video Presentation Link:**`, etc.).
> 2. **Write your answers directly after** the colon `:` of each field, replacing the placeholder text completely (including the outer brackets `[` and `]`).
> 3. **Maintain the file structure**. Changing headers, bold titles, or deleting lines can cause the autograder to miss your responses and award 0 marks.

---

## Student Information 
- **Name:** Yumna Hussain
- **UID (netID):** yhuss3
- **UIN:** 673006309

---

## Section 1: Dataset & University Configuration
- **Total Courses Configured:** [Write total number of courses here, must be 15 or more]
- **Total Rooms Configured:** [Write total number of rooms here, must be 6 or more]
- **Total Time Slots Configured:** [Write total number of time slots here, must be 15 or more]

---

## Section 2: Local Verification & Implemented Solvers
*Check the algorithms and features you successfully ran and verified by placing an `x` in the brackets (e.g., `[x]`):*
- [ ] DataLoader & CSV Parsing
- [ ] Hard Constraint Validation Engine
- [ ] Soft Penalty & Quality Evaluation Engine
- [ ] CSP Backtracking with MRV + LCV + Forward Checking
- [ ] Min-Conflicts CSP Local Search
- [ ] Timetable CSV Export (<studentid>_timetable.csv)

---

## Section 3: Video Presentation & Project Structure
- **Video Presentation Link:** [Provide an accessible link to your 5–7 minute video presentation]
- **Project Directory Structure:** All of the data sits in .csv files withing the data/ directory. app.py is the entry point and holds studentscheduler(), which loads the data, runs the solver, and writes the timetable CSV. data_loader.py reads the CSV files, and timetable_model.py defines the variables, domains, constraints, and soft penalty score. backtracking.py and localsearch.py hold the CSP and Min-Conflicts algorithms, csp_heuristics.py has the MRV, LCV, and forward checking versions of the algorithms, and soft_search.py optimizes the soft penalties. solver.py runs the full pipeline, and the data/ folder holds the input CSVs and the output <studentid>_timetable.csv. report.md, AI_declaration.png, and requirements.txt sit in the root as required.

---

## Section 4: Discussion & Problem Formulation
*Provide your written analysis for each point by replacing the bracket placeholders below:*
- **How did you formulate the variables, domains, and constraints for this scheduling problem?**
    Each course is a variable, and its domain is the set of (time slot, room) pairs that pass the single-course rules: the room is available, not blocked (LAB 254), big enough, and type-compatible, and the instructors are free. Since the data has no enrollment column, I used cohort size, or an estimate from the rooms a course historically used. The hard constraints between courses (no shared room, instructor, or cohort) apply only when the sessions overlap in time, which I check using real start and end times because some slots overlap. Soft constraints S1-S5 and the room preferences are combined into one penalty score that is minimized after a valid timetable is found.
- **Compare CSP Backtracking (with heuristics) vs Local Search (Min-Conflicts) in terms of scalability, completeness, and solution quality.**
    Backtracking is complete. It finds a valid timetable if one exists and can prove when none does, while Min-Conflicts can get stuck and can never prove infeasibility. With MRV, LCV and forward checking, backtracking solved all 65 courses with zero backtracks, though it only returns the first valid timetable, which had a poor soft penalty of 1071. Local search is better for quality, since it cut that penalty to 46 without breaking any hard constraint, so I use backtracking to get feasibility and local search to optimize.
- **How can modern AI / LLM techniques be combined with CSP solvers for real-world automated university scheduling?**
    An LLM can turn messy data/text, like the room mentions and scheduling contexts in this dataset or an instructor’s emailed request, into structured constraints for the solver. It can also explain infeasible results in plain English and suggest which constraints to relax. Because LLMs can hallucinate, the CSP solver should stay the final decision maker and validate every schedule against the hard constraints.
