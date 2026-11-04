"""add_so_lan_thu_to_cr_phieu

Revision ID: 80450814195f
Revises: 6ce3193f60b5
Create Date: 2026-08-12 14:08:28.961116

Viec 2b (yeu cau truc tiep user) - them cot dem so lan DA THU XUAT THAT cho 1
cell.

VI SAO CAN COT RIENG (khong suy ra duoc tu du lieu co san):
`uq_cr_phieu_session_cell UNIQUE (cr_session_id, cell_name)` chi cho DUNG 1
dong / cell / session. Khi xuat lai, `XuatPhieuUseCase` TAI DUNG dong cu va
`update_result()` GHI DE hoan toan (trang_thai/response_body/phieu_id/
error_message/request_payload) - khong con dau vet cua lan thu truoc. `created_at`
cung khong giup vi do la luc tao dong DAU TIEN, khong doi qua cac lan retry.
Khong co cot nay thi phieu FAILED do loi DU LIEU (vd CTS tra 400 vi 1 field sai)
se bi job thu lai VO HAN moi ngay.

server_default='0' + NOT NULL: 2 dong CU dang co trong bang tu nhien nhan gia
tri 0 - dung y nghia "chua dem lan nao", KHONG can backfill tay. Day KHONG phai
cot thoi gian nen server_default an toan (lenh cam server_default chi ap dung
cho timestamp - C1.4-fix9, do Postgres server TimeZone GUC = Asia/Ho_Chi_Minh).

DA CAT BOT SO VOI BAN AUTOGENERATE (doc truoc khi sua file nay):
Ban autogenerate sinh kem 8 thao tac KHONG lien quan cot moi, deu la DRIFT co
san giua models/ va DB that tu truoc:
  - doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_<col>):
    do model dung index=True (Alembic tu dat ten) trong khi migration cu dat ten
    tay. 3 drop_index + 3 create_index.
  - them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id. 2 lenh.
Da XOA ca 8 - migration nay CHI them/xoa dung 1 cot. Drift VAN CON, lan
autogenerate sau se lai de xuat, phai kiem tra tay moi lan.

(Ban autogenerate lan nay KHONG con sinh op.drop_table('cell_infor') - filter
include_object trong alembic/env.py da chan tu goc, xem migration 6ce3193f60b5.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80450814195f'
down_revision: Union[str, Sequence[str], None] = '6ce3193f60b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cr_phieu',
        sa.Column('so_lan_thu', sa.INTEGER(), server_default=sa.text('0'), nullable=False),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cr_phieu', 'so_lan_thu', schema=_SCHEMA)
