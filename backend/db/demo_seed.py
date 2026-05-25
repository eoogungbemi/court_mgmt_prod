"""
Populate today's docket with realistic demo data so that all dashboard
panels show numbers on first launch.

Idempotent — safe to run multiple times (checks for existing today's hearings
in each room before inserting).

Usage:
    alembic upgrade head
    python db/seed.py          # creates rooms/lawyers/judges/users if absent
    python db/demo_seed.py     # adds today's rich hearing data
"""

import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import (
    Accused, Case, Courtroom, ETAEstimate, Hearing, Judge, Lawyer,
    LawyerConflict, User,
)
from utils.security import hash_password

fake = Faker("en_US")
random.seed(0)
Faker.seed(0)

TODAY = date.today()
TZ    = timezone.utc

HEARING_TYPES = [
    "arraignment", "detention", "adjudicatory",
    "dispositional", "review", "status_conference",
]

CASE_TYPES = [
    ("delinquency",   0.55),
    ("dependency",    0.30),
    ("status_offense", 0.15),
]

COMPLEXITY = [("low", 0.40), ("medium", 0.40), ("high", 0.20)]

DURATION_RANGE = {
    "low":    (15, 30),
    "medium": (30, 60),
    "high":   (60, 90),
}

CASE_PREFIX = {"delinquency": "JD", "dependency": "DP", "status_offense": "SO"}

_case_counter: dict[str, int] = defaultdict(int)


def _wc(choices):
    items, weights = zip(*choices)
    return random.choices(items, weights=weights, k=1)[0]


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(TODAY.year, TODAY.month, TODAY.day, h, m, tzinfo=TZ)


def _ensure_users(db: Session, lawyers: list[Lawyer], judges: list[Judge]) -> None:
    """Create one user per role for demo login if not already present."""
    demo_users = [
        ("demo_admin",    "Admin1234",    "admin",    None, None),
        ("demo_clerk",    "Clerk1234",    "clerk",    None, None),
        ("demo_judge",    "Judge1234",    "judge",    None, judges[0].id if judges else None),
        ("demo_attorney", "Attorney1234", "attorney", lawyers[0].id if lawyers else None, None),
        ("demo_public",   "Public1234",   "public",   None, None),
    ]
    for username, password, role, lawyer_id, judge_id in demo_users:
        if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
            continue
        db.add(User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            lawyer_id=lawyer_id,
            judge_id=judge_id,
        ))
    db.commit()
    print("  Demo users: demo_admin / demo_clerk / demo_judge / demo_attorney / demo_public (pw: <Role>1234)")


def _make_case(db: Session, lawyer: Lawyer) -> Case:
    case_type  = _wc(CASE_TYPES)
    complexity = _wc(COMPLEXITY)
    prefix     = CASE_PREFIX[case_type]
    _case_counter[prefix] += 1
    case_number = f"{TODAY.year}-{prefix}-DEMO{_case_counter[prefix]:04d}"

    existing = db.execute(select(Case).where(Case.case_number == case_number)).scalar_one_or_none()
    if existing:
        return existing

    case = Case(
        case_number=case_number,
        case_type=case_type,
        complexity=complexity,
        status="active",
        defense_lawyer_id=lawyer.id,
        is_confidential=random.random() < 0.1,
    )
    db.add(case)
    db.flush()
    db.add(Accused(name=fake.name(), case_id=case.id, phone=fake.phone_number()))
    db.flush()
    return case


def _add_eta(db: Session, hearing: Hearing, offset_mins: int) -> None:
    p25 = max(5, hearing.estimated_duration_mins - 5)
    p75 = hearing.estimated_duration_mins + 10
    db.add(ETAEstimate(
        hearing_id=hearing.id,
        estimated_start=hearing.scheduled_start + timedelta(minutes=offset_mins),
        p25_mins=p25,
        p75_mins=p75,
        rationale="Demo seed — representative estimate for dashboard display.",
        agent_name="DurationEstimatorAgent",
    ))


def _seed_room(
    db: Session,
    room: Courtroom,
    judge: Judge,
    lawyers: list[Lawyer],
    now_hour: int,
) -> list[Hearing]:
    existing = db.execute(
        select(Hearing).where(
            Hearing.courtroom_id == room.id,
            Hearing.scheduled_start >= _dt(8),
            Hearing.scheduled_start < _dt(17),
        )
    ).scalars().all()
    if existing:
        return existing

    hearings: list[Hearing] = []
    current = _dt(8, 30)
    end_of_day = _dt(16, 30)
    lawyer_pool = [l for l in lawyers if l.bar_number != "PRO-SE"]
    lawyer_slots: dict[int, list] = defaultdict(list)
    now = _dt(now_hour)

    while current < end_of_day:
        complexity  = _wc(COMPLEXITY)
        lo, hi      = DURATION_RANGE[complexity]
        duration    = random.randint(lo, hi)
        slot_end    = current + timedelta(minutes=duration)
        if slot_end > end_of_day:
            break

        # Pick a lawyer not already busy in this slot
        candidates = [l for l in lawyer_pool
                      if not any(s < slot_end and current < e for s, e in lawyer_slots[l.id])]
        if not candidates:
            current += timedelta(minutes=15)
            continue
        lawyer = random.choice(candidates)
        lawyer_slots[lawyer.id].append((current, slot_end))

        case = _make_case(db, lawyer)
        hearing_type = random.choice(HEARING_TYPES)

        hearing = Hearing(
            case_id=case.id,
            courtroom_id=room.id,
            judge_id=judge.id,
            hearing_type=hearing_type,
            scheduled_start=current,
            scheduled_end=slot_end,
            estimated_duration_mins=duration,
            status="scheduled",
            interpreter_required=random.random() < 0.15,
        )

        # Assign realistic status based on time-of-day simulation
        if slot_end < now:
            # Hearing already done
            variance = random.randint(-5, 8)
            actual_dur = max(5, duration + variance)
            hearing.actual_start = current + timedelta(minutes=random.randint(0, 3))
            hearing.actual_end   = hearing.actual_start + timedelta(minutes=actual_dur)
            hearing.status = "completed" if random.random() < 0.85 else "cancelled"
            hearing.lawyer_checked_in  = True
            hearing.accused_checked_in = True
        elif current <= now < slot_end:
            # Currently in progress
            hearing.actual_start = current + timedelta(minutes=random.randint(0, 5))
            hearing.status = random.choice(["in_progress", "delayed"])
            hearing.lawyer_checked_in  = True
            hearing.accused_checked_in = random.random() < 0.8
        else:
            # Future
            hearing.status = "scheduled"

        db.add(hearing)
        db.flush()

        # Add AI ETA estimate for all non-cancelled hearings
        if hearing.status != "cancelled":
            _add_eta(db, hearing, offset_mins=random.randint(-2, 5))

        hearings.append(hearing)
        current = slot_end + timedelta(minutes=5)

    return hearings


def _seed_conflict(db: Session, all_hearings: list[Hearing], lawyers: list[Lawyer]) -> None:
    """Create 2-3 artificial conflicts so the conflict panel shows data."""
    lawyer_to_hearings: dict[int, list[Hearing]] = defaultdict(list)
    for h in all_hearings:
        if h.status in ("scheduled", "in_progress"):
            lawyer_to_hearings[h.case.defense_lawyer_id].append(h)

    conflicts_added = 0
    for lawyer_id, hs in lawyer_to_hearings.items():
        if conflicts_added >= 3:
            break
        if len(hs) < 2:
            continue
        ha, hb = hs[0], hs[1]
        overlap_start = max(ha.scheduled_start, hb.scheduled_start)
        overlap_end   = min(ha.scheduled_end,   hb.scheduled_end)
        if overlap_start >= overlap_end:
            continue

        existing = db.execute(
            select(LawyerConflict).where(
                LawyerConflict.lawyer_id    == lawyer_id,
                LawyerConflict.hearing_a_id == ha.id,
                LawyerConflict.hearing_b_id == hb.id,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        db.add(LawyerConflict(
            lawyer_id=lawyer_id,
            hearing_a_id=ha.id,
            hearing_b_id=hb.id,
            overlap_start=overlap_start,
            overlap_end=overlap_end,
            resolved=conflicts_added == 0,  # first one already resolved
        ))
        conflicts_added += 1

    db.flush()


def demo_seed(db: Session) -> None:
    print(f"Demo seeding today's docket ({TODAY}) ...")

    rooms   = db.execute(select(Courtroom)).scalars().all()
    judges  = db.execute(select(Judge)).scalars().all()
    lawyers = db.execute(select(Lawyer)).scalars().all()

    if not rooms or not judges or not lawyers:
        print("  ERROR: No rooms/judges/lawyers found. Run `python db/seed.py` first.")
        return

    judge_map = {j.courtroom_id: j for j in judges}
    now_hour  = datetime.now(TZ).hour  # simulate "current time" for status assignment

    all_hearings: list[Hearing] = []
    for room in rooms:
        judge = judge_map.get(room.id)
        if not judge:
            continue
        hs = _seed_room(db, room, judge, lawyers, now_hour)
        all_hearings.extend(hs)
        print(f"  {room.name}: {len(hs)} hearings")

    db.commit()

    # Reload with relationships for conflict seeding
    all_hearings = db.execute(select(Hearing)).scalars().all()
    _seed_conflict(db, all_hearings, lawyers)
    db.commit()

    _ensure_users(db, lawyers, judges)

    completed = sum(1 for h in all_hearings if h.status == "completed")
    total     = len(all_hearings)
    print(f"\nDone. {total} hearings today | {completed} completed | "
          f"{len(rooms)} rooms | {len(lawyers)} attorneys")
    print("Analytics dashboard should now display live data.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        demo_seed(db)
    finally:
        db.close()
