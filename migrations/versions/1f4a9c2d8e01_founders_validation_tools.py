"""Founder validation tools: polls, pitch, finmodel

Revision ID: 1f4a9c2d8e01
Revises: 0a2dbf49c3b6
Create Date: 2026-05-22

"""
from alembic import op
import sqlalchemy as sa


revision = "1f4a9c2d8e01"
down_revision = "0a2dbf49c3b6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("startup", schema=None) as batch_op:
        batch_op.add_column(sa.Column("business_model_type", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("pitch_pre_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("pitch_analysis_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("fin_model_json", sa.Text(), nullable=True))

    op.create_table(
        "idea_poll",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("startup_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("yes_count", sa.Integer(), nullable=False),
        sa.Column("no_count", sa.Integer(), nullable=False),
        sa.Column("maybe_count", sa.Integer(), nullable=False),
        sa.Column("engagement_count", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"]),
        sa.ForeignKeyConstraint(["startup_id"], ["startup.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id"),
    )
    with op.batch_alter_table("idea_poll", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_idea_poll_startup_id"), ["startup_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_idea_poll_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_idea_poll_verdict"), ["verdict"], unique=False)

    op.create_table(
        "idea_poll_vote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("poll_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("choice", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["poll_id"], ["idea_poll.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("poll_id", "user_id", name="uq_poll_vote"),
    )
    with op.batch_alter_table("idea_poll_vote", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_idea_poll_vote_poll_id"), ["poll_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_idea_poll_vote_user_id"), ["user_id"], unique=False)


def downgrade():
    op.drop_table("idea_poll_vote")
    op.drop_table("idea_poll")
    with op.batch_alter_table("startup", schema=None) as batch_op:
        batch_op.drop_column("fin_model_json")
        batch_op.drop_column("pitch_analysis_json")
        batch_op.drop_column("pitch_pre_json")
        batch_op.drop_column("business_model_type")
