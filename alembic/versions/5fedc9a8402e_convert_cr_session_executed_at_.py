"""convert cr_session executed_at evaluated_at to timestamptz

Revision ID: 5fedc9a8402e
Revises: 4af97c72f2fb
Create Date: 2026-07-21 13:06:54.693321

C1.4-fix10 (21072026, dieu tra rieng roi xac nhan voi user): cr_session.
executed_at/evaluated_at bi loai KHOI pham vi 13 cot cua C1.4-fix9 vi ly do
luc do la "gia tri Python da set dung UTC tu truoc, khong dinh bug
server_default=now()" - dung ve mat GIA TRI, nhung sot mat he qua: 2 cot
nay van la TIMESTAMP WITHOUT TIME ZONE (naive), nen SQLAlchemy/asyncpg doc
len tra ve datetime KHONG co tzinfo -> response JSON (Pydantic v2) khong
them "Z"/offset, khac voi created_at/updated_at (da la TIMESTAMPTZ, doc len
tz-aware, co "Z"). BE tra ve khong nhat quan giua cac field timestamp dù
gia tri UTC deu dung.

Khac voi 13 cot C1.4-fix9 (du lieu cu THAT SU sai gio VN can AT TIME ZONE
'Asia/Ho_Chi_Minh' de sua), 2 cot nay CHUA TUNG bi bug gia tri - moi dong
da duoc ghi bang datetime.now(timezone.utc) (trigger_cr_use_case.py dong
416, evaluate_cr_use_case.py dong 314) roi moi bi tang repo strip tzinfo
truoc khi INSERT/UPDATE (adapters/postgres/cr_session_repo.py). Vi vay
dung "AT TIME ZONE 'UTC'" (KHONG phai 'Asia/Ho_Chi_Minh') - chi GAN nhan
UTC dung cho gia tri wall-clock da la UTC san, KHONG dich chuyen gio.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fedc9a8402e'
down_revision: Union[str, Sequence[str], None] = '4af97c72f2fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"
_TABLE = "cr_session"
_COLUMNS = ["executed_at", "evaluated_at"]


def upgrade() -> None:
    """Upgrade schema."""
    for column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_SCHEMA}."{_TABLE}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMPTZ '
            f"USING \"{column}\" AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_SCHEMA}."{_TABLE}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMP '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )
