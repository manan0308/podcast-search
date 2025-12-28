"""Fix chunks speakers column type from ARRAY to JSON.

Revision ID: 004
Revises: 003
Create Date: 2024-12-28
"""

from alembic import op


# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert speakers column from VARCHAR[] to JSON
    # First convert existing array data to JSON format
    op.execute(
        """
        ALTER TABLE chunks 
        ALTER COLUMN speakers 
        TYPE JSON 
        USING COALESCE(array_to_json(speakers), '[]'::json)
    """
    )

    # Set default for new rows
    op.execute(
        """
        ALTER TABLE chunks 
        ALTER COLUMN speakers 
        SET DEFAULT '[]'::json
    """
    )


def downgrade() -> None:
    # Convert back to ARRAY
    op.execute(
        """
        ALTER TABLE chunks 
        ALTER COLUMN speakers 
        TYPE VARCHAR[] 
        USING ARRAY(SELECT json_array_elements_text(speakers))
    """
    )

    op.execute(
        """
        ALTER TABLE chunks 
        ALTER COLUMN speakers 
        SET DEFAULT '{}'
    """
    )
