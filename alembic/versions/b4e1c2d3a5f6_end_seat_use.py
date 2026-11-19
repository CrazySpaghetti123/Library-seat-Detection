"""end seat use: latest detection result and leave check anchors

Revision ID: b4e1c2d3a5f6
Revises: 723c00705f85
Create Date: 2026-11-20 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4e1c2d3a5f6'
down_revision: Union[str, Sequence[str], None] = '723c00705f85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('seats', sa.Column('last_detection', sa.String(length=30), nullable=True))
    op.add_column('seats', sa.Column('last_detection_at', sa.DateTime(), nullable=True))
    op.add_column('bookings', sa.Column('leave_requested_at', sa.DateTime(), nullable=True))
    op.add_column('bookings', sa.Column('leave_check_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # SQLite 不支援直接 DROP COLUMN（舊版），以 batch 模式重建資料表
    with op.batch_alter_table('bookings') as batch:
        batch.drop_column('leave_check_at')
        batch.drop_column('leave_requested_at')
    with op.batch_alter_table('seats') as batch:
        batch.drop_column('last_detection_at')
        batch.drop_column('last_detection')
