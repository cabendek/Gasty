"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE gmail_connection_status_enum AS ENUM "
        "('connected', 'needs_reauth', 'never_connected')"
    )
    op.execute(
        "CREATE TYPE transaction_type_enum AS ENUM "
        "('expense', 'income', 'refund', 'internal_transfer')"
    )
    op.execute(
        "CREATE TYPE budget_type_enum AS ENUM ('fixed', 'percentage')"
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("supabase_id", sa.String(), nullable=False, unique=True),
        sa.Column("gmail_access_token", sa.String(), nullable=True),
        sa.Column("gmail_refresh_token", sa.String(), nullable=True),
        sa.Column("gmail_watch_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "gmail_connection_status",
            postgresql.ENUM(
                "connected",
                "needs_reauth",
                "never_connected",
                name="gmail_connection_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="never_connected",
        ),
        sa.Column("expo_push_token", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "budget_type",
            postgresql.ENUM("fixed", "percentage", name="budget_type_enum", create_type=False),
            nullable=True,
        ),
        sa.Column("budget_amount", sa.Numeric(12, 0), nullable=True),
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 0), nullable=False),
        sa.Column("merchant", sa.String(), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "transaction_type",
            postgresql.ENUM(
                "expense",
                "income",
                "refund",
                "internal_transfer",
                name="transaction_type_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="expense",
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_email_id", sa.String(), nullable=False, unique=True),
        sa.Column("raw_subject", sa.Text(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_duplicate_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "parse_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("source_email_id", sa.String(), nullable=False),
        sa.Column("raw_subject", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "processed_pubsub_messages",
        sa.Column("message_id", sa.String(), primary_key=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_pubsub_messages")
    op.drop_table("parse_errors")
    op.drop_table("transactions")
    op.drop_table("categories")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS budget_type_enum")
    op.execute("DROP TYPE IF EXISTS transaction_type_enum")
    op.execute("DROP TYPE IF EXISTS gmail_connection_status_enum")
