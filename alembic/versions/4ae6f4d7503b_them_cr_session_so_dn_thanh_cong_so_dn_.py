"""them cr_session.so_dn_thanh_cong + so_dn_tong

Revision ID: 4ae6f4d7503b
Revises: 49066deb32a4
Create Date: 2026-08-19

TY LE DN PROVISION THANH CONG (yeu cau truc tiep user, 19/08). Sau khi co
PARTIAL_SUCCESS (commit 1ff269e), status chi noi duoc "co mot so DN hong" chu
KHONG noi duoc BAO NHIEU:

    so_dn_thanh_cong INTEGER NULL  - so DN provision THANH CONG
    so_dn_tong       INTEGER NULL  - tong so DN trong plan

=== VI SAO PHAI THEM COT ===

(1) THONG TIN NAY HIEN CHI NAM TRONG cr_log BUOC 13 DANG CHU:
        "Provision 3/4 DN thanh cong (6/12 MO)
         OK   MRBTS-116952 (1 MO)
         ..."
    Doc bang mat thi duoc, nhung KHONG truy van duoc, KHONG hien len bang
    duoc, KHONG loc/sap xep duoc. Muon tra loi "session nao chi provision
    duoc mot phan" thi phai LIKE tren cot text cua cr_log roi parse chuoi -
    cham, khong index, va vo cung de vo khi doi dinh dang dong tom tat.

(2) NGUOI VAN HANH CAN THAY NGAY TREN DANH SACH. "PARTIAL_SUCCESS" mot minh
    khong du de quyet dinh: 3/4 tram thanh cong khac han 1/4 tram thanh cong -
    mot ben chi con 1 tram phai xu ly tay, mot ben gan nhu hong ca. Phai mo
    tung session xem cr_log moi biet la qua cham cho viec quyet dinh hang ngay.

=== VI SAO CHI 2 COT, KHONG THEM so_mo_* ===

Don vi NGHIEP VU o day la TRAM (DN) - "3/4 tram da doi tham so RF". So MO
(managed object) la CHI TIET KY THUAT ben trong 1 tram, chi dung khi di soi
1 ca cu the, va DA CO san trong cr_log buoc 13. Them 2 cot nua chi de hien 1
con so khong ai loc/sap xep theo la phinh bang khong can thiet.

=== NULLABLE, KHONG BACKFILL ===

Session cu (chay truoc dot nay) de NULL. KHONG doan nguoc tu cr_log: dong tom
tat buoc 13 chi moi co tu commit 1ff269e (19/08), cac session truoc do KHONG
he ghi ty le DN nao - parse ra so la BIA. NULL dung nghia "khong ghi nhan",
va FE phan biet duoc voi 0/0 (co ghi nhan, khong DN nao thanh cong).

=== DA CAT BOT SO VOI BAN AUTOGENERATE ===

Ban autogenerate sinh 20 thao tac; 18 trong so do KHONG lien quan 2 cot moi -
van la DRIFT co san giua models/ va DB that, y het 4 lan truoc (80450814195f,
ce1a0d7996ac, e98069b2cd40, 49066deb32a4):
  - doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_<col>):
    model dung index=True (Alembic tu dat ten) trong khi migration cu dat ten
    tay. 3 drop_index + 3 create_index.
  - them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id. 2 lenh.
  - cac op keo theo trong downgrade().
Da XOA het - migration nay CHI them DUNG 2 cot. Drift VAN CON, lan autogenerate
sau se lai de xuat, phai kiem tra tay moi lan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ae6f4d7503b'
down_revision: Union[str, Sequence[str], None] = '49066deb32a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_session',
        sa.Column('so_dn_thanh_cong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_session',
        sa.Column('so_dn_tong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Thu tu NGUOC voi upgrade() - khong bat buoc ve ky thuat (2 cot doc lap)
    # nhung giu dung quy uoc de doc de doi chieu.
    op.drop_column('cr_session', 'so_dn_tong', schema=_SCHEMA)
    op.drop_column('cr_session', 'so_dn_thanh_cong', schema=_SCHEMA)
