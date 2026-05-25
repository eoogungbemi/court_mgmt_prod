"""
Seed the Allegheny County Juvenile Court database.

Run after migrations:
    alembic upgrade head
    python db/seed.py
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta, date

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import (
    NUM_COURTROOMS, NUM_LAWYERS,
    COURT_START_HOUR, COURT_END_HOUR,
    BUFFER_BETWEEN_HEARINGS_MINS,
    MAX_LAWYER_HEARINGS_PER_DAY,
    HEARING_DURATIONS, COMPLEXITY_MULTIPLIER,
    ADMIN_USERNAME, ADMIN_PASSWORD,
)
from db.database import SessionLocal
from db.models import Courtroom, Judge, Lawyer, Case, Accused, Hearing, User
from utils.security import hash_password

fake = Faker("en_US")
random.seed(42)
Faker.seed(42)

CASE_TYPE_WEIGHTS = [("delinquency", 0.55), ("dependency", 0.30), ("status_offense", 0.15)]
COMPLEXITY_WEIGHTS = [("low", 0.40), ("medium", 0.40), ("high", 0.20)]
CASE_PREFIX = {"delinquency": "JD", "dependency": "DP", "status_offense": "SO"}


# ── helpers ───────────────────────────────────────────────────────────────────

def weighted_choice(choices: list[tuple]) -> str:
    items, weights = zip(*choices)
    return random.choices(items, weights=weights, k=1)[0]


def sample_duration(case_type: str, hearing_type: str, complexity: str) -> int:
    lo, hi = HEARING_DURATIONS[case_type][hearing_type]
    base = random.randint(lo, hi)
    return max(5, int(base * COMPLEXITY_MULTIPLIER[complexity]))


def workweek_dates(num_days: int = 5) -> list[date]:
    today = date.today()
    days, d = [], today
    while len(days) < num_days:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def overlaps(s_a, e_a, s_b, e_b) -> bool:
    return s_a < e_b and s_b < e_a


def find_available_lawyer(
    lawyers: list[Lawyer],
    start: datetime,
    end: datetime,
    day_schedule: dict,
    day_counts: dict,
) -> Lawyer | None:
    candidates = [l for l in lawyers if day_counts[l.id] < MAX_LAWYER_HEARINGS_PER_DAY]
    random.shuffle(candidates)
    for lawyer in candidates:
        if not any(overlaps(start, end, s, e) for s, e in day_schedule[lawyer.id]):
            return lawyer
    return None


# ── creators ──────────────────────────────────────────────────────────────────

def create_courtrooms(db: Session) -> list[Courtroom]:
    rooms = []
    for i in range(1, NUM_COURTROOMS + 1):
        floor = ((i - 1) // 5) + 1
        room = Courtroom(name=f"Juvenile Court - Room {i}", floor=floor)
        db.add(room)
        rooms.append(room)
    db.flush()
    return rooms


def create_judges(db: Session, courtrooms: list[Courtroom]) -> list[Judge]:
    judges = []
    for room in courtrooms:
        judge = Judge(name=f"Hon. {fake.last_name()}", courtroom_id=room.id)
        db.add(judge)
        judges.append(judge)
    db.flush()
    return judges


def create_lawyers(db: Session) -> list[Lawyer]:
    lawyers = []
    for _ in range(NUM_LAWYERS):
        bar = f"PA-{random.randint(100000, 999999)}"
        lawyer = Lawyer(
            name=f"{fake.first_name()} {fake.last_name()}, Esq.",
            bar_number=bar,
            phone=fake.phone_number(),
            email=fake.ascii_company_email(),
        )
        db.add(lawyer)
        lawyers.append(lawyer)

    # Pro se placeholder — must exist for self-represented juveniles
    db.add(Lawyer(name="Self-Represented (Pro Se)", bar_number="PRO-SE"))
    db.flush()
    return lawyers


def create_hearing(
    db: Session,
    courtroom: Courtroom,
    judge: Judge,
    start: datetime,
    case_number: str,
    case_type: str,
    hearing_type: str,
    complexity: str,
    lawyer: Lawyer,
    duration_mins: int,
) -> Hearing:
    end = start + timedelta(minutes=duration_mins)
    case = Case(
        case_number=case_number,
        case_type=case_type,
        complexity=complexity,
        status="active",
        defense_lawyer_id=lawyer.id,
    )
    db.add(case)
    db.flush()

    db.add(Accused(name=fake.name(), case_id=case.id, phone=fake.phone_number()))

    hearing = Hearing(
        case_id=case.id,
        courtroom_id=courtroom.id,
        judge_id=judge.id,
        hearing_type=hearing_type,
        scheduled_start=start,
        scheduled_end=end,
        estimated_duration_mins=duration_mins,
        status="scheduled",
    )
    db.add(hearing)
    db.flush()
    return hearing


def schedule_courtroom_day(
    db: Session,
    courtroom: Courtroom,
    judge: Judge,
    hearing_date: date,
    lawyers: list[Lawyer],
    day_schedule: dict,
    day_counts: dict,
    case_counters: dict,
) -> int:
    current = datetime(hearing_date.year, hearing_date.month, hearing_date.day,
                       COURT_START_HOUR, 0)
    end_of_day = datetime(hearing_date.year, hearing_date.month, hearing_date.day,
                          COURT_END_HOUR, 0)
    created = 0

    while current < end_of_day:
        case_type    = weighted_choice(CASE_TYPE_WEIGHTS)
        hearing_type = random.choice(list(HEARING_DURATIONS[case_type].keys()))
        complexity   = weighted_choice(COMPLEXITY_WEIGHTS)
        duration     = sample_duration(case_type, hearing_type, complexity)

        slot_end = current + timedelta(minutes=duration)
        if slot_end > end_of_day:
            break

        lawyer = find_available_lawyer(
            [l for l in lawyers if l.bar_number != "PRO-SE"],
            current, slot_end, day_schedule, day_counts,
        )
        if lawyer is None:
            current += timedelta(minutes=30)
            continue

        prefix = CASE_PREFIX[case_type]
        case_counters[prefix] += 1
        case_number = f"{hearing_date.year}-{prefix}-{case_counters[prefix]:05d}"

        create_hearing(
            db=db, courtroom=courtroom, judge=judge, start=current,
            case_number=case_number, case_type=case_type,
            hearing_type=hearing_type, complexity=complexity,
            lawyer=lawyer, duration_mins=duration,
        )

        day_schedule[lawyer.id].append((current, slot_end))
        day_counts[lawyer.id] += 1
        current = slot_end + timedelta(minutes=BUFFER_BETWEEN_HEARINGS_MINS)
        created += 1

    return created


def create_admin_user(db: Session) -> None:
    if db.execute(
        select(User).where(User.username == ADMIN_USERNAME)
    ).scalar_one_or_none():
        print(f"  Admin user '{ADMIN_USERNAME}' already exists — skipped.")
        return
    db.add(User(
        username=ADMIN_USERNAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        role="admin",
    ))
    db.commit()
    print(f"  Admin user '{ADMIN_USERNAME}' created.")


# ── entry point ───────────────────────────────────────────────────────────────

def seed(db: Session) -> None:
    print("Seeding Allegheny County Juvenile Court database...")

    courtrooms = create_courtrooms(db)
    judges     = create_judges(db, courtrooms)
    lawyers    = create_lawyers(db)

    courtroom_judge = list(zip(courtrooms, judges))
    work_days       = workweek_dates(5)
    case_counters: dict[str, int] = defaultdict(int)
    total_hearings  = 0

    for day in work_days:
        day_schedule: dict[int, list] = defaultdict(list)
        day_counts:   dict[int, int]  = defaultdict(int)
        day_total = 0

        for room, judge in courtroom_judge:
            day_total += schedule_courtroom_day(
                db=db, courtroom=room, judge=judge,
                hearing_date=day, lawyers=lawyers,
                day_schedule=day_schedule, day_counts=day_counts,
                case_counters=case_counters,
            )

        db.commit()
        print(f"  {day.strftime('%A %Y-%m-%d')}: {day_total} hearings")
        total_hearings += day_total

    print(f"\nDone. {total_hearings} hearings | "
          f"{NUM_COURTROOMS} rooms | {NUM_LAWYERS} attorneys")

    create_admin_user(db)


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
