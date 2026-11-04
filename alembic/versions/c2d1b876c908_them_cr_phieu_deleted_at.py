"""them_cr_phieu_deleted_at

Revision ID: c2d1b876c908
Revises: 83ce2300cade
Create Date: 2026-10-04 00:00:00.000000

Quyet dinh 04/10/2026 (XOA MEM phieu, yeu cau truc tiep user): phieu da xoa
KHONG duoc hien lai o bat cu dau nua, VA KHONG duoc tao lai. Truoc gio DELETE
/phieu/{id} la HARD DELETE that (xem adapters/postgres/cr_phieu_repo.py::xoa()
cu) - xoa sach moi dau vet nen (a) khong con gi de phan biet "chua xuat" voi
"da xuat roi bi xoa", UNIQUE(cr_session_id, cell_name) cho insert lai ngay ->
job tu dong lai tao phieu MOI cho dung cell vua bi xoa (bug that da khao sat
04/10/2026: alert "Co N phieu xuat loi" van hien sau khi xoa vi job_run_log la
lich su dong bang, KHONG lien quan migration nay - nhung cung phat sinh tu
cung 1 goc: khong co dau vet "da xoa" nao de cac noi doc/dem loai ra).

VIET TAY (KHONG autogenerate) - CHI 1 thao tac them cot, dung tien le migration
83ce2300cade.

Cot MOI la TIMESTAMPTZ NULLABLE, KHONG server_default (dung pattern C1.4-fix9
da ap dung xuyen suot project cho moi cot TIMESTAMPTZ - Postgres server
TimeZone GUC = Asia/Ho_Chi_Minh, server_default=now() se ghi gio VN thay vi
UTC). Repo luon set qua Python datetime.now(timezone.utc) khi xoa (xem
CrPhieuRepo.xoa() sau sua). NULL = "chua xoa" (gia tri mac dinh cho MOI dong
cu, khong can backfill).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d1b876c908'
down_revision: Union[str, Sequence[str], None] = '83ce2300cade'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_phieu',
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cr_phieu', 'deleted_at', schema=_SCHEMA)
