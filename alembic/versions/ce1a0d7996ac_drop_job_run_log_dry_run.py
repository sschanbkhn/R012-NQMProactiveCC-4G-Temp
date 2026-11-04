"""drop job_run_log.dry_run

Revision ID: ce1a0d7996ac
Revises: 80450814195f
Create Date: 2026-08-12 21:39:41.658250

V2 (yeu cau truc tiep user, 12/08) - BO HOAN TOAN che do dry_run cua job xuat
phieu. Moi luot chay deu POST THAT len TTS, nen cot nay chi con DUY NHAT 1 gia
tri (false) - khong phan biet duoc gi nua ma van bat moi cho doc (model, repo,
schema API, FE) phai mang theo.

AN TOAN DU LIEU - da kiem tra bang SELECT TRUOC khi viet migration nay:
  - system_nsn_nqmproactivecc.job_run_log            : 0 dong (bang con rong)
  - job_run_log WHERE dry_run IS TRUE                : 0 dong
  - cr_phieu WHERE trang_thai = 'DRY_RUN'            : 0 dong
Khong co du lieu nao can chuyen doi/backfill; drop cot la mat mat 0 thong tin.

DA CAT BOT SO VOI BAN AUTOGENERATE (doc truoc khi sua file nay):
Ban autogenerate sinh kem DUNG 8 thao tac KHONG lien quan cot nay - van la
DRIFT co san giua models/ va DB that, y het lan migration 80450814195f:
  - doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_<col>):
    model dung index=True (Alembic tu dat ten) trong khi migration cu dat ten
    tay. 3 drop_index + 3 create_index.
  - them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id. 2 lenh.
Da XOA ca 8 - migration nay CHI xoa dung 1 cot. Drift VAN CON, lan autogenerate
sau se lai de xuat, phai kiem tra tay moi lan.

downgrade() dung server_default=false + NOT NULL: neu phai quay lai, cac dong
job_run_log tao trong thoi gian khong co cot nay se nhan false - dung su that
(chung deu la luot POST that).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce1a0d7996ac'
down_revision: Union[str, Sequence[str], None] = '80450814195f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('job_run_log', 'dry_run', schema=_SCHEMA)


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'job_run_log',
        sa.Column('dry_run', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False),
        schema=_SCHEMA,
    )
