"""them cr_phieu.nguon_khong_dat

Revision ID: 49066deb32a4
Revises: e98069b2cd40
Create Date: 2026-08-17

QoE NGANG HANG QoS (yeu cau truc tiep user, 17/08): cell KHONG DAT o BAT KY chi
so nao (QoS hoac QoE) deu duoc xuat phieu, va 1 cell van chi 1 PHIEU chua ca 2
chi so. Cot moi ghi lai CHI SO NAO da lam cell do khong dat:

    nguon_khong_dat VARCHAR(10) NULL  - QOS / QOE / CA_HAI

=== VI SAO PHAI THEM COT, KHONG NHET VAO request_payload ===

(1) HAI TANG KHAC NHAU. `request_payload` (JSONB) la "CAI DA GUI DI CTS" - ban
    sao nguyen van cua request, dung de audit va doi chieu voi phieu that tren
    TTS. Con `nguon_khong_dat` la "VI SAO TA QUYET DINH XUAT PHIEU NAY" - ket
    luan danh gia cua he thong, KHONG phai thu CTS quan tam. Tron 2 tang lam
    payload thoi khong con la ban sao trung thuc cua request nua.

(2) KHONG TRA LOI DUOC CAU HOI VAN HANH CO BAN neu thieu cot nay:
      - Thang nay bao nhieu phieu xuat do QoE?
      - Tu khi bat CEM (CEM_ENABLED=true), so phieu tang bao nhieu?
      - Cell nao khong dat CA HAI chi so (nghiem trong hon han)?
    Query xuoi vao JSONB thi lam duoc nhung CHAM va KHONG CO INDEX. Quan trong
    hon: JSONB chi chua cai da gui CTS (Qos/Qoe/SoChiTieuVP) - tu do KHONG SUY
    NGUOC duoc "khong dat vi chi so nao". VD SoChiTieuVP="1" chi noi vi pham 1
    chi tieu, khong noi la chi tieu NAO.

(3) VARCHAR(10) du cho 3 gia tri (dai nhat "CA_HAI" = 6 ky tu) + con cho. KHONG
    dat 20/30 nhu cac cot khac vi day la tap gia tri DONG (enum nghiep vu), khac
    trang_thai (da phai noi 20 -> 30 o b7f4c2a91d38 vi them gia tri dai 24 ky
    tu). Neu sau nay them chi so thu 3 thi ten van ngan (vd "QOS_QOE_TSD" = 11)
    - luc do moi phai xem lai.

=== NULLABLE, KHONG server_default - CO CHU DICH ===

Cac dong cr_phieu tao TRUOC dot nay de NULL. KHONG backfill, KHONG doan nguoc
thanh 'QOS'. Ly do: luc do he thong CHI danh gia QoS (QoE con la mock tra 3.5
cung) nen khong ai biet cac cell do co dat QoE hay khong - dien 'QOS' vao se la
BIA MOT DU KIEN CHUA TUNG DUOC DO. Rat co the trong so do co cell khong dat ca
QoE ma he thong chua bao gio kiem.

NULL o day dung nghia "khong ghi nhan / chua co co che", va do chinh la thu can
phan biet khi thong ke "so phieu do QoE tu khi bat CEM".

=== DA CAT BOT SO VOI BAN AUTOGENERATE ===

Ban autogenerate sinh 18 thao tac; 17 trong so do KHONG lien quan cot moi - van
la DRIFT co san giua models/ va DB that, y het 3 lan truoc (80450814195f,
ce1a0d7996ac, e98069b2cd40):
  - doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_<col>):
    model dung index=True (Alembic tu dat ten) trong khi migration cu dat ten
    tay. 3 drop_index + 3 create_index.
  - them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id. 2 lenh.
  - cac op keo theo trong downgrade().
Da XOA het - migration nay CHI them DUNG 1 cot. Drift VAN CON, lan autogenerate
sau se lai de xuat, phai kiem tra tay moi lan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49066deb32a4'
down_revision: Union[str, Sequence[str], None] = 'e98069b2cd40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_phieu',
        sa.Column('nguon_khong_dat', sa.VARCHAR(length=10), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cr_phieu', 'nguon_khong_dat', schema=_SCHEMA)
