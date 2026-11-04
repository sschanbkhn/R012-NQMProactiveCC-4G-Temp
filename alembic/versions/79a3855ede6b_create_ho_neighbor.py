"""create_ho_neighbor

Revision ID: 79a3855ede6b
Revises: c2d1b876c908
Create Date: 2026-10-08 00:00:00.000000

Quyet dinh 06-08/10/2026 (BO CDS, yeu cau truc tiep user) - CDS /cell/neighbors
tinh neighbor tu azimuth/do cao NHAP TAY (hay sai). Thay bang HO (handover)
THAT tu NetAct: UE dang handover sang cell nao nhieu nhat thi cell do dang
PHU VUNG that. Bang nay luu ket qua doc + giai ma san tu file report HO
(~3 trieu dong/lan export) de thuat toan chon cell (domain/services/
ho_cell_selector.py) doc nhanh theo source_enb, khong phai doc lai CSV moi
lan chay - xem models/ho_neighbor.py va docs/BUSINESS_RULES.md.

VIET TAY (KHONG autogenerate) - dung tien le cac migration truoc (83ce2300cade,
c2d1b876c908). CHUA CHAY migration nay (yeu cau truc tiep user "Migration VIET
TAY, CHUA chay, bao cao file") - chi tao file, KHONG goi `alembic upgrade`.

SUA 08/10/2026 lan 4 (yeu cau truc tiep user, "NAP DAY DU HO VAO DB"): thay 2
chi muc rieng le (netact, source_enb) bang 1 chi muc GHEP (netact, source_enb)
- khop DUNG mau truy van duy nhat cua IHoNeighborRepo.get_by_source_enb()
(adapters/postgres/ho_neighbor_repo.py: luon loc CA HAI cot cung luc). Chi
SUA TRUC TIEP file nay (khong tao migration moi chong len) vi migration CHUA
TUNG duoc ap dung o bat ky moi truong nao (`alembic current` = c2d1b876c908,
xac nhan truoc khi sua) - an toan sua, tranh chong 2 migration khong can
thiet cho 1 bang chua ai dung.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79a3855ede6b'
down_revision: Union[str, Sequence[str], None] = 'c2d1b876c908'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ho_neighbor',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('netact', sa.VARCHAR(20), nullable=False),
        sa.Column('ngay_du_lieu', sa.DATE(), nullable=False),
        sa.Column('source_enb', sa.INTEGER(), nullable=False),
        sa.Column('source_lncel_name', sa.VARCHAR(200), nullable=False),
        sa.Column('source_sector', sa.INTEGER(), nullable=False),
        sa.Column('target_eci', sa.BIGINT(), nullable=False),
        sa.Column('target_enb', sa.INTEGER(), nullable=False),
        sa.Column('target_lcr', sa.INTEGER(), nullable=False),
        sa.Column('ho_attempt', sa.INTEGER(), nullable=False),
        sa.Column('ho_sr', sa.NUMERIC(5, 2), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'netact', 'source_enb', 'source_sector', 'target_enb', 'target_lcr',
            name='uq_ho_neighbor_netact_source_target',
        ),
        schema=_SCHEMA,
    )
    # Chi muc GHEP (netact, source_enb) - khop DUNG mau truy van duy nhat
    # cua get_by_source_enb() (loc CA HAI cot cung luc). THAY cho 2 chi muc
    # rieng le (netact) + (source_enb) o ban truoc (xem SUA 08/10/2026 lan 4
    # o docstring dau file).
    op.create_index(
        'ix_ho_neighbor_netact_source_enb', 'ho_neighbor', ['netact', 'source_enb'], unique=False, schema=_SCHEMA,
    )
    op.create_index(
        'ix_ho_neighbor_target_enb', 'ho_neighbor', ['target_enb'], unique=False, schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ho_neighbor', schema=_SCHEMA)
