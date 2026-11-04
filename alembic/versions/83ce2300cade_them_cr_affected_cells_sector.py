"""them_cr_affected_cells_sector

Revision ID: 83ce2300cade
Revises: 05593c1e5cd2
Create Date: 2026-10-04 00:00:00.000000

Quyet dinh 04/10/2026 (xuat phieu toi da 2/sector cua TRAM TAT) - can biet
SECTOR cua tung cell trong cr_affected_cells de gom nhom xep hang/cat tran
(xem application/xuat_phieu_use_case.py::_danh_gia_va_xep_hang()). Truoc gio
bang nay CHI co huong_id (RAW tu CDS, VARCHAR(10), hay NULL cho nhom huong
ten "W..." - xem khao sat 04/10/2026), KHONG co sector - phai them cot moi.

VIET TAY (KHONG autogenerate) theo yeu cau user - CHI 1 thao tac (them cot +
backfill), khong lan drift khac cua model/DB (xem bai hoc o migration
80450814195f, da tung phai cat 8 thao tac drift khong lien quan ra khoi ban
autogenerate).

Cot MOI la INTEGER NULLABLE (khong NOT NULL/server_default): sector CHI tinh
duoc khi huong_id la so nguyen hop le - 1 phan du lieu cu (~6.7% dong, xem
khao sat 04/10/2026) co huong_id NULL (CDS tra null cho nhom huong ten "W...")
nen sector cua cac dong do PHAI duoc phep NULL, khong the ep gia tri gia.

BACKFILL dong cu: sector = huong_id % 10 (CHU SO CUOI huong_id - dinh nghia
sector GIONG HET domain/services/neighbor_cell_filter.py, Y = huong_id % 10),
CHI khi huong_id la chuoi so nguyen hop le (regex ^[0-9]+$ - huong_id la
VARCHAR, co the chua gia tri khong phai so neu du lieu loi trong tuong lai,
guard truoc khi CAST de tranh migration FAIL giua chung tren DB that). Dong
huong_id NULL hoac khong phai so -> sector GIU NULL (KHONG doan).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83ce2300cade'
down_revision: Union[str, Sequence[str], None] = '05593c1e5cd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_affected_cells',
        sa.Column('sector', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    # Backfill dong cu - xem docstring dau file ve ly do chi backfill khi
    # huong_id la so nguyen hop le, con lai giu NULL.
    op.execute(
        f"""
        UPDATE {_SCHEMA}.cr_affected_cells
        SET sector = CAST(huong_id AS INTEGER) % 10
        WHERE huong_id IS NOT NULL AND huong_id ~ '^[0-9]+$'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cr_affected_cells', 'sector', schema=_SCHEMA)
