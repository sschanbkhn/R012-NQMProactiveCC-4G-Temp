"""create_cell_vi_tri_uoc_luong

Revision ID: c3f7a1b29e44
Revises: 79a3855ede6b
Create Date: 2026-10-10 00:00:00.000000

BUOC 4c (10/10/2026, yeu cau truc tiep user) - vi tri uoc luong cell cua tram
TOA_DO_DUNG_CHUNG (CRAN), CHI DUNG DE HIEN THI (ban do xem truoc/API
/stations/map) - xem models/cell_vi_tri_uoc_luong.py va domain/services/
cran_vi_tri_estimator.py ve day du ly do/cong thuc.

VIET TAY (KHONG autogenerate) - dung tien le cac migration truoc (83ce2300cade,
c2d1b876c908, 79a3855ede6b).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f7a1b29e44'
down_revision: Union[str, Sequence[str], None] = '79a3855ede6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cell_vi_tri_uoc_luong',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('netact', sa.VARCHAR(20), nullable=False),
        sa.Column('enb', sa.INTEGER(), nullable=False),
        sa.Column('lcr', sa.INTEGER(), nullable=False),
        sa.Column('lat', sa.NUMERIC(10, 6), nullable=False),
        sa.Column('lon', sa.NUMERIC(10, 6), nullable=False),
        sa.Column('ty_le_ho_tin_cay', sa.NUMERIC(5, 4), nullable=False),
        sa.Column('so_tram_dich', sa.INTEGER(), nullable=False),
        sa.Column('ngay_du_lieu', sa.DATE(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'netact', 'enb', 'lcr',
            name='uq_cell_vi_tri_uoc_luong_netact_enb_lcr',
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        'ix_cell_vi_tri_uoc_luong_netact', 'cell_vi_tri_uoc_luong', ['netact'], unique=False, schema=_SCHEMA,
    )
    op.create_index(
        'ix_cell_vi_tri_uoc_luong_enb', 'cell_vi_tri_uoc_luong', ['enb'], unique=False, schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('cell_vi_tri_uoc_luong', schema=_SCHEMA)
