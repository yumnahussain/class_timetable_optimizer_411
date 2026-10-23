"""Loads the CSV datasets from data_dir into simple dataclasses."""

import csv
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def norm_key(s) -> str:
    return " ".join(str(s).split()).upper()


def _col(name) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [{_col(k): (v or "").strip() for k, v in raw.items() if k is not None}
                for raw in csv.DictReader(f)]
    return [r for r in rows if any(r.values())]


def pick(row, *names, default=""):
    for n in names:
        if row.get(n):
            return row[n]
    return default


def split_items(text: str, pattern: str = r"[;|]") -> List[str]:
    return [p.strip() for p in re.split(pattern, text or "") if p.strip()]


def parse_int(text, default=0):
    try:
        return int(float(str(text).strip()))
    except ValueError:
        return default


def parse_minutes(text: str) -> int:
    h, m = re.match(r"\s*(\d{1,2})[:.](\d{2})", text).groups()
    return int(h) * 60 + int(m)


@dataclass
class Slot:
    id: str
    day: str
    start: str
    end: str
    start_min: int
    end_min: int
    day_idx: int


@dataclass
class Room:
    id: str
    building: str
    capacity: int
    room_type: str
    available: bool


@dataclass
class CourseRec:
    id: str
    level: str
    instructors: List[str]
    rooms_text: str
    context: str


@dataclass
class InstructorRec:
    id: str
    name: str
    courses: List[str]
    unavailable: List[str] = field(default_factory=list)
    preferred: List[str] = field(default_factory=list)


@dataclass
class Cohort:
    id: str
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
    preferred_rooms: Dict[str, Set[str]]
    weights: Dict[str, float]


def resolve_slot_tokens(tokens: List[str], slots: List[Slot]) -> Set[int]:
    """Slot ids or day names (e.g. 'MON_S1', 'Friday') -> slot indices."""
    out = set()
    for tok in tokens:
        t = tok.strip().lower()
        out.update(i for i, s in enumerate(slots) if t in (s.id.lower(), s.day.lower()))
    return out


def load_dataset(data_dir: str) -> Dataset:
    def path(name):
        return os.path.join(data_dir, name)

    day_order: Dict[str, int] = {}
    slots = []
    for r in read_csv(path("time_slots.csv")):
        day = pick(r, "day")
        idx = WEEKDAYS.index(day.lower()) if day.lower() in WEEKDAYS else day_order.setdefault(day.lower(), 100 + len(day_order))
        st, en = pick(r, "start_time"), pick(r, "end_time")
        slots.append(Slot(pick(r, "slot_id"), day, st, en, parse_minutes(st), parse_minutes(en), idx))

    rooms = []
    for r in read_csv(path("rooms.csv")):
        rid = pick(r, "room_id")
        cap = parse_int(pick(r, "scheduling_capacity", "physical_capacity"))
        avail = pick(r, "available_for_regular_classes", default="yes").lower() in ("yes", "y", "true", "1")
        rooms.append(Room(rid, pick(r, "building") or rid.split()[0], cap, pick(r, "room_type"), avail))

    courses, seen = [], set()
    for r in read_csv(path("courses.csv")):
        cid = pick(r, "course_id")
        if cid and norm_key(cid) not in seen:
            seen.add(norm_key(cid))
            courses.append(CourseRec(cid, pick(r, "level"), split_items(pick(r, "instructors")),
                                     pick(r, "rooms_mentioned"), pick(r, "scheduling_context")))

    instructors = [InstructorRec(pick(r, "instructor_id"), pick(r, "instructor_name"),
                                 split_items(pick(r, "courses")),
                                 split_items(pick(r, "unavailable_slots"), r"[;,|]"),
                                 split_items(pick(r, "preferred_slots"), r"[;,|]"))
                   for r in read_csv(path("instructors.csv")) if pick(r, "instructor_id")]

    cohorts = [Cohort(pick(r, "cohort_id"), parse_int(pick(r, "size")), split_items(pick(r, "mandatory_courses")))
               for r in read_csv(path("student_cohorts.csv")) if pick(r, "cohort_id")]

    blocked: Set[str] = set()
    preferred_rooms: Dict[str, Set[str]] = {}
    for r in read_csv(path("constraints.csv")):
        rule = pick(r, "rule")
        m = re.search(r"room_id\s*!=\s*'([^']+)'", rule)
        if m and pick(r, "constraint_type", "type").lower() == "hard":
            blocked.add(norm_key(m.group(1)))
        m = re.search(r"preferred_room\s*=\s*'([^']+)'", rule)
        if m:
            for c in split_items(pick(r, "applies_to")):
                preferred_rooms.setdefault(norm_key(c), set()).add(norm_key(m.group(1)))

    weights: Dict[str, float] = {}
    for name in ("sample_constraints.json", "constraints.json"):
        if os.path.exists(path(name)):
            with open(path(name), encoding="utf-8") as f:
                for item in json.load(f).get("soft_constraints", []):
                    m = re.match(r"(S\d+)", item.get("id", ""))
                    if m and "penalty_weight" in item:
                        weights[m.group(1)] = float(item["penalty_weight"])
            break

    return Dataset(slots, rooms, courses, instructors, cohorts, blocked, preferred_rooms, weights)
