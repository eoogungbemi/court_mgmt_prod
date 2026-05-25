"""performance indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16 00:01:00
"""

from alembic import op

revision      = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── hearings ──────────────────────────────────────────────────────────────
    # Primary queue query: all hearings for a courtroom ordered by start time
    op.create_index("ix_hearings_courtroom_start",
                    "hearings", ["courtroom_id", "scheduled_start"])
    # Status filtering (scheduled / in_progress / completed …)
    op.create_index("ix_hearings_status",
                    "hearings", ["status"])
    # FK lookup from cases → hearings
    op.create_index("ix_hearings_case_id",
                    "hearings", ["case_id"])
    # Judge's docket lookup
    op.create_index("ix_hearings_judge_id",
                    "hearings", ["judge_id"])

    # ── cases ─────────────────────────────────────────────────────────────────
    # Attorney case list (most common non-admin query)
    op.create_index("ix_cases_defense_lawyer_id",
                    "cases", ["defense_lawyer_id"])
    # Active / closed filter
    op.create_index("ix_cases_status",
                    "cases", ["status"])
    # Confidential filter (used by sealed-case guard)
    op.create_index("ix_cases_is_confidential",
                    "cases", ["is_confidential"])

    # ── accused ───────────────────────────────────────────────────────────────
    # Respondent lookup per case (FK, SQLAlchemy won't create this automatically)
    op.create_index("ix_accused_case_id",
                    "accused", ["case_id"])

    # ── eta_estimates ─────────────────────────────────────────────────────────
    # Latest ETA per hearing (ordered by generated_at desc)
    op.create_index("ix_eta_estimates_hearing_generated",
                    "eta_estimates", ["hearing_id", "generated_at"])

    # ── lawyer_conflicts ──────────────────────────────────────────────────────
    op.create_index("ix_lawyer_conflicts_lawyer_id",
                    "lawyer_conflicts", ["lawyer_id"])
    # Unresolved-only filter
    op.create_index("ix_lawyer_conflicts_resolved",
                    "lawyer_conflicts", ["resolved"])

    # ── audit_log ─────────────────────────────────────────────────────────────
    # Per-entity audit trail (entity_type + entity_id)
    op.create_index("ix_audit_log_entity",
                    "audit_log", ["entity_type", "entity_id"])
    # Time-range queries (daily export, compliance review)
    op.create_index("ix_audit_log_created_at",
                    "audit_log", ["created_at"])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    # Revoke all tokens for a user (password reset / account disable)
    op.create_index("ix_refresh_tokens_user_id",
                    "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id",         table_name="refresh_tokens")
    op.drop_index("ix_audit_log_created_at",           table_name="audit_log")
    op.drop_index("ix_audit_log_entity",               table_name="audit_log")
    op.drop_index("ix_lawyer_conflicts_resolved",      table_name="lawyer_conflicts")
    op.drop_index("ix_lawyer_conflicts_lawyer_id",     table_name="lawyer_conflicts")
    op.drop_index("ix_eta_estimates_hearing_generated",table_name="eta_estimates")
    op.drop_index("ix_accused_case_id",                table_name="accused")
    op.drop_index("ix_cases_is_confidential",          table_name="cases")
    op.drop_index("ix_cases_status",                   table_name="cases")
    op.drop_index("ix_cases_defense_lawyer_id",        table_name="cases")
    op.drop_index("ix_hearings_judge_id",              table_name="hearings")
    op.drop_index("ix_hearings_case_id",               table_name="hearings")
    op.drop_index("ix_hearings_status",                table_name="hearings")
    op.drop_index("ix_hearings_courtroom_start",       table_name="hearings")
