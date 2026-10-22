## AI Policy: Use & Declaration

- **Limited AI Use:** AI coding assistants (e.g., GitHub Copilot) may be used for syntax suggestions, debugging, coding support, and learning assistance.
- **Prohibited — Project Materials:** Do not paste project prompts, guidelines, problem statements, or substantial portions of project materials into AI systems for code generation, completion, or debugging.
- **Prohibited — Written Work:** You **must not** use AI tools to write, rewrite, generate, or substantially edit any report, written analysis, mathematical reasoning, or explanation submitted for this project. All submitted written work must be **your own writing and reasoning**.
- **Responsibility:** Submitted work must reflect your own understanding, implementation, and problem-solving effort.

### AI Use Declaration

1. Complete the [PETRA AI Student Declaration](https://www.petraai.org/student) based on your actual AI use for this project.
2. Generate and save the declaration image as **`AI_declaration.png`**.
3. Include **`AI_declaration.png`** in your project repository.

> **Required:** Your declaration must accurately reflect how you used AI tools for this project.

### Code Resources
You can refer to or consult code from the following resources:
1. Student Starter Code: [Project02_Test_Student](https://github.com/CS411-MTD/Project02_Test_Student)
2. Reference Code from [AI: A Modern Approach (AIMA Python)](https://github.com/aimacode/aima-python) (CSP & Search modules)

---

## Project Overview: University Class Scheduling & Timetable Optimizer

University course timetabling is a classic, NP-hard **Constraint Satisfaction Problem (CSP)** and combinatorial optimization problem faced by academic institutions worldwide, including UIC.

In this assignment, you will model and implement an automated intelligent class scheduling system that assigns university Computer Science courses to available classrooms/lecture halls and time slots while satisfying essential **Hard Constraints** (zero double-bookings, room capacity limits, instructor availability, cohort clash prevention) and optimizing **Soft Constraints** (instructor preferences, minimizing student dead hours/gaps, campus building transit).

### Learning Objectives

1. **CSP Formulation:** Formulate a complex real-world scheduling problem into Variables ($X$), Domains ($D$), and Constraints ($C$).
2. **Heuristic CSP Search:** Implement CSP Backtracking enhanced with Minimum Remaining Values (MRV), Degree Heuristic, Least Constraining Value (LCV), and Forward Checking / Arc Consistency.
3. **Local Search:** Implement Min-Conflicts local search for soft constraint optimization.
4. **Data Modeling & Validation:** Parse relational CSV datasets (`courses.csv`, `instructors.csv`, `rooms.csv`, `time_slots.csv`, `student_cohorts.csv`, `constraints.csv`) and build a constraint verification engine.
5. **Timetable Generation & Output:** Generate a finalized timetable and export the schedule dynamically to `<studentid>_timetable.csv`.

---

## Your Job

1. Use the provided relational datasets in the `data/` folder (`courses.csv`, `instructors.csv`, `rooms.csv`, `time_slots.csv`, `student_cohorts.csv`, `constraints.csv`).
2. Design and implement your constraint checking, CSP backtracking, and local search algorithms.
3. Provide the main entry point in **`app.py`** via the function **`studentscheduler(data_dir="data", output_dir="data", student_id=None)`**.
4. When `studentscheduler()` is executed, it must dynamically process the datasets from `data_dir`, solve the scheduling problem, and generate the schedule file named **`<studentid>_timetable.csv`** in the specified `output_dir` (default: `data/`).
5. Ensure that your scheduler is dynamic: if datasets in `data/` are updated or changed, your scheduler should still successfully load the new data and generate a valid schedule.
6. **Project Structure Flexibility:** You are free to design and structure your own internal helper modules, classes, and folder structure however you like. In testing, evaluation focuses on executing `studentscheduler()` from `app.py` and verifying that the timetable CSV is created.
7. Explain how your project directory and architecture are built in your **`report.md`** and your **video presentation**.

---

### Project Directory
You must use the exact file names and folder structure shown below. Do not rename, move, or remove the required files or folders, as the project structure will be used for automated testing and evaluation.

```text
├── app.py                      # REQUIRED: Contains studentscheduler() entry point
├── data/                       # Provided relational datasets & output folder
│   ├── courses.csv             # Course catalog and enrollment requirements
│   ├── instructors.csv         # Instructor profiles and availability
│   ├── rooms.csv               # Rooms, buildings, capacities, and room types
│   ├── time_slots.csv          # Weekly timetable time slots
│   ├── student_cohorts.csv     # Student cohorts and curriculum requirements
│   ├── constraints.csv         # Constraint definitions and guidelines
│   └── <studentid>_timetable.csv # Output schedule generated by studentscheduler()
├── report.md                   # REQUIRED: Complete the provided report template
├── AI_declaration.png          # REQUIRED: AI use declaration generated using PETRA
├── requirements.txt            # Python dependencies
└── [Your Custom Modules]       # Helper modules, solvers, or packages of your choice
```

---

### 📋 Task 1: Dataset & Problem Understanding (`data/*.csv`)
The relational datasets are provided for you in `data/`:
- **Courses (`courses.csv`):** Course IDs, course levels, instructor assignments, and room requirements.
- **Instructors (`instructors.csv`):** Instructor IDs, names, assigned courses, and teaching preferences.
- **Rooms (`rooms.csv`):** Room IDs, buildings, physical/scheduling capacities, and room types (Lecture Hall, Computer Lab, Classroom, etc.).
- **Time Slots (`time_slots.csv`):** Weekly time slots across days (Monday to Friday) and periods.
- **Student Cohorts (`student_cohorts.csv`):** Cohorts, student counts, and mandatory courses.
- **Constraints (`constraints.csv`):** Formal definitions of hard and soft scheduling rules.

---

### 📋 Task 2: Constraint Engine & Problem Formulation
Formulate the scheduling problem into variables, domains, and constraints:
- **Hard Constraints (Feasibility - 0 Clashes Allowed):**
  1. *H1: No Room Double-Booking:* No two courses scheduled in the same room at the same time slot.
  2. *H2: Room Capacity & Type Compatibility:* Assigned room capacity $\ge$ course enrollment, and room type matches requirements (e.g. lab courses in Computer Labs).
  3. *H3: No Instructor Double-Booking:* An instructor cannot teach two courses simultaneously.
  4. *H4: Instructor Availability:* No assignments in an instructor's declared unavailable slots.
  5. *H5: No Student Cohort Clash:* Mandatory courses for the same student cohort cannot overlap in time.
  6. *H6: Complete Assignment:* Every required course in the curriculum must be scheduled.
- **Soft Constraints (Quality & Penalties):**
  1. *S1: Instructor Preferences:* Penalize assignments outside preferred slots.
  2. *S2: Room Utilization Fit:* Penalize heavily oversized rooms.
  3. *S3: Student Dead Hours:* Penalize gaps/dead hours in a cohort's daily schedule.
  4. *S4: Consecutive Session Fatigue:* Penalize $>2$ back-to-back classes for cohorts.
  5. *S5: Campus Transit:* Penalize consecutive classes in different buildings without transit time.

---

### 📋 Task 3: Implement CSP & Local Search Algorithms
Implement your scheduling solvers:
1. **CSP Backtracking:**
   - Minimum Remaining Values (MRV) heuristic for variable selection.
   - Degree Heuristic as tie-breaker.
   - Least Constraining Value (LCV) heuristic for value ordering.
   - Forward Checking / Arc Consistency (AC-3) for domain pruning.
2. **Local Search:**
   - Min-Conflicts CSP local search for soft penalty minimization.

---

### 📋 Task 4: Main Entry Point & Timetable Export (`app.py`)
Implement the `studentscheduler()` function in `app.py`:
- Accepts parameters: `data_dir="data"`, `output_dir="data"`, `student_id=None`.
- Loads the datasets dynamically from `data_dir`.
- Executes your CSP / optimization solver to produce a complete schedule.
- Saves the timetable to `<studentid>_timetable.csv` in `output_dir`.
- Returns the path to the generated CSV file.

Recommended CSV format columns:
```csv
course_id,room_id,slot_id,instructor_id,cohort_id,day,start_time,end_time
```

---

### 📋 Task 5: Complete the Report (`report.md`)
Complete all required sections in [report.md](report.md):
- **Student Information:** Full Name, UID (netID), and UIN.
- **Dataset Configuration:** Counts of courses, rooms, and time slots.
- **Local Verification Checklist:** Mark verified solvers and features with `[x]`.
- **Project Structure & Video Presentation:** Provide your video link and explain your directory structure.
- **Discussion & Analysis:** Detailed answers covering CSP formulation, comparison of Backtracking vs Local Search, and LLM/AI integration.

> [!WARNING]
> Do not modify the section headers, bold titles, or overall formatting of [report.md](report.md). Changes to the structure may cause the autograder tests to fail.
> Replace all bracketed placeholder text with your answers. Do not leave any placeholders in the final report.

---

### 📋 Task 6: Record a Video Presentation

Record a **5–7 minute video presentation** explaining your project implementation:
- **Project Directory Structure:** Explain how your codebase, modules, and files are structured and how they interact.
- **Problem Formulation:** How did you formulate variables, domains, and hard/soft constraints?
- **CSP Backtracking Heuristics:** How do MRV, LCV, and Forward Checking improve search efficiency?
- **Local Search & Soft Optimization:** How does Min-Conflicts optimize schedule quality and resolve constraint conflicts?
- **Demonstration:** Show `studentscheduler()` executing and generating the timetable CSV file `<studentid>_timetable.csv`.

#### Video Requirements
- You may use tools such as Zoom, Loom, or OBS Studio to record your presentation.
- Your face must be visible during the presentation. If you are not comfortable with this requirement, please discuss it with the instructor in advance.
- The recorded video must be in `.mp4` format and must not exceed **7 minutes**.
- Upload the video to a sharing platform such as YouTube, Google Drive, or Dropbox.
- Ensure the video link is publicly accessible to the instructor.
- Add the video link to Section 3 of `report.md`.

---

## Marking Scheme (100 marks)

### 1. Project Implementation (40 marks)
- **Required Files & Datasets Check (10 marks):** `app.py`, `report.md`, `AI_declaration.png`, and datasets in `data/` present.
- **Scheduler & Timetable Generation (30 marks):** `studentscheduler()` in `app.py` runs successfully on the dataset, dynamically generates `<studentid>_timetable.csv` in `data/`, and outputs a valid non-empty timetable schedule.

### 2. Completion of report.md (30 marks)
- **Student Information (5 marks):** Full Name, UID (netID), and UIN filled in.
- **Dataset Configuration (5 marks):** Course, room, and time slot counts documented.
- **Verification Checklist (5 marks):** Checklist showing verified solvers and CSV export.
- **Presentation & Project Structure (5 marks):** Provide valid video presentation link and project directory structure overview.
- **Discussion & Problem Formulation (10 marks):** Comprehensive analysis answering the 3 discussion questions.

### 3. Schedule Correctness, Quality & Video Presentation (30 marks)
**Note**: This section is manually graded.
- **Constraint Satisfaction & Correctness (15 marks):** The generated schedule strictly adheres to all hard constraints (0 room conflicts, 0 instructor conflicts, 0 cohort clashes, room capacities respected).
- **Soft Constraint Optimization & Quality (5 marks):** Effective minimization of soft penalties (instructor preferences, cohort gaps, transit time).
- **Video Presentation (10 marks):** The 5–7 minute presentation clearly demonstrates the scheduler, explains the CSP formulation, heuristics, and local search optimization.

---

## Submission Instructions

### 1. Pre-Submission Check

Before submitting, make sure all required files are included and follow the required directory structure.

**Note**: The Gradescope autograder awards up to 70 points. The remaining 30 points are manually graded.

### 2. Submission to Gradescope

* Submit all required files to Gradescope.
* Do not rename or move required files/folders/structure.
* Review your autograder results and score after submission.
* You may revise and resubmit before the deadline.

**Note**: Only the official Gradescope results are used for grading.


