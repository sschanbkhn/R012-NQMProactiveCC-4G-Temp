"""them cr_session.oss_instance_id + cr_session.noc, backfill session cu

Revision ID: 05593c1e5cd2
Revises: b3f7d21ac504
Create Date: 2026-10-02 00:00:00.000000

*** VIET TAY (KHONG autogenerate). CHUA CHAY - file nay de nguoi duyet doc
truoc khi `alembic upgrade head`. ***

===========================================================================
LY DO (02/10/2026, "cr_session luu NetAct + NOC de tra lich su")
===========================================================================
Giai doan 1 buoc 2 (27/09/2026) da them dinh tuyen OSS THEO TUNG CELL
(domain/value_objects/oss_instance.py, adapters/netact/oss_router_env.py)
nhung OSS/NOC da dung cho 1 CR CHI ton tai TAM THOI trong bo nho luc chay
(PlanResult.oss_instance) - khong co cach nao tra loi "session nay THAT SU
chay tren NetAct nao / NOC nao" sau khi CR da xong, tru phi mo dung file
execution.log (text khong cau truc, khong truy van duoc).

2 cot moi:
  oss_instance_id VARCHAR(50) NULL - ten goi NetAct (vd "NA09"), KHONG phai
    FK (OSS cau hinh trong .env NETACT_SERVERS, khong co bang DB rieng).
  noc             VARCHAR(20) NULL - don vi van hanh quan ly OSS do (vd
    "NOC1"), tu OssInstance.noc moi (them cung dot - xem
    domain/value_objects/oss_instance.py).

CA 2 NULLABLE: session bi TU CHOI TRUOC khi chon duoc 1 OSS cu the (vd
CR_NHIEU_OSS - nhieu OSS khac nhau, khong co 1 cai de ghi; hoac loi CDS o
buoc 3 truoc ca buoc dinh tuyen) thi KHONG co gia tri nao hop ly de dien -
de NULL, KHONG doan (xem application/trigger_cr_use_case.py::_fail(),
tham so `oss` moi).

===========================================================================
BACKFILL SESSION CU - DIEU KIEN DA CHON (bao cao de nguoi duyet doi chieu)
===========================================================================
noc = 'NOC1' CHO MOI DONG, KHONG dieu kien gi - he thong truoc Giai doan 1
chi dinh tuyen ve 1 vung DUY NHAT (HNI, qua get_ma_tinh() + 1 bo
NETACT_SERVERS khong phan vung NOC), xac nhan voi user "truoc nay chi chay
HNI". Khong co session cu nao tung chay NOC khac - gan cung an toan.

oss_instance_id = 'NA09' CHI khi executed_at IS NOT NULL. Ly do chon dieu
kien nay (tu xac dinh tu code, KHONG co cot nao san co ghi truc tiep "da
gui SSH chua"):
  - executed_at CHI duoc gan O 1 CHO DUY NHAT trong toan bo code (truoc ban
    sua nay): application/trigger_cr_use_case.py, buoc 17, NGAY SAU khi
    submit_cr() tra ve ket qua co "ok"=True (DONE hoac PARTIAL_SUCCESS) -
    xem run_cr_flow(). Noi khac (guard loi, cac nhanh FAILED som hon) DEU
    KHONG dong vao cot nay.
  - Truoc ban sua nay, KHI Import/Provision that bai tren NetAct that
    (submit_cr() tra "ok"=False) MA session van THAT SU da goi SSH, code
    CU **KHONG** luu plan_name/duong_dan_log/executed_at xuong DB cho
    truong hop do (gan vao bien session CHI xay ra o nhanh thanh cong, sau
    diem kiem tra "ok") - nghia la VOI DU LIEU DA CO SAN tren DB (truoc ban
    sua nay), KHONG CO CACH NAO phan biet duoc "that bai truoc khi gui SSH"
    voi "that bai SAU khi gui SSH that" tu cac cot hien huu. Day la GIOI
    HAN THAT cua du lieu lich su, khong phai loi cua migration nay.
  - Vi vay dieu kien executed_at IS NOT NULL la dieu kien CHAT NHAT, AN
    TOAN NHAT co san: CHI gan oss_instance_id cho session DA CHAC CHAN gui
    CR thanh cong (it nhat 1 phan) len NetAct that. Session FAILED o
    Import/Provision (du co the DA thuc su gui SSH) se KHONG duoc backfill
    oss_instance_id (giu NULL) - DUOI UOC LUONG, khong phai qua uoc luong:
    tho hon la BO SOT vai session thuc ra co OSS, con hon GAN SAI oss cho
    session chua chac chan da gui gi.
  - Moi session backfill (executed_at IS NOT NULL) deu la 'NA09' (tuong
    ung host 10.212.242.20, HNI) - cung ly do voi noc='NOC1': he thong
    truoc Giai doan 1 chi co 1 OSS vat ly duy nhat dang dung.

CAU SQL CHINH XAC (chay trong upgrade(), xem code ben duoi):
    UPDATE cr_session SET noc = 'NOC1';
    UPDATE cr_session SET oss_instance_id = 'NA09' WHERE executed_at IS NOT NULL;

===========================================================================
GHI CHU VE AUTOGENERATE
===========================================================================
File nay VIET TAY hoan toan theo yeu cau (KHONG chay `alembic revision
--autogenerate`) - tranh drift index/FK khong lien quan tu schema nay (da
biet tu cac migration truoc, xem b3f7d21ac504).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05593c1e5cd2'
down_revision: Union[str, Sequence[str], None] = 'b3f7d21ac504'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_session',
        sa.Column('oss_instance_id', sa.VARCHAR(length=50), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_session',
        sa.Column('noc', sa.VARCHAR(length=20), nullable=True),
        schema=_SCHEMA,
    )

    # --- Backfill session cu (xem docstring dau file cho dieu kien day du) ---
    # noc='NOC1' cho MOI dong - he thong truoc Giai doan 1 chi chay 1 vung (HNI).
    op.execute(f"UPDATE {_SCHEMA}.cr_session SET noc = 'NOC1'")
    # oss_instance_id='NA09' CHI session DA THUC SU hoan tat goi SSH toi
    # NetAct (executed_at IS NOT NULL - xem ly do day du o tren).
    op.execute(
        f"UPDATE {_SCHEMA}.cr_session SET oss_instance_id = 'NA09' WHERE executed_at IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cr_session', 'noc', schema=_SCHEMA)
    op.drop_column('cr_session', 'oss_instance_id', schema=_SCHEMA)
