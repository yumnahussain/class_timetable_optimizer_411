"""
data_loader.py

Reads the relational CSV datasets from `data_dir` into plain dataclasses.

Design goals
------------
* Dynamic: nothing is hard-coded to the current dataset. Column names are
  normalised (case / punctuation insensitive) and several aliases are accepted.
* Tolerant: optional files / columns (instructor unavailability, preferences,
  explicit enrollment, ...) are used when present and ignored when absent.
* Rules that live in constraints.csv (blocked rooms, preferred rooms) are parsed
  from the `rule` column instead of being hard-coded.
"""

import csv
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def norm_key(s) -> str:
    """Canonical comparison key: collapse whitespace, upper-case."""
    return " ".join(str(s).split()).upper()


def _col(name) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def read_csv(path: str) -> List[Dict[str, str]]:
    """Read a CSV into a list of dicts with normalised column names."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            row = {}
            for k, v in raw.items():
                if k is None:
                    continue
                row[_col(k)] = (v or "").strip() if isinstance(v, str) or v is None else ""
            if any(row.values()):
                rows.append(row)
    return rows


def pick(row: Dict[str, str], *names: str, default: str = "") -> str:
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return v
    return default


def split_items(text: str, pattern: str = r"[;|]") -> List[str]:
    return [p.strip() for p in re.split(pattern, text or "") if p.strip()]


def parse_int(text, default=None):
    try:
        return int(float(str(text).strip()))
    except (ValueError, TypeError):
        return default


def parse_minutes(text: str) -> int:
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*([AaPp][Mm])?", text or "")
    if not m:
        raise ValueError(f"Cannot parse time '{text}'")
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        ap = ap.lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    return h * 60 + mi


def truthy(text: str, default=True) -> bool:
    if text is None or text == "":
        return default
    return text.strip().lower() in ("yes", "y", "true", "1", "available")


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class Slot:
    id: str
    day: str
    start: str
    end: str
    period: str
    start_min: int
    end_min: int
    day_idx: int


@dataclass
class Room:
    id: str
    building: str
    floor: str
    physical_capacity: int
    capacity: int            # scheduling capacity (what the hard constraint uses)
    room_type: str
    available: bool
    notes: str = ""
    features: str = ""


@dataclass
class CourseRec:
    id: str
    level: str = ""
    instructors: List[str] = field(default_factory=list)   # names as written
    rooms_text: str = ""
    context: str = ""
    notes: str = ""
    enrollment: Optional[int] = None        # only if the CSV provides it
    required_type: str = ""                 # only if the CSV provides it


@dataclass
class InstructorRec:
    id: str
    name: str
    courses: List[str] = field(default_factory=list)
    unavailable: List[str] = field(default_factory=list)
    preferred: List[str] = field(default_factory=list)


@dataclass
class Cohort:
    id: str
    name: str
    size: int
    courses: List[str]


@dataclass
class Dataset:
    slots: List[Slot]
    rooms: List[Room]
    courses: List[CourseRec]
    instructors: List[InstructorRec]
    cohorts: List[Cohort]
    blocked_rooms: Set[str]
    preferred_rooms: Dict[str, Set[str]]      # course key -> {room key}
    weights: Dict[str, float]
    warnings: List[str]


# --------------------------------------------------------------------------- #
# Slot-token resolution (used for optional unavailable / preferred columns)
# --------------------------------------------------------------------------- #
def resolve_slot_tokens(tokens: List[str], slots: List[Slot]) -> Set[int]:
    """
    Turn tokens such as 'MON_S1', 'Friday', 'FRI', 'Morning', 'Morning 1',
    'Monday Morning' into a set of slot indices.
    """
    out: Set[int] = set()
    for tok in tokens:
        t = tok.strip().lower()
        if not t:
            continue
        exact = [i for i, s in enumerate(slots) if s.id.lower() == t]
        if exact:
            out.update(exact)
            continue

        def day_match(word, s):
            sd = s.day.lower()
            return sd == word or (len(word) == 3 and sd.startswith(word))

        parts = t.split()
        if len(parts) >= 2 and any(d == parts[0] or (len(parts[0]) == 3 and d.startswith(parts[0])) for d in WEEKDAYS):
            rest = " ".join(parts[1:])
            out.update(i for i, s in enumerate(slots)
                       if day_match(parts[0], s) and s.period.lower().startswith(rest))
            continue
        out.update(i for i, s in enumerate(slots) if day_match(t, s))
        out.update(i for i, s in enumerate(slots) if s.period.lower().startswith(t))
    return out


# --------------------------------------------------------------------------- #
# Main loader
# --------------------------------------------------------------------------- #
def load_dataset(data_dir: str) -> Dataset:
    warnings: List[str] = []

    def path(name):
        return os.path.join(data_dir, name)

    for required in ("courses.csv", "rooms.csv", "time_slots.csv"):
        if not os.path.exists(path(required)):
            raise FileNotFoundError(f"Required dataset '{required}' not found in '{data_dir}'")

    # ---- time slots -------------------------------------------------------
    slots: List[Slot] = []
    day_order: Dict[str, int] = {}
    for r in read_csv(path("time_slots.csv")):
        day = pick(r, "day")
        dl = day.lower()
        if dl in WEEKDAYS:
            didx = WEEKDAYS.index(dl)
        else:
            didx = day_order.setdefault(dl, 100 + len(day_order))
        st, en = pick(r, "start_time", "start"), pick(r, "end_time", "end")
        slots.append(Slot(
            id=pick(r, "slot_id", "id"), day=day, start=st, end=en,
            period=pick(r, "period"), start_min=parse_minutes(st),
            end_min=parse_minutes(en), day_idx=didx))
    if not slots:
        raise ValueError("time_slots.csv contains no slots")

    # ---- rooms ------------------------------------------------------------
    rooms: List[Room] = []
    for r in read_csv(path("rooms.csv")):
        phys = parse_int(pick(r, "physical_capacity", "capacity"), 0)
        cap = parse_int(pick(r, "scheduling_capacity"), None)
        if cap is None:
            cap = phys
        rooms.append(Room(
            id=pick(r, "room_id", "id"), building=pick(r, "building") or pick(r, "room_id", "id").split()[0],
            floor=pick(r, "floor"), physical_capacity=phys, capacity=cap,
            room_type=pick(r, "room_type", "type"),
            available=truthy(pick(r, "available_for_regular_classes", "available"), True),
            notes=pick(r, "scheduling_notes"), features=pick(r, "features_or_constraints", "features")))
    if not rooms:
        raise ValueError("rooms.csv contains no rooms")

    # ---- courses ----------------------------------------------------------
    courses: List[CourseRec] = []
    seen = set()
    for r in read_csv(path("courses.csv")):
        cid = pick(r, "course_id", "course", "id")
        if not cid:
            continue
        if norm_key(cid) in seen:
            warnings.append(f"Duplicate course_id '{cid}' ignored")
            continue
        seen.add(norm_key(cid))
        courses.append(CourseRec(
            id=cid, level=pick(r, "level"),
            instructors=split_items(pick(r, "instructors", "instructor", "instructor_names")),
            rooms_text=pick(r, "rooms_mentioned", "rooms", "room"),
            context=pick(r, "scheduling_context", "context", "activity_type"),
            notes=pick(r, "notes"),
            enrollment=parse_int(pick(r, "enrollment", "enrolment", "expected_enrollment", "enrollment_estimate"), None),
            required_type=pick(r, "required_room_type", "required_type")))
    if not courses:
        raise ValueError("courses.csv contains no courses")

    # ---- instructors (optional) ------------------------------------------
    instructors: List[InstructorRec] = []
    inst_rows = read_csv(path("instructors.csv"))
    if not inst_rows:
        warnings.append("instructors.csv missing/empty: instructor ids derived from course rows")
    for r in inst_rows:
        iid = pick(r, "instructor_id", "id")
        if not iid:
            continue
        instructors.append(InstructorRec(
            id=iid, name=pick(r, "instructor_name", "name"),
            courses=split_items(pick(r, "courses", "course_ids")),
            unavailable=split_items(pick(r, "unavailable_slots", "unavailable", "unavailability"), r"[;,|]"),
            preferred=split_items(pick(r, "preferred_slots", "preferred", "preferences"), r"[;,|]")))

    # ---- cohorts (optional) ----------------------------------------------
    cohorts: List[Cohort] = []
    for r in read_csv(path("student_cohorts.csv")):
        cid = pick(r, "cohort_id", "id")
        if not cid:
            continue
        cohorts.append(Cohort(
            id=cid, name=pick(r, "name"), size=parse_int(pick(r, "size", "student_count", "students"), 0) or 0,
            courses=split_items(pick(r, "mandatory_courses", "courses"))))
    if not cohorts:
        warnings.append("student_cohorts.csv missing/empty: no cohort constraints (H5/S3/S4/S5) will apply")

    # ---- constraints.csv: blocked + preferred rooms ----------------------
    blocked: Set[str] = set()
    preferred_rooms: Dict[str, Set[str]] = {}
    for r in read_csv(path("constraints.csv")):
        rule = pick(r, "rule")
        ctype = pick(r, "constraint_type", "type").lower()
        applies = pick(r, "applies_to")
        m = re.search(r"room_id\s*!=\s*'([^']+)'", rule)
        if m and ctype == "hard":
            blocked.add(norm_key(m.group(1)))
        m = re.search(r"preferred_room\s*=\s*'([^']+)'", rule)
        if m:
            for c in split_items(applies):
                preferred_rooms.setdefault(norm_key(c), set()).add(norm_key(m.group(1)))

    # ---- penalty weights (optional JSON) ---------------------------------
    weights: Dict[str, float] = {}
    for name in ("sample_constraints.json", "constraints.json"):
        p = path(name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    js = json.load(f)
                for item in js.get("soft_constraints", []):
                    m = re.match(r"(S\d+)", item.get("id", ""))
                    if m and "penalty_weight" in item:
                        weights[m.group(1)] = float(item["penalty_weight"])
                break
            except (ValueError, OSError):
                warnings.append(f"Could not parse {name}; default weights used")

    return Dataset(slots, rooms, courses, instructors, cohorts, blocked,
                   preferred_rooms, weights, warnings)
