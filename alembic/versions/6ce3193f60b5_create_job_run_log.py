"""create_job_run_log

Revision ID: 6ce3193f60b5
Revises: f717675f110d
Create Date: 2026-08-11 17:17:38.520044

JOB TU DONG buoc 1/4 (yeu cau truc tiep user) - luu lich su MOI LAN job/
scheduler chay (job dau tien: "xuat_phieu_auto"). Xem ly do can bang rieng
(khong dung cr_log/audit_log) trong models/job_run_log.py.

started_at/finished_at TIMESTAMPTZ KHONG server_default=now() - C1.4-fix9 da
xac nhan Postgres server TimeZone GUC = Asia/Ho_Chi_Minh, now() se ghi GIO VN
thay vi UTC. Luon set qua Python datetime.now(timezone.utc) trong adapter.
Cac cot so/bool VAN dung server_default (0/false) - khong dinh gi toi timezone,
giong alert_log.is_acknowledged da lam.

DA CAT BOT SO VOI BAN AUTOGENERATE (quan trong - doc truoc khi sua file nay):
alembic revision --autogenerate sinh kem 8 thao tac KHONG lien quan job_run_log,
deu la DRIFT co san giua models/ va DB THAT tu truoc:
  1. op.drop_table('cell_infor')  <-- NGUY HIEM NHAT: bang that dang co 27763
     dong, la nguon du lieu RF cua toan bo flow trigger CR. Bang nay duoc tao
     bang script ngoai Alembic va KHONG co model SQLModel (truy cap qua raw
     asyncpg - adapters/postgres/cell_infor_repo.py) nen autogenerate luon coi
     no la "thua" va de xuat DROP.
  2. Doi ten index cr_affected_cells/cr_phieu (idx_* -> ix_<schema>_<table>_*)
     - do model dung index=True (Alembic tu dat ten) trong khi migration cu dat
     ten tay.
  3. Them FK cell_params.tram_id / cr_session.tram_id -> tram.tram_id.
Tat ca deu NGOAI PHAM VI buoc 1/4 va rui ro cao (mot cai xoa du lieu that), da
XOA khoi migration nay - migration chi tao DUNG bang job_run_log + 2 index cua
no. Drift tren VAN CON, lan autogenerate sau se lai de xuat - PHAI kiem tra
tay moi lan, dac biet dong drop_table('cell_infor').
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6ce3193f60b5'
down_revision: Union[str, Sequence[str], None] = 'f717675f110d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_run_log',
        sa.Column('id', sa.Integer(), nullable=False),
        # Loai job - "xuat_phieu_auto" truoc mat, de ngo cho job khac dung chung
        # bang (VARCHAR + index thay vi Enum: them loai moi khong can migration).
        sa.Column('job_type', sa.VARCHAR(length=50), nullable=False),
        # KHONG server_default=sa.text('now()') - xem docstring dau file.
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False),
        # NULL = job chua xong (hoac chet giua chung, xem models/job_run_log.py).
        sa.Column('finished_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('trang_thai', sa.VARCHAR(length=20), nullable=False),
        sa.Column('dry_run', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False),
        sa.Column('so_session_quet', sa.INTEGER(), server_default=sa.text('0'), nullable=False),
        sa.Column('so_phieu_thanh_cong', sa.INTEGER(), server_default=sa.text('0'), nullable=False),
        sa.Column('so_phieu_that_bai', sa.INTEGER(), server_default=sa.text('0'), nullable=False),
        sa.Column('so_cell_vuot_gioi_han', sa.INTEGER(), server_default=sa.text('0'), nullable=False),
        sa.Column('error_message', sa.TEXT(), nullable=True),
        sa.Column('chi_tiet', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # KHONG co FK toi cr_session: 1 dong = 1 LUOT chay job (quet nhieu
        # session), khac cr_log/cr_phieu/cr_affected_cells (du lieu CUA 1 session).
        schema=_SCHEMA,
    )
    # DESC index - man hinh lich su luon xem luot MOI NHAT truoc; index ASC mac
    # dinh khong phuc vu duoc thu tu nay. sa.literal_column() la dung pattern da
    # co o f582103cf794 (idx_cr_session_created_at/idx_alert_created/idx_audit_created).
    op.create_index(
        'idx_job_run_log_started', 'job_run_log', [sa.literal_column('started_at DESC')],
        unique=False, schema=_SCHEMA,
    )
    op.create_index(
        op.f('ix_system_nsn_nqmproactivecc_job_run_log_job_type'), 'job_run_log', ['job_type'],
        unique=False, schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_system_nsn_nqmproactivecc_job_run_log_job_type'),
        table_name='job_run_log', schema=_SCHEMA,
    )
    op.drop_index('idx_job_run_log_started', table_name='job_run_log', schema=_SCHEMA)
    op.drop_table('job_run_log', schema=_SCHEMA)
