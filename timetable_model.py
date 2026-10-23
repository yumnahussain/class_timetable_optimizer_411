"""
Formulates the timetable as a CSP.

Variable: one per course. Value: (slot_index, room_index).
Domain filtering covers the single-course hard rules (room availability, capacity, room type, H4).
Binary hard constraints (H1 room, H3 instructor, H5 cohort) apply when two sessions overlap in time.
"""

import math
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from backtracking import CSP
from data_loader import Dataset, norm_key, resolve_slot_tokens, split_items

Value = Tuple[int, int]

DEFAULT_WEIGHTS = {"S1": 10.0, "S2": 5.0, "S3": 8.0, "S4": 12.0, "S5": 6.0,
                   "PREF_ROOM": 15.0, "HIST_ROOM": 3.0, "LAB": 4.0}
EXCESS_FREE_SEATS = 30
BACK_TO_BACK_GAP = 20       # minutes
DEFAULT_ENROLLMENT = {"graduate": 20, "undergraduate": 25}


def expand_room_mentions(text: str, known: Set[str]) -> List[str]:
    """'TECH 201/202' -> ['TECH 201', 'TECH 202'], keeping only known rooms."""
    out: List[str] = []
    for tok in split_items(text):
        parts = [p.strip() for p in tok.split("/")]
        cands = [tok]
        if len(parts) > 1 and norm_key(tok) not in known:
            m = re.match(r"^(.*?)(\d+[A-Za-z]?)$", parts[0])
            if m and all(re.fullmatch(r"\d+[A-Za-z]?", p) for p in parts[1:]):
                cands = [parts[0]] + [m.group(1) + p for p in parts[1:]]
            else:
                cands = parts
        for c in cands:
            k = norm_key(c)
            if k in known and k not in out:
                out.append(k)
    return out


def room_tags(room) -> Set[str]:
    t = room.room_type.lower()
    pairs = (("auditorium", "auditorium"), ("lecture", "lecture"), ("classroom", "classroom"),
             ("lab", "lab"), ("computer", "computer"), ("specialized", "specialized"), ("specialized", "evl"))
    return {tag for tag, kw in pairs if kw in t}


def activity_tags(context: str) -> Set[str]:
    """Room tags that can host a course, judged from its scheduling_context."""
    general = {"classroom", "lecture", "lab", "specialized"}
    need: Set[str] = set()
    for tok in context.lower().split(";"):
        matched = False
        if "computer lab" in tok:
            need |= {"computer", "lab", "specialized"}; matched = True
        elif "lab" in tok:
            need |= {"lab", "classroom", "computer"}; matched = True
        if "lecture" in tok:
            need |= {"auditorium", "lecture", "classroom"}; matched = True
        if "discussion" in tok:
            need |= {"classroom", "lab"}; matched = True
        if "specialized" in tok:
            need |= {"specialized", "classroom"}; matched = True
        if any(k in tok for k in ("seminar", "graduate", "elective", "upper-level",
                                  "400-level", "topic", "placeholder", "section")):
            need |= general; matched = True
        if not matched and tok.strip():
            need |= general | {"auditorium"}
    return need or (general | {"auditorium"})


class Course:
    pass


class Problem:
    def __init__(self, data: Dataset):
        self.data = data
        self.w = {**DEFAULT_WEIGHTS, **data.weights}
        self._build_slots()
        self._build_rooms()
        self._build_people()
        self._build_courses()
        self._build_domains()
        self._build_graph()
        self.unary = {c.id: {v: self.unary_cost(c, v) for v in c.domain} for c in self.courses}

    def _build_slots(self):
        S = self.data.slots
        n = len(S)
        self.slots = S
        self.slot_day = [s.day_idx for s in S]
        self.slot_start = [s.start_min for s in S]
        self.slot_end = [s.end_min for s in S]
        self.ov = [[S[i].day_idx == S[j].day_idx and S[i].start_min < S[j].end_min
                    and S[j].start_min < S[i].end_min for j in range(n)] for i in range(n)]
        self.ovset = [frozenset(j for j in range(n) if self.ov[i][j]) for i in range(n)]

    def _build_rooms(self):
        R = self.data.rooms
        self.rooms = R
        self.room_index = {norm_key(r.id): i for i, r in enumerate(R)}
        buildings: Dict[str, int] = {}
        self.room_building = [buildings.setdefault(r.building.upper(), len(buildings)) for r in R]
        self.room_tag = [room_tags(r) for r in R]
        self.avail_rooms = [i for i, r in enumerate(R)
                            if r.available and norm_key(r.id) not in self.data.blocked_rooms and r.capacity > 0]

    def _build_people(self):
        self.unavail: Dict[str, Set[int]] = {}
        self.pref: Dict[str, Set[int]] = {}
        self.by_name = defaultdict(list)
        for rec in self.data.instructors:
            self.by_name[norm_key(rec.name)].append(rec)
            self.unavail[rec.id] = resolve_slot_tokens(rec.unavailable, self.slots)
            self.pref[rec.id] = resolve_slot_tokens(rec.preferred, self.slots)
        self.inst_course_keys = {r.id: {norm_key(c) for c in r.courses} for r in self.data.instructors}

    def _resolve_instructors(self, rec) -> List[str]:
        ids: List[str] = []
        ck = norm_key(rec.id)
        for name in rec.instructors:
            cands = self.by_name.get(norm_key(name))
            if cands:
                for x in [x for x in cands if ck in self.inst_course_keys[x.id]] or cands[:1]:
                    if x.id not in ids:
                        ids.append(x.id)
            else:
                synth = "INSTR_" + re.sub(r"\W+", "_", name.strip()).upper()
                self.unavail.setdefault(synth, set())
                self.pref.setdefault(synth, set())
                if synth not in ids:
                    ids.append(synth)
        for iid, keys in self.inst_course_keys.items():
            if ck in keys and iid not in ids:
                ids.append(iid)
        return ids

    def _build_courses(self):
        known = set(self.room_index)
        course_keys = {norm_key(c.id): c.id for c in self.data.courses}
        cohort_of: Dict[str, List[str]] = defaultdict(list)
        self.cohort_size = {}
        self.cohort_members: Dict[str, List[str]] = {}
        for co in self.data.cohorts:
            self.cohort_size[co.id] = co.size
            self.cohort_members[co.id] = []
            for name in co.courses:
                k = norm_key(name)
                if k in course_keys:
                    self.cohort_members[co.id].append(course_keys[k])
                    cohort_of[k].append(co.id)

        self.courses: List[Course] = []
        for rec in self.data.courses:
            c = Course()
            c.id, c.key = rec.id, norm_key(rec.id)
            c.context = rec.context.lower()
            c.need = activity_tags(c.context)
            c.mentioned = [self.room_index[k] for k in expand_room_mentions(rec.rooms_text, known)]
            c.preferred_rooms = {self.room_index[k] for k in self.data.preferred_rooms.get(c.key, ())
                                 if k in self.room_index}
            c.instructors = self._resolve_instructors(rec)
            c.cohorts = cohort_of.get(c.key, [])
            c.enrollment = self._enrollment(rec, c)
            self.courses.append(c)
        self.course_by_id = {c.id: c for c in self.courses}

    def _enrollment(self, rec, c) -> int:
        if c.cohorts:
            return sum(self.cohort_size[x] for x in c.cohorts)
        caps = [self.rooms[r].capacity for r in c.mentioned if self.rooms[r].capacity > 0]
        if caps:
            return max(1, int(round(0.75 * min(caps))))
        return DEFAULT_ENROLLMENT["graduate" if rec.level.lower().startswith("grad") else "undergraduate"]

    def type_compatible(self, c, r) -> bool:
        return r in c.mentioned or bool(self.room_tag[r] & c.need)

    def _build_domains(self):
        for c in self.courses:
            c.rooms = [r for r in self.avail_rooms
                       if self.rooms[r].capacity >= c.enrollment and self.type_compatible(c, r)]
            blocked = set().union(*(self.unavail.get(i, set()) for i in c.instructors))
            open_slots = [s for s in range(len(self.slots)) if s not in blocked]
            if not c.rooms or not open_slots:
                raise ValueError(f"{c.id}: no feasible (slot, room) pair")
            c.domain = [(s, r) for s in open_slots for r in c.rooms]

    def _build_graph(self):
        self.tied: Dict[str, Set[str]] = {c.id: set() for c in self.courses}
        self.instructor_members: Dict[str, List[str]] = defaultdict(list)
        for c in self.courses:
            for i in c.instructors:
                self.instructor_members[i].append(c.id)
        for g in list(self.instructor_members.values()) + list(self.cohort_members.values()):
            for a in g:
                self.tied[a].update(b for b in g if b != a)
        room_users: Dict[int, Set[str]] = defaultdict(set)
        for c in self.courses:
            for r in c.rooms:
                room_users[r].add(c.id)
        self.neighbors: Dict[str, Set[str]] = {}
        for c in self.courses:
            nb = set(self.tied[c.id])
            for r in c.rooms:
                nb |= room_users[r]
            nb.discard(c.id)
            self.neighbors[c.id] = nb

    def unary_cost(self, c, val: Value) -> float:
        w, (s, r) = self.w, val
        total = 0.0
        for i in c.instructors:                                   # S1
            p = self.pref.get(i)
            if p and s not in p:
                total += w["S1"]
        excess = self.rooms[r].capacity - c.enrollment            # S2
        if excess > EXCESS_FREE_SEATS:
            total += w["S2"] * (excess - EXCESS_FREE_SEATS) / 10.0
        if c.preferred_rooms:
            if r not in c.preferred_rooms:
                total += w["PREF_ROOM"]
        elif c.mentioned and r not in c.mentioned:
            total += w["HIST_ROOM"]
        if "computer lab" in c.context and "lab" not in self.room_tag[r]:
            total += w["LAB"]
        return total

    def group_cost(self, sessions, is_cohort: bool) -> float:
        """S3/S4/S5 for one cohort (all three) or one instructor (S4 only).
        sessions: [(day, start_min, end_min, building)]"""
        if len(sessions) < 2:
            return 0.0
        w3, w4, w5 = self.w["S3"], self.w["S4"], self.w["S5"]
        days: Dict[int, list] = {}
        for d, st, en, b in sessions:
            days.setdefault(d, []).append((st, en, b))
        total = 0.0
        for lst in days.values():
            if len(lst) < 2:
                continue
            lst.sort()
            run, prev_end, prev_b = 1, lst[0][1], lst[0][2]
            for st, en, b in lst[1:]:
                gap = st - prev_end
                if gap <= BACK_TO_BACK_GAP:
                    run += 1
                    if is_cohort and b != prev_b:
                        total += w5
                else:
                    total += w4 * max(0, run - 2)
                    run = 1
                    if is_cohort:
                        total += w3 * math.ceil(gap / 60.0)
                prev_end = max(prev_end, en)
                prev_b = b
            total += w4 * max(0, run - 2)
        return total

    def session(self, val: Value):
        s, r = val
        return (self.slot_day[s], self.slot_start[s], self.slot_end[s], self.room_building[r])

    def groups(self):
        g = [(True, m) for m in self.cohort_members.values() if len(m) >= 2]
        return g + [(False, m) for m in self.instructor_members.values() if len(m) >= 2]

    def soft_cost(self, assignment: Dict[str, Value]) -> float:
        total = sum(self.unary_cost(self.course_by_id[c], v) for c, v in assignment.items())
        for is_cohort, members in self.groups():
            total += self.group_cost([self.session(assignment[m]) for m in members if m in assignment], is_cohort)
        return total

    def build_csp(self) -> "TimetableCSP":
        return TimetableCSP(self)


class TimetableCSP(CSP):
    """backtracking.CSP with a faster conflict counter."""

    def __init__(self, problem: Problem):
        super().__init__([c.id for c in problem.courses], {c.id: c.domain for c in problem.courses},
                         problem.neighbors, self._constraint)
        self.ov = problem.ov
        self.tied = problem.tied

    def _constraint(self, v1, a, v2, b) -> bool:
        if not self.ov[a[0]][b[0]]:
            return True
        return a[1] != b[1] and v2 not in self.tied[v1]

    def nconflicts(self, var, val, assignment) -> int:
        s, r = val
        ovs, tied, get = self.ov[s], self.tied[var], assignment.get
        cnt = 0
        for nb in self.neighbors[var]:
            o = get(nb)
            if o is not None and ovs[o[0]] and (o[1] == r or nb in tied):
                cnt += 1
        return cnt

    def is_consistent(self, var, val, assignment) -> bool:
        return self.nconflicts(var, val, assignment) == 0
