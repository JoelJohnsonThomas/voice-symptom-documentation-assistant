"""Add document versioning and annotation tables

Revision ID: 001
Revises: None
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(), index=True),
        sa.Column("author_id", sa.String(), nullable=True, index=True),
        sa.Column("author_username", sa.String(), nullable=True),
        sa.Column("author_role", sa.String(), nullable=True),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("change_type", sa.String(), nullable=False, server_default="edit"),
        sa.Column("confidence_json", sa.Text(), nullable=True),
        sa.Column("is_encrypted", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.create_table(
        "document_annotations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_version_id", sa.String(), nullable=False, index=True),
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), index=True),
        sa.Column("author_id", sa.String(), nullable=True, index=True),
        sa.Column("author_username", sa.String(), nullable=True),
        sa.Column("soap_section", sa.String(), nullable=False),
        sa.Column("field_path", sa.String(), nullable=True),
        sa.Column("text_offset_start", sa.Integer(), nullable=True),
        sa.Column("text_offset_end", sa.Integer(), nullable=True),
        sa.Column("annotation_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("suggested_replacement", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="open"),
        sa.Column("resolved_by_id", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("document_annotations")
    op.drop_table("document_versions")
