"""create_cr_affected_cells

Revision ID: 35c121cc3135
Revises: 5fedc9a8402e
Create Date: 2026-07-22 04:35:54.417420

Phuong an B (22072026, DA DUYET thiet ke) - luu 47 cell "bi anh huong"
(NeighborCellFilter.filter_affected(), Nhanh A) rieng, tach khoi cell_params
(12 cell "chay CR", Nhanh B). LY DO khong dung chung cell_params: cot
UNIQUE(tram_id, cell_name) cua cell_params la trang thai HIEN TAI cua 1 cell
vat ly (upsert lien tuc boi sync-netact hang ngay), 1 cell chi giu duoc DUY
NHAT 1 cr_session_id tai 1 thoi diem - neu 1 cell la "affected" cua nhieu CR
session khac nhau theo thoi gian se MAT lich su session truoc. Bang moi khoa
theo (cr_session_id, cell_name) - dung PATTERN da co san cua qoe_snapshot/
qos_snapshot (DB_SCHEMA.md Section 5/6), khong phai kieu moi.

created_at TIMESTAMPTZ KHONG dung server_default=now() - C1.4-fix9 da xac
nhan Postgres server TimeZone GUC = Asia/Ho_Chi_Minh, server_default=now()
se ghi GIO VN thay vi UTC. Luon set qua Python datetime.now(timezone.utc)
(xem adapters/postgres/cr_affected_cells_repo.py).

KHONG backfill 6 session cu (du lieu test, xac nhan voi user) - bang bat dau
rong, chi CR session MOI tu gio moi co affected_cells.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35c121cc3135'
down_revision: Union[str, Sequence[str], None] = '5fedc9a8402e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cr_affected_cells',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cr_session_id', sa.INTEGER(), nullable=False),
        sa.Column('cell_name', sa.VARCHAR(length=200), nullable=False),
        # tram_id = LNBTS (domain/services/dist_name.py::extract_lnbts()),
        # nullable - mot so LNBTS chua join duoc bang tram (site chua sync
        # RIMS), van luu cell_name/huong_id de khong mat du lieu.
        sa.Column('tram_id', sa.VARCHAR(length=50), nullable=True),
        sa.Column('huong_id', sa.VARCHAR(length=10), nullable=True),
        sa.Column('dist_name', sa.VARCHAR(length=300), nullable=True),
        # KHONG server_default=sa.text('now()') - xem docstring dau file.
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['cr_session_id'], [f'{_SCHEMA}.cr_session.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cr_session_id', 'cell_name', name='uq_affected_cells_session_cell'),
        schema=_SCHEMA,
    )
    op.create_index(
        'idx_affected_cells_session', 'cr_affected_cells', ['cr_session_id'],
        unique=False, schema=_SCHEMA,
    )
    op.create_index(
        'idx_affected_cells_cell', 'cr_affected_cells', ['cell_name'],
        unique=False, schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_affected_cells_cell', table_name='cr_affected_cells', schema=_SCHEMA)
    op.drop_index('idx_affected_cells_session', table_name='cr_affected_cells', schema=_SCHEMA)
    op.drop_table('cr_affected_cells', schema=_SCHEMA)
