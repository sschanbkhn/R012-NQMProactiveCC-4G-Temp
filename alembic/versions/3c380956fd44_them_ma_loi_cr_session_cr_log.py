"""them ma_loi vao cr_session va cr_log

Revision ID: 3c380956fd44
Revises: c3f7a1b29e44
Create Date: 2026-10-16 00:00:00.000000

THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - cot MOI
`ma_loi VARCHAR(30) NULL` tren CA 2 bang `cr_session` va `cr_log`, luu
error_code cua DomainError gay FAILED/KHONG_CHAY (vd "KHONG_CO_DU_LIEU_HO",
"SSH_CONNECTION_ERROR" - xem domain/errors.py).

- cr_session.ma_loi: ghi boi TriggerCrUseCase._fail() CUNG LUC voi status
  (FAILED hoac KHONG_CHAY moi, xem domain/entities/cr_session.py::CrStatus) -
  mo ta loi CUOI CUNG cua session, de FE loc/hien thi nhanh khong can doc
  tung dong cr_log.
- cr_log.ma_loi: ghi tren DONG cu the (status="failed") gay ra loi do - giu
  lich su CHI TIET theo tung buoc (1 session co the co nhieu dong cr_log,
  cr_session.ma_loi chi la ban ghi CUOI CUNG).

CA 2 COT DEU NULLABLE, KHONG server_default, KHONG backfill: toan bo session/
cr_log CU (truoc migration nay) KHONG CO du lieu goc (message tu do, da luu
duoi dang text tu do khong structured) de suy nguoc error_code CHINH XAC -
dien bua se la NOI DOI (giong ly do KHONG backfill oss_instance_id/noc o
migration truoc, xem .env.example/docs lien quan).

VARCHAR(30) chu KHONG phai 20: CUNG bai hoc voi xuat_phieu_ket_qua (migration
e98069b2cd40) - error_code dai nhat hien tai la "CR_EVALUATION_IN_PROGRESS"
(25 ky tu), can du cho con cho (xem domain/errors.py).

VIET TAY (KHONG autogenerate) - dung tien le cac migration truoc (83ce2300cade,
c2d1b876c908, 79a3855ede6b, c3f7a1b29e44).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c380956fd44'
down_revision: Union[str, Sequence[str], None] = 'c3f7a1b29e44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_session',
        sa.Column('ma_loi', sa.VARCHAR(length=30), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_log',
        sa.Column('ma_loi', sa.VARCHAR(length=30), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Thu tu NGUOC voi upgrade() - 2 cot doc lap (bang khac nhau), giu dung
    # quy uoc de doc de doi chieu (giong e98069b2cd40).
    op.drop_column('cr_log', 'ma_loi', schema=_SCHEMA)
    op.drop_column('cr_session', 'ma_loi', schema=_SCHEMA)
