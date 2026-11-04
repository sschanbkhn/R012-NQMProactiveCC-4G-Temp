"""noi rong cr_phieu.trang_thai VARCHAR(20) -> VARCHAR(30)

Revision ID: b7f4c2a91d38
Revises: ce1a0d7996ac
Create Date: 2026-08-13 09:45:00.000000

V4 (yeu cau truc tiep user, 12/08) - them 2 gia tri trang_thai cho cell ma job
CO Y khong xuat:
    KHONG_XUAT_VUOT_GIOI_HAN   24 ky tu
    KHONG_XUAT_HET_LUOT_THU    23 ky tu
Cot dang la VARCHAR(20) nen CA HAI deu KHONG vua - moi INSERT se chet ngay voi
asyncpg.exceptions.StringDataRightTruncationError ("value too long for type
character varying(20)").

PHAT HIEN BANG TEST, KHONG PHAI TREN PRODUCTION: test integration
tests/integration/test_cr_phieu_repo.py::test_v2_khong_truyen_trang_thai_thi_LAY_TAT_CA
do thang vao DB that nen bat duoc ngay. Neu chi test bang mock thi loi nay se
chi lo ra o luot job dau tien chay that, va lo ra dung o cho te nhat: cell vuot
tran 10 se KHONG duoc ghi lai - dung cai ma V4 sinh ra de tranh.

VI SAO NOI COT chu KHONG rut ngan ten trang thai: 2 ten nay do user dat, mang
dung nghia nghiep vu ("vuot gioi han" / "het luot thu"). Rut thanh VUOT_TRAN /
HET_THU cho vua 20 ky tu la bop nghiep vu cho vua ky thuat - trong khi noi cot
VARCHAR khong ton kem gi tren Postgres (khong rewrite bang, khong khoa lau:
tang do dai VARCHAR la thao tac chi sua catalog tu PG 9.2).

30 = gia tri dai nhat (24) + con cho cho 1-2 trang thai moi, KHONG noi qua tay
thanh VARCHAR(255)/TEXT: cot nay la tap gia tri DONG (whitelist o
api/routers/phieu.py::_PhieuTrangThai), gioi han do dai la 1 lop chan nhe chong
ghi bua.

AN TOAN DU LIEU: chi NOI RONG (20 -> 30), khong dong nao dang co bi cat. 3 dong
hien tai deu la PENDING/SUCCESS/FAILED (<= 7 ky tu).

downgrade() thu hep lai 20 - SE CHET neu luc do da co dong mang trang_thai
KHONG_XUAT_* (Postgres tu chan, khong am tham cat chuoi). Do la hanh vi DUNG:
thu hep cot khi da co du lieu dai hon phai that bai to tieng chu khong duoc mat
du lieu. Muon downgrade thi phai xu ly cac dong do truoc.

DA CAT BOT SO VOI BAN AUTOGENERATE: file nay VIET TAY (khong chay autogenerate)
- autogenerate se lai keo theo dung 8 drift index/FK da biet, xem ghi chu trong
migration 80450814195f va ce1a0d7996ac.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f4c2a91d38'
down_revision: Union[str, Sequence[str], None] = 'ce1a0d7996ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'cr_phieu',
        'trang_thai',
        existing_type=sa.VARCHAR(length=20),
        type_=sa.VARCHAR(length=30),
        existing_nullable=False,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'cr_phieu',
        'trang_thai',
        existing_type=sa.VARCHAR(length=30),
        type_=sa.VARCHAR(length=20),
        existing_nullable=False,
        schema=_SCHEMA,
    )
