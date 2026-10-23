"""
timetable_model.py

Turns a Dataset into a CSP.

Variables : one per course (one weekly session per course -> one output row).
Domains   : (slot_index, room_index) pairs that satisfy every *unary* hard rule
            (room availability, testing-centre block, capacity, room type,
            instructor unavailability).
Binary hard constraints (between two courses A and B whose times overlap):
            H1 same room, H3 shared instructor, H5 shared cohort.
            "Overlap" is real time overlap, not slot-id equality, because the
            timetable contains overlapping slots (e.g. 13:00-14:15 vs 14:00-15:15).
H6        : enforced by search (every variable must be assigned).
Soft      : S1..S5 plus room-preference terms; see Problem.unary / group_cost.
"""

import math
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from backtracking import CSP
from data_loader import Dataset, norm_key, resolve_slot_tokens, split_items

Value = Tuple[int, int]   # (slot_idx, room_idx)

DEFAULT_WEIGHTS = {
    "S1": 10.0,          # instructor preferred slots
    "S2": 5.0,           # oversized room (per 10 excess seats beyond 30)
    "S3": 8.0,           # cohort idle gap (per started hour)
    "S4": 12.0,          # >2 back-to-back sessions (per extra session)
    "S5": 6.0,           # back-to-back in different buildings
    "PREF_ROOM": 15.0,   # constraints.csv "Preferred" room requests (C006-C008)
    "HIST_ROOM": 3.0,    # not in a room the course historically used (C011)
    "TYPE": 25.0,        # room type had to be relaxed to find any room
    "LAB": 4.0,          # computer-lab course not in a lab-type room (C009)
}
EXCESS_FREE_SEATS = 30      # S2: unused seats tolerated before penalising
BACK_TO_BACK_GAP = 20       # minutes; gap <= this counts as "back-to-back"
DEFAULT_ENROLLMENT = {"graduate": 20, "undergraduate": 25}


# --------------------------------------------------------------------------- #
# Room mention expansion  ("TECH 201/202/203/204" -> 4 rooms)
# --------------------------------------------------------------------------- #
def expand_room_mentions(text: str, known: Set[str]) -> List[str]:
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


# --------------------------------------------------------------------------- #
# Room type <-> activity compatibility (H2, type half)
# --------------------------------------------------------------------------- #
def room_tags(room) -> Set[str]:
    t = room.room_type.lower()
    tags = set()
    for tag, kw in (("auditorium", "auditorium"), ("lecture", "lecture"), ("classroom", "classroom"),
                    ("lab", "lab"), ("computer", "computer"), ("specialized", "specialized"),
                    ("specialized", "evl")):
        if kw in t:
            tags.add(tag)
    return tags


def activity_tags(context: str) -> Set[str]:
    """Which room tags can host a course, judged from its scheduling_context."""
    need: Set[str] = set()
    general = {"classroom", "lecture", "lab", "specialized"}
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
    def __init__(self, data: Dataset, weights: Dict[str, float] = None):
        self.data = data
        self.w = dict(DEFAULT_WEIGHTS)
        self.w.update(data.weights)
        if weights:
            self.w.update(weights)
        self.warnings: List[str] = list(data.warnings)

        self._build_slots()
        self._build_rooms()
        self._build_people()
        self._build_courses()
        self._build_domains()
        self._build_graph()
        self._build_unary()

    # ------------------------------------------------------------------ slots
    def _build_slots(self):
        S = self.data.slots
        self.slots = S
        n = len(S)
        self.slot_day = [s.day_idx for s in S]
        self.slot_start = [s.start_min for s in S]
        self.slot_end = [s.end_min for s in S]
        self.ov = [[False] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                self.ov[i][j] = (S[i].day_idx == S[j].day_idx and
                                 S[i].start_min < S[j].end_min and S[j].start_min < S[i].end_min)
        self.ovset = [frozenset(j for j in range(n) if self.ov[i][j]) for i in range(n)]

    # ------------------------------------------------------------------ rooms
    def _build_rooms(self):
        R = self.data.rooms
        self.rooms = R
        self.room_index = {norm_key(r.id): i for i, r in enumerate(R)}
        buildings = {}
        self.room_building = [buildings.setdefault(r.building.upper(), len(buildings)) for r in R]
        self.room_tag = [room_tags(r) for r in R]
        self.avail_rooms = [i for i, r in enumerate(R)
                            if r.available and norm_key(r.id) not in self.data.blocked_rooms and r.capacity > 0]
        if not self.avail_rooms:
            raise ValueError("No rooms are available for regular classes")

    # ----------------------------------------------------------------- people
    def _build_people(self):
        D = self.data
        self.unavail: Dict[str, Set[int]] = {}
        self.pref: Dict[str, Set[int]] = {}
        self.instructor_name: Dict[str, str] = {}
        self.by_name: Dict[str, list] = defaultdict(list)
        for rec in D.instructors:
            self.by_name[norm_key(rec.name)].append(rec)
            self.instructor_name[rec.id] = rec.name
            self.unavail[rec.id] = resolve_slot_tokens(rec.unavailable, self.slots)
            self.pref[rec.id] = resolve_slot_tokens(rec.preferred, self.slots)
        self.inst_course_keys = {rec.id: {norm_key(c) for c in rec.courses} for rec in D.instructors}

    def _resolve_instructors(self, rec) -> List[str]:
        ids: List[str] = []
        ck = norm_key(rec.id)
        for name in rec.instructors:
            cands = self.by_name.get(norm_key(name))
            if cands:
                match = [x for x in cands if ck in self.inst_course_keys[x.id]] or cands[:1]
                for x in match:
                    if x.id not in ids:
                        ids.append(x.id)
            else:
                synth = "INSTR_" + re.sub(r"\W+", "_", name.strip()).upper()
                self.instructor_name.setdefault(synth, name)
                self.unavail.setdefault(synth, set())
                self.pref.setdefault(synth, set())
                if synth not in ids:
                    ids.append(synth)
        for iid, keys in self.inst_course_keys.items():   # instructors.csv -> course
            if ck in keys and iid not in ids:
                ids.append(iid)
        return ids

    # ---------------------------------------------------------------- courses
    def _build_courses(self):
        D = self.data
        known = set(self.room_index)
        cohort_of: Dict[str, List[int]] = defaultdict(list)
        self.cohort_members: Dict[str, List[str]] = {}
        course_keys = {norm_key(c.id): c.id for c in D.courses}
        self.cohort_size = {}
        for co in D.cohorts:
            self.cohort_size[co.id] = co.size
            members = []
            for cname in co.courses:
                k = norm_key(cname)
                if k in course_keys:
                    members.append(course_keys[k])
                    cohort_of[k].append(co.id)
                else:
                    self.warnings.append(f"Cohort {co.id}: course '{cname}' not in courses.csv (ignored)")
            self.cohort_members[co.id] = members

        self.courses: List[Course] = []
        for rec in D.courses:
            c = Course()
            c.id, c.key, c.level = rec.id, norm_key(rec.id), rec.level
            c.context = rec.context.lower()
            c.required_type = rec.required_type.lower()
            c.mentioned = [self.room_index[k] for k in expand_room_mentions(rec.rooms_text, known)]
            c.preferred_rooms = {self.room_index[k] for k in D.preferred_rooms.get(c.key, ())
                                 if k in self.room_index}
            c.instructors = self._resolve_instructors(rec)
            c.cohorts = cohort_of.get(c.key, [])
            c.enrollment_source, c.enrollment = self._enrollment(rec, c)
            c.enrollment_requested = c.enrollment
            self.courses.append(c)
        self.course_by_id = {c.id: c for c in self.courses}

    def _enrollment(self, rec, c):
        if rec.enrollment is not None:
            return "csv", rec.enrollment
        if c.cohorts:                                   # shared course: students add up
            return "cohort", sum(self.cohort_size[x] for x in c.cohorts)
        caps = [self.rooms[r].capacity for r in c.mentioned if self.rooms[r].capacity > 0]
        if caps:                                        # historical room => 75% fill
            return "estimate", max(1, int(round(0.75 * min(caps))))
        lvl = "graduate" if rec.level.lower().startswith("grad") else "undergraduate"
        return "default", DEFAULT_ENROLLMENT[lvl]

    # ---------------------------------------------------------------- domains
    def type_compatible(self, c, r) -> bool:
        if r in c.mentioned:
            return True
        if c.required_type:
            rt = self.rooms[r].room_type.lower()
            return c.required_type in rt or rt in c.required_type
        return bool(self.room_tag[r] & activity_tags(c.context))

    def _candidate_rooms(self, c):
        avail = self.avail_rooms
        cap = lambda r: self.rooms[r].capacity
        a = [r for r in avail if cap(r) >= c.enrollment and self.type_compatible(c, r)]
        if a:
            return a, 0
        b = [r for r in avail if cap(r) >= c.enrollment]
        if b:
            self.warnings.append(f"{c.id}: no type-compatible room; room type relaxed")
            return b, 1
        mx = max(cap(r) for r in avail)
        self.warnings.append(f"{c.id}: enrollment {c.enrollment} exceeds every room; capped to {mx}")
        c.enrollment = mx
        t = [r for r in avail if cap(r) >= mx and self.type_compatible(c, r)]
        return (t or [r for r in avail if cap(r) >= mx]), 2

    def _build_domains(self):
        all_slots = set(range(len(self.slots)))
        for c in self.courses:
            c.rooms, c.tier = self._candidate_rooms(c)
            blocked: Set[int] = set()
            for i in c.instructors:
                blocked |= self.unavail.get(i, set())
            ok = sorted(all_slots - blocked)
            if not ok:
                self.warnings.append(f"{c.id}: instructors unavailable in every slot; H4 relaxed")
                ok = sorted(all_slots)
            c.domain = [(s, r) for s in ok for r in c.rooms]

    # ------------------------------------------------------------------ graph
    def _build_graph(self):
        ids = [c.id for c in self.courses]
        self.tied: Dict[str, Set[str]] = {i: set() for i in ids}        # share instructor / cohort
        self.instructor_members: Dict[str, List[str]] = defaultdict(list)
        for c in self.courses:
            for i in c.instructors:
                self.instructor_members[i].append(c.id)
        groups = list(self.instructor_members.values()) + list(self.cohort_members.values())
        for g in groups:
            for a in g:
                for b in g:
                    if a != b:
                        self.tied[a].add(b)
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

    # ------------------------------------------------------------ soft costs
    def unary_terms(self, c, val: Value, acc=None) -> float:
        w = self.w
        s, r = val
        total = 0.0

        def add(key, amount):
            nonlocal total
            if amount:
                total += amount
                if acc is not None:
                    acc[key] += amount

        for i in c.instructors:                       # S1
            p = self.pref.get(i)
            if p and s not in p:
                add("S1", w["S1"])
        excess = self.rooms[r].capacity - c.enrollment  # S2
        if excess > EXCESS_FREE_SEATS:
            add("S2", w["S2"] * (excess - EXCESS_FREE_SEATS) / 10.0)
        if c.preferred_rooms:                         # C006-C008
            if r not in c.preferred_rooms:
                add("ROOM_REQUEST", w["PREF_ROOM"])
        elif c.mentioned and r not in c.mentioned:    # C011
            add("HISTORICAL_ROOM", w["HIST_ROOM"])
        if not self.type_compatible(c, r):
            add("ROOM_TYPE", w["TYPE"])
        if "computer lab" in c.context and "lab" not in self.room_tag[r]:   # C009
            add("COMPUTER_LAB", w["LAB"])
        return total

    def _build_unary(self):
        self.unary: Dict[str, Dict[Value, float]] = {
            c.id: {v: self.unary_terms(c, v) for v in c.domain} for c in self.courses}

    def group_cost(self, sessions, is_cohort: bool, acc=None) -> float:
        """
        sessions: list of (day_idx, start_min, end_min, building_idx) for ONE cohort
        or ONE instructor.  S3/S5 apply to cohorts only; S4 to both.
        """
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
                        if acc is not None:
                            acc["S5"] += w5
                else:
                    if run > 2:
                        total += w4 * (run - 2)
                        if acc is not None:
                            acc["S4"] += w4 * (run - 2)
                    run = 1
                    if is_cohort:
                        x = w3 * math.ceil(gap / 60.0)
                        total += x
                        if acc is not None:
                            acc["S3"] += x
                if en > prev_end:
                    prev_end = en
                prev_b = b
            if run > 2:
                total += w4 * (run - 2)
                if acc is not None:
                    acc["S4"] += w4 * (run - 2)
        return total

    def session(self, val: Value):
        s, r = val
        return (self.slot_day[s], self.slot_start[s], self.slot_end[s], self.room_building[r])

    def groups(self):
        """[(is_cohort, [course ids])] for every cohort / instructor with >= 2 courses."""
        g = [(True, m) for m in self.cohort_members.values() if len(m) >= 2]
        g += [(False, m) for m in self.instructor_members.values() if len(m) >= 2]
        return g

    def soft_cost(self, assignment: Dict[str, Value], acc=None) -> float:
        total = 0.0
        for cid, val in assignment.items():
            total += self.unary_terms(self.course_by_id[cid], val, acc)
        for is_cohort, members in self.groups():
            sess = [self.session(assignment[m]) for m in members if m in assignment]
            total += self.group_cost(sess, is_cohort, acc)
        return total

    # --------------------------------------------------------------- CSP glue
    def build_csp(self) -> "TimetableCSP":
        return TimetableCSP(self)


class TimetableCSP(CSP):
    """Your generic CSP with a fast, timetable-specific conflict counter."""

    def __init__(self, problem: Problem):
        ids = [c.id for c in problem.courses]
        super().__init__(ids, {c.id: c.domain for c in problem.courses},
                         problem.neighbors, self._constraint)
        self.problem = problem
        self.ov = problem.ov
        self.tied = problem.tied

    def _constraint(self, v1, a, v2, b) -> bool:
        if not self.ov[a[0]][b[0]]:
            return True
        if a[1] == b[1]:
            return False                      # H1 room clash
        return v2 not in self.tied[v1]        # H3 instructor / H5 cohort clash

    def nconflicts(self, var, val, assignment) -> int:
        s, r = val
        ovs = self.ov[s]
        tied = self.tied[var]
        cnt = 0
        get = assignment.get
        for nb in self.neighbors[var]:
            o = get(nb)
            if o is not None and ovs[o[0]] and (o[1] == r or nb in tied):
                cnt += 1
        return cnt

    def is_consistent(self, var, val, assignment) -> bool:
        return self.nconflicts(var, val, assignment) == 0


# --------------------------------------------------------------------------- #
# Independent validator (does not use the CSP machinery)
# --------------------------------------------------------------------------- #
def validate(problem: Problem, assignment: Dict[str, Value]) -> Dict[str, List[str]]:
    P = problem
    out: Dict[str, List[str]] = {k: [] for k in ("H1", "H2", "H3", "H4", "H5", "H6")}
    for c in P.courses:
        if c.id not in assignment:
            out["H6"].append(f"{c.id} unscheduled")
            continue
        s, r = assignment[c.id]
        room = P.rooms[r]
        if (not room.available) or norm_key(room.id) in P.data.blocked_rooms:
            out["H2"].append(f"{c.id} in unavailable room {room.id}")
        if room.capacity < c.enrollment:
            out["H2"].append(f"{c.id} enrollment {c.enrollment} > capacity {room.capacity} ({room.id})")
        for i in c.instructors:
            if s in P.unavail.get(i, ()):
                out["H4"].append(f"{c.id}: instructor {i} unavailable in {P.slots[s].id}")
    cs = [c for c in P.courses if c.id in assignment]
    for x in range(len(cs)):
        for y in range(x + 1, len(cs)):
            a, b = cs[x], cs[y]
            (s1, r1), (s2, r2) = assignment[a.id], assignment[b.id]
            if not P.ov[s1][s2]:
                continue
            if r1 == r2:
                out["H1"].append(f"{a.id} & {b.id} share room {P.rooms[r1].id} at {P.slots[s1].id}/{P.slots[s2].id}")
            if set(a.instructors) & set(b.instructors):
                out["H3"].append(f"{a.id} & {b.id} share an instructor at {P.slots[s1].id}/{P.slots[s2].id}")
            if set(a.cohorts) & set(b.cohorts):
                out["H5"].append(f"{a.id} & {b.id} share a cohort at {P.slots[s1].id}/{P.slots[s2].id}")
    return out
