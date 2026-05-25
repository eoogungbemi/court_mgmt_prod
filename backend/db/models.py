from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Court structure ───────────────────────────────────────────────────────────

class Courtroom(Base):
    __tablename__ = "courtrooms"

    id    = Column(Integer, primary_key=True)
    name  = Column(String, nullable=False)
    floor = Column(Integer, nullable=False)

    judge    = relationship("Judge", back_populates="courtroom", uselist=False)
    hearings = relationship("Hearing", back_populates="courtroom")


class Judge(Base):
    __tablename__ = "judges"

    id           = Column(Integer, primary_key=True)
    name         = Column(String, nullable=False)
    courtroom_id = Column(Integer, ForeignKey("courtrooms.id"), unique=True, nullable=False)

    courtroom = relationship("Courtroom", back_populates="judge")
    hearings  = relationship("Hearing", back_populates="judge")
    users     = relationship("User", back_populates="judge")


class Lawyer(Base):
    __tablename__ = "lawyers"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    bar_number = Column(String, unique=True, nullable=False)
    phone      = Column(String, nullable=True)
    email      = Column(String, nullable=True)

    cases = relationship("Case", back_populates="defense_lawyer")
    users = relationship("User", back_populates="lawyer")


# ── Cases & parties ───────────────────────────────────────────────────────────

class Case(Base):
    __tablename__ = "cases"

    id                = Column(Integer, primary_key=True)
    case_number       = Column(String, unique=True, nullable=False)
    case_type         = Column(String, nullable=False)   # delinquency | dependency | status_offense
    complexity        = Column(String, nullable=False)   # low | medium | high
    status            = Column(String, default="active") # active | closed
    is_confidential   = Column(Boolean, default=False)
    defense_lawyer_id = Column(Integer, ForeignKey("lawyers.id"), nullable=False)

    defense_lawyer = relationship("Lawyer", back_populates="cases")
    # Primary respondent shortcut (first by id); use .respondents for all.
    accused        = relationship(
        "Accused", uselist=False, order_by="Accused.id",
        primaryjoin="Case.id == foreign(Accused.case_id)",
        overlaps="respondents",
        viewonly=True,
    )
    respondents = relationship("Accused", back_populates="case", order_by="Accused.id")
    hearings    = relationship("Hearing", back_populates="case")


class Accused(Base):
    """Juvenile respondent.  Multiple rows per case = co-respondents."""
    __tablename__ = "accused"

    id             = Column(Integer, primary_key=True)
    name           = Column(String, nullable=False)
    case_id        = Column(Integer, ForeignKey("cases.id"), nullable=False)
    phone          = Column(String, nullable=True)
    guardian_name  = Column(String, nullable=True)   # parent / legal guardian
    guardian_phone = Column(String, nullable=True)

    case = relationship("Case", back_populates="respondents", overlaps="accused")


# ── Hearings ──────────────────────────────────────────────────────────────────

class Hearing(Base):
    __tablename__ = "hearings"

    id           = Column(Integer, primary_key=True)
    case_id      = Column(Integer, ForeignKey("cases.id"), nullable=False)
    courtroom_id = Column(Integer, ForeignKey("courtrooms.id"), nullable=False)
    judge_id     = Column(Integer, ForeignKey("judges.id"), nullable=False)

    hearing_type             = Column(String, nullable=False)
    scheduled_start          = Column(DateTime(timezone=True), nullable=False)
    scheduled_end            = Column(DateTime(timezone=True), nullable=False)
    estimated_duration_mins  = Column(Integer, nullable=False)

    actual_start = Column(DateTime(timezone=True), nullable=True)
    actual_end   = Column(DateTime(timezone=True), nullable=True)

    # scheduled | in_progress | completed | delayed | cancelled
    status = Column(String, default="scheduled", nullable=False)

    lawyer_checked_in  = Column(Boolean, default=False)
    accused_checked_in = Column(Boolean, default=False)
    notes              = Column(Text, nullable=True)

    # Juvenile-specific fields
    interpreter_required = Column(Boolean, default=False)
    detention_status     = Column(String, nullable=True)  # secure | non_secure | released

    case      = relationship("Case", back_populates="hearings")
    courtroom = relationship("Courtroom", back_populates="hearings")
    judge     = relationship("Judge", back_populates="hearings")
    eta_estimates = relationship("ETAEstimate", back_populates="hearing",
                                 cascade="all, delete-orphan")


# ── AI estimates ──────────────────────────────────────────────────────────────

class ETAEstimate(Base):
    __tablename__ = "eta_estimates"

    id              = Column(Integer, primary_key=True)
    hearing_id      = Column(Integer, ForeignKey("hearings.id"), nullable=False)
    estimated_start = Column(DateTime(timezone=True), nullable=False)
    p25_mins        = Column(Integer, nullable=False)
    p75_mins        = Column(Integer, nullable=False)
    rationale       = Column(Text, nullable=True)
    generated_at    = Column(DateTime(timezone=True), server_default=func.now())
    agent_name      = Column(String, nullable=False)

    hearing = relationship("Hearing", back_populates="eta_estimates")


# ── Conflicts & audit ─────────────────────────────────────────────────────────

class LawyerConflict(Base):
    __tablename__ = "lawyer_conflicts"

    id            = Column(Integer, primary_key=True)
    lawyer_id     = Column(Integer, ForeignKey("lawyers.id"), nullable=False)
    hearing_a_id  = Column(Integer, ForeignKey("hearings.id"), nullable=False)
    hearing_b_id  = Column(Integer, ForeignKey("hearings.id"), nullable=False)
    overlap_start = Column(DateTime(timezone=True), nullable=False)
    overlap_end   = Column(DateTime(timezone=True), nullable=False)
    resolved      = Column(Boolean, default=False)
    detected_at   = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("lawyer_id", "hearing_a_id", "hearing_b_id", name="uq_conflict"),
    )

    lawyer    = relationship("Lawyer",  foreign_keys=[lawyer_id])
    hearing_a = relationship("Hearing", foreign_keys=[hearing_a_id])
    hearing_b = relationship("Hearing", foreign_keys=[hearing_b_id])


class AuditLog(Base):
    __tablename__ = "audit_log"

    id          = Column(Integer, primary_key=True)
    event_type  = Column(String, nullable=False)
    agent_name  = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id   = Column(Integer, nullable=True)
    payload     = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ── Auth ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    username      = Column(String, unique=True, nullable=False)
    email         = Column(String, unique=True, nullable=True)
    password_hash = Column(String, nullable=False)
    # admin | clerk | attorney | judge
    role          = Column(String, nullable=False)
    # Links attorney/judge users to their court records
    lawyer_id     = Column(Integer, ForeignKey("lawyers.id"), nullable=True)
    judge_id      = Column(Integer, ForeignKey("judges.id"), nullable=True)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    last_login    = Column(DateTime(timezone=True), nullable=True)

    lawyer = relationship("Lawyer", back_populates="users")
    judge  = relationship("Judge", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user",
                                  cascade="all, delete-orphan")


class RefreshToken(Base):
    """Stored as SHA-256 hash so a DB breach doesn't expose usable tokens."""
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked    = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")
