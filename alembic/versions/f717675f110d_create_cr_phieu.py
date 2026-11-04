"""create_cr_phieu

Revision ID: f717675f110d
Revises: 35c121cc3135
Create Date: 2026-08-07 10:44:44.968180

Luu phieu da xuat qua SaveCellClm (yeu cau truc tiep user, KHOI 2/5) de audit
+ chong trung - khoa (cr_session_id, cell_name), dung PATTERN cr_affected_cells
(35c121cc3135)/qoe_snapshot/qos_snapshot: 1 cell chi giu 1 phieu / 1 CR session.

created_at TIMESTAMPTZ KHONG dung server_default=now() - C1.4-fix9 da xac
nhan Postgres server TimeZone GUC = Asia/Ho_Chi_Minh, server_default=now()
se ghi GIO VN thay vi UTC. Luon set qua Python datetime.now(timezone.utc)
(xem adapters/postgres/cr_phieu_repo.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'f717675f110d'
down_revision: Union[str, Sequence[str], None] = '35c121cc3135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cr_phieu',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cr_session_id', sa.INTEGER(), nullable=False),
        sa.Column('cell_name', sa.VARCHAR(length=200), nullable=False),
        sa.Column('trang_thai', sa.VARCHAR(length=20), nullable=False),
        sa.Column('request_payload', JSONB(), nullable=False),
        sa.Column('response_body', JSONB(), nullable=True),
        sa.Column('phieu_id', sa.VARCHAR(length=100), nullable=True),
        sa.Column('error_message', sa.TEXT(), nullable=True),
        # KHONG server_default=sa.text('now()') - xem docstring dau file.
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['cr_session_id'], [f'{_SCHEMA}.cr_session.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cr_session_id', 'cell_name', name='uq_cr_phieu_session_cell'),
        schema=_SCHEMA,
    )
    op.create_index(
        'idx_cr_phieu_session', 'cr_phieu', ['cr_session_id'],
        unique=False, schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_cr_phieu_session', table_name='cr_phieu', schema=_SCHEMA)
    op.drop_table('cr_phieu', schema=_SCHEMA)
