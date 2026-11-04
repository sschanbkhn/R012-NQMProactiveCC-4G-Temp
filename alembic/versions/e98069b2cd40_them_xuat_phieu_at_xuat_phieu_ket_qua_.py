"""them xuat_phieu_at + xuat_phieu_ket_qua vao cr_session

Revision ID: e98069b2cd40
Revises: b7f4c2a91d38
Create Date: 2026-08-14 11:00:51.239655

Man hinh THEO DOI TIEN TRINH (yeu cau truc tiep user, 14/08) - 2 cot ghi lai
KET QUA cua luot job xuat phieu tren tung session:
    xuat_phieu_at      TIMESTAMPTZ NULL  - moc job quet XONG session nay.
                                           NULL = chua toi luot quet.
    xuat_phieu_ket_qua VARCHAR(30) NULL  - DA_XUAT / KHONG_CAN_XUAT / LOI

=== VI SAO PHAI THEM COT, KHONG SUY RA DUOC TU DU LIEU DA CO ===

(1) KHONG co truong nao dang ghi "da danh gia theo tieu chi XUAT PHIEU".
    `cr_session.status = EVALUATED` den tu EvaluateCrUseCase - co che KHAC HAN:
        EvaluateCrUseCase : nguong -0.1, moc EVALUATION_DAYS = 21 ngay
        XuatPhieuUseCase  : nguong -0.2, moc XUAT_PHIEU_AFTER_DAYS = 8 ngay
    Hai thu doc lap hoan toan, va job 21 ngay CHUA TUNG chay that (kiem tra DB
    ngay 13/08: 0 session co evaluated_at, 0 dong qoe_snapshot/qos_snapshot).
    Lay status=EVALUATED lam dau hieu "da xuat phieu xong" se SAI ca 2 chieu.

(2) Suy tien trinh tu bang cr_phieu KHONG DU. Truong hop TAT CA CELL DAT (job
    da quet, danh gia xong, ket luan khong cell nao can phieu) tao ra 0 dong
    cr_phieu - KHONG phan biet duoc voi "chua toi luot quet" (cung 0 dong).
    Nghiem trong hon vi PA A: moi session chi duoc quet DUNG 1 LAN (dieu kien
    `ngay_CR == hom_nay - 8`, khong con `<=`), nen session "tat ca cell dat" se
    hien "dang cho" VINH VIEN tren UI - khong bao gio co luot quet thu 2 de sua
    lai. Day chinh la case MOCK994 trong bo du lieu mau.

VARCHAR(30) chu KHONG phai 20: bai hoc truc tiep tu migration b7f4c2a91d38 -
cr_phieu.trang_thai de VARCHAR(20) roi V4 them gia tri dai 24 ky tu, phai chay
them 1 migration nua chi de noi cot. 30 du cho 3 gia tri hien tai + con cho.

CA HAI COT DEU NULLABLE, KHONG server_default: 15 session cu deu la du lieu
LICH SU chay truoc khi co co che nay - dien mot gia tri mac dinh nao do vao
chung se la NOI DOI (vd dien 'KHONG_CAN_XUAT' cho session ma job chua bao gio
cham toi). NULL dung nghia "khong biet / chua toi luot", va do CHINH LA thu FE
can de hien trang thai "dang cho" hoac "qua han".

DA CAT BOT SO VOI BAN AUTOGENERATE (doc truoc khi sua file nay):
Ban autogenerate sinh kem DUNG 8 thao tac KHONG lien quan 2 cot moi - van la
DRIFT co san giua models/ va DB that, y het 2 lan truoc (80450814195f,
ce1a0d7996ac):
  - doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_<col>):
    model dung index=True (Alembic tu dat ten) trong khi migration cu dat ten
    tay. 3 drop_index + 3 create_index.
  - them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id. 2 lenh.
Da XOA ca 8 - migration nay CHI them dung 2 cot. Drift VAN CON, lan autogenerate
sau se lai de xuat, phai kiem tra tay moi lan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e98069b2cd40'
down_revision: Union[str, Sequence[str], None] = 'b7f4c2a91d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_session',
        sa.Column('xuat_phieu_at', sa.TIMESTAMP(timezone=True), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_session',
        sa.Column('xuat_phieu_ket_qua', sa.VARCHAR(length=30), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Thu tu NGUOC voi upgrade() - khong bat buoc ve ky thuat (2 cot doc lap,
    # khong cot nao phu thuoc cot kia) nhung giu dung quy uoc de doc de doi chieu.
    op.drop_column('cr_session', 'xuat_phieu_ket_qua', schema=_SCHEMA)
    op.drop_column('cr_session', 'xuat_phieu_at', schema=_SCHEMA)
