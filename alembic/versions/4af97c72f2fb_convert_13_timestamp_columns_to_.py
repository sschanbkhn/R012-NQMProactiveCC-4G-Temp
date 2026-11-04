"""convert_13_timestamp_columns_to_timestamptz

Revision ID: 4af97c72f2fb
Revises: c67cefa52d9e
Create Date: 2026-07-21 07:53:30.642729

C1.4-fix9 (21072026, xac nhan voi user, Phan 2/3): 13 cot TIMESTAMP (khong tz)
dung server_default=now() bi loi that - Postgres server TimeZone GUC =
Asia/Ho_Chi_Minh (xac nhan truc tiep tren DB that: SELECT now()::timestamp
tra ve gia tri LECH +7h so voi UTC that), nen moi lan INSERT khong truyen
gia tri, cot nay bi ghi GIO VN thay vi UTC - trong khi cac cot Python tu set
(executed_at, updated_at cua cr_session qua repo...) deu dung UTC. 2 chuan
khac nhau tren cung 1 bang gay nham lan khi doi chieu (vd created_at "trong
nhu" dung GMT+7 khi hien thi truc tiep, nhung that ra la BUG chu khong phai
thiet ke).

Sua theo huong B (da chot voi user): doi ca 13 cot sang TIMESTAMPTZ (luu
UTC that, tu convert dung bat ke session TimeZone doc/ghi la gi) + bo
server_default=now() (models/ sua rieng, xem C1.4-fix9 trong DEV_LOG.md) -
tu nay MOI timestamp deu do Python set datetime.now(timezone.utc) ro rang,
khong con phu thuoc TimeZone GUC cua server nua.

Data cu: user da xac nhan la du lieu TEST, BO QUA (khong can dung tuyet
doi). Dung "USING col AT TIME ZONE 'Asia/Ho_Chi_Minh'" (thay vi de Postgres
tu suy ngam dinh theo session TimeZone cua ket noi chay migration) de
migration cho ra ket qua ON DINH, khong phu thuoc TimeZone GUC cua ket noi
dang chay no.

LUU Y QUAN TRONG (phat hien khi doi chieu du lieu that sau khi chay): 8/13
cot "created_at" (tram/cr_session/cell_params/cr_log/alert_log/audit_log/
qoe_snapshot/qos_snapshot) CHAC CHAN toan bo la GMT+7 wall-clock (KHONG co
code Python nao tung set created_at - ray soat toan bo repo/script xac
nhan) nen AT TIME ZONE 'Asia/Ho_Chi_Minh' convert DUNG 100% cho nhom nay.
Nhung 5 cot con lai (tram.last_synced_at/updated_at, cr_session.updated_at,
cell_params.last_synced_at/updated_at) la HON HOP: 1 so dong da duoc repo
Python set dung UTC tu truoc (vd CrSessionRepo.update(), CellParamsRepo.
upsert(), EnodebRepo.upsert_many() - deu dung datetime.now(timezone.utc)),
1 so dong khac (ghi qua raw SQL now() cua script doc lap
sync_tram_from_enodeb.py/import_cell_params_csv.py TRUOC KHI duoc sua o
C1.4-fix9) moi thuc su la GMT+7 sai. Khong the phan biet 2 loai nay bang
SQL (khong co cot danh dau nguon ghi) nen AT TIME ZONE ap dung DONG LOAT -
CHINH XAC cho dong tung ghi qua script cu, nhung LAM LECH THEM -7h cho
dong da dung san (vi du xac nhan that: session #203 - cr_session.updated_at
truoc migration la 17:50:48 UTC (dung), sau migration thanh 10:50:48 UTC
(sai) vi bi tru nham 7h). Chap nhan duoc THEO DUNG pham vi user da xac nhan
("data cu test, bo qua") - KHONG the sua triet de o muc SQL migration (du
lieu nguon khong the phan biet), chi luu y de bao cao ro rang thay vi bao
sai la "vo tinh sua dung het data cu".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4af97c72f2fb'
down_revision: Union[str, Sequence[str], None] = 'c67cefa52d9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"

# 13 cot dung server_default=now() - DUNG 13 nay, KHONG dong cac cot Python
# da tu set truoc gio (executed_at/evaluated_at cua cr_session,
# acknowledged_at cua alert_log) - cac cot do da UTC dung tu truoc, khong
# co bug, giu nguyen TIMESTAMP thuong (xem DEV_LOG.md muc [C1.4-fix9] cho
# ly do day du phan loai 13/16 cot timestamp).
_COLUMNS = [
    ("tram", "last_synced_at"),
    ("tram", "created_at"),
    ("tram", "updated_at"),
    ("cr_session", "created_at"),
    ("cr_session", "updated_at"),
    ("cell_params", "last_synced_at"),
    ("cell_params", "created_at"),
    ("cell_params", "updated_at"),
    ("cr_log", "created_at"),
    ("alert_log", "created_at"),
    ("audit_log", "created_at"),
    ("qoe_snapshot", "created_at"),
    ("qos_snapshot", "created_at"),
]


def upgrade() -> None:
    """Upgrade schema."""
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_SCHEMA}."{table}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMPTZ '
            f"USING \"{column}\" AT TIME ZONE 'Asia/Ho_Chi_Minh'"
        )
        # DROP DEFAULT rieng (khong gop chung 1 lenh ALTER TABLE voi TYPE) -
        # Postgres cho phep nhieu ALTER COLUMN trong 1 cau lenh nhung tach
        # rieng o day de moi buoc ro rang, de doc log neu loi giua chung.
        op.execute(f'ALTER TABLE {_SCHEMA}."{table}" ALTER COLUMN "{column}" DROP DEFAULT')


def downgrade() -> None:
    """Downgrade schema."""
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_SCHEMA}."{table}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMP '
            f'USING "{column}" AT TIME ZONE \'Asia/Ho_Chi_Minh\''
        )
        op.execute(
            f'ALTER TABLE {_SCHEMA}."{table}" ALTER COLUMN "{column}" SET DEFAULT now()'
        )
