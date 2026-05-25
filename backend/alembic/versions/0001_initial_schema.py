"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision      = "0001"
down_revision = None
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "courtrooms",
        sa.Column("id",    sa.Integer(), primary_key=True),
        sa.Column("name",  sa.String(),  nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
    )

    op.create_table(
        "judges",
        sa.Column("id",           sa.Integer(), primary_key=True),
        sa.Column("name",         sa.String(),  nullable=False),
        sa.Column("courtroom_id", sa.Integer(), sa.ForeignKey("courtrooms.id"),
                  unique=True, nullable=False),
    )

    op.create_table(
        "lawyers",
        sa.Column("id",         sa.Integer(), primary_key=True),
        sa.Column("name",       sa.String(),  nullable=False),
        sa.Column("bar_number", sa.String(),  unique=True, nullable=False),
        sa.Column("phone",      sa.String(),  nullable=True),
        sa.Column("email",      sa.String(),  nullable=True),
    )

    op.create_table(
        "cases",
        sa.Column("id",                sa.Integer(), primary_key=True),
        sa.Column("case_number",       sa.String(),  unique=True, nullable=False),
        sa.Column("case_type",         sa.String(),  nullable=False),
        sa.Column("complexity",        sa.String(),  nullable=False),
        sa.Column("status",            sa.String(),  server_default="active"),
        sa.Column("is_confidential",   sa.Boolean(), server_default=sa.false()),
        sa.Column("defense_lawyer_id", sa.Integer(), sa.ForeignKey("lawyers.id"),
                  nullable=False),
    )

    op.create_table(
        "accused",
        sa.Column("id",             sa.Integer(), primary_key=True),
        sa.Column("name",           sa.String(),  nullable=False),
        sa.Column("case_id",        sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("phone",          sa.String(),  nullable=True),
        sa.Column("guardian_name",  sa.String(),  nullable=True),
        sa.Column("guardian_phone", sa.String(),  nullable=True),
    )

    op.create_table(
        "hearings",
        sa.Column("id",           sa.Integer(), primary_key=True),
        sa.Column("case_id",      sa.Integer(), sa.ForeignKey("cases.id"),     nullable=False),
        sa.Column("courtroom_id", sa.Integer(), sa.ForeignKey("courtrooms.id"), nullable=False),
        sa.Column("judge_id",     sa.Integer(), sa.ForeignKey("judges.id"),    nullable=False),

        sa.Column("hearing_type",            sa.String(),              nullable=False),
        sa.Column("scheduled_start",         sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end",           sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_duration_mins", sa.Integer(),             nullable=False),

        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end",   sa.DateTime(timezone=True), nullable=True),

        sa.Column("status",              sa.String(),  server_default="scheduled", nullable=False),
        sa.Column("lawyer_checked_in",  sa.Boolean(), server_default=sa.false()),
        sa.Column("accused_checked_in", sa.Boolean(), server_default=sa.false()),
        sa.Column("notes",              sa.Text(),    nullable=True),

        sa.Column("interpreter_required", sa.Boolean(), server_default=sa.false()),
        sa.Column("detention_status",     sa.String(),  nullable=True),
    )

    op.create_table(
        "eta_estimates",
        sa.Column("id",              sa.Integer(), primary_key=True),
        sa.Column("hearing_id",      sa.Integer(), sa.ForeignKey("hearings.id"), nullable=False),
        sa.Column("estimated_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("p25_mins",        sa.Integer(), nullable=False),
        sa.Column("p75_mins",        sa.Integer(), nullable=False),
        sa.Column("rationale",       sa.Text(),    nullable=True),
        sa.Column("generated_at",    sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("agent_name",      sa.String(),  nullable=False),
    )

    op.create_table(
        "lawyer_conflicts",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("lawyer_id",     sa.Integer(), sa.ForeignKey("lawyers.id"),  nullable=False),
        sa.Column("hearing_a_id",  sa.Integer(), sa.ForeignKey("hearings.id"), nullable=False),
        sa.Column("hearing_b_id",  sa.Integer(), sa.ForeignKey("hearings.id"), nullable=False),
        sa.Column("overlap_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overlap_end",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved",      sa.Boolean(), server_default=sa.false()),
        sa.Column("detected_at",   sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("lawyer_id", "hearing_a_id", "hearing_b_id",
                            name="uq_conflict"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id",          sa.Integer(), primary_key=True),
        sa.Column("event_type",  sa.String(),  nullable=False),
        sa.Column("agent_name",  sa.String(),  nullable=False),
        sa.Column("entity_type", sa.String(),  nullable=True),
        sa.Column("entity_id",   sa.Integer(), nullable=True),
        sa.Column("payload",     sa.Text(),    nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("username",      sa.String(),  unique=True, nullable=False),
        sa.Column("email",         sa.String(),  unique=True, nullable=True),
        sa.Column("password_hash", sa.String(),  nullable=False),
        sa.Column("role",          sa.String(),  nullable=False),
        sa.Column("lawyer_id",     sa.Integer(), sa.ForeignKey("lawyers.id"), nullable=True),
        sa.Column("judge_id",      sa.Integer(), sa.ForeignKey("judges.id"),  nullable=True),
        sa.Column("is_active",     sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at",    sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("last_login",    sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id",         sa.Integer(), primary_key=True),
        sa.Column("user_id",    sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(),  unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked",    sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("audit_log")
    op.drop_table("lawyer_conflicts")
    op.drop_table("eta_estimates")
    op.drop_table("hearings")
    op.drop_table("accused")
    op.drop_table("cases")
    op.drop_table("lawyers")
    op.drop_table("judges")
    op.drop_table("courtrooms")
