"""dem theo CELL thay vi DN + bang cr_phieu_lan_thu + cr_session.duong_dan_log

Revision ID: b3f7d21ac504
Revises: 4ae6f4d7503b
Create Date: 2026-09-02 09:40:00.000000

Gom 3 thay doi doc lap nhung cung mot dot (A2 / A5 / A6).

===========================================================================
A2 - cr_session: BO so_dn_thanh_cong/so_dn_tong, THEM so_cell_thanh_cong/
     so_cell_tong
===========================================================================
CR lam viec theo CELL, khong theo tram. 1 managedObject trong XML NetAct =
1 CELL (LNCEL); MRBTS chi la noi cell cam vao, khong phai don vi tac dong.
Con so co nghia voi nguoi van hanh la "5/5 cell", khong phai "3/3 tram".

VI SAO XOA COT CU CHU KHONG DOI TEN (RENAME):
So dang nam trong 2 cot cu duoc dem theo DN (tram). Doi ten cot thanh
so_cell_* se BIEN gia tri cu thanh mot con so noi doi: session 2641 dang
mang 3/4 theo nghia TRAM, sau khi doi ten se doc thanh "3/4 cell" - sai
hoan toan va KHONG co cach nao nhin ra la sai. Xoa cot roi them cot moi
NULL thi cac session cu dung nghia "khong ghi nhan", va se duoc tinh lai
dung theo cell tu lan chay sau.

=> DU LIEU 2 COT CU BI MAT VINH VIEN khi chay upgrade. Da can nhac: gia tri
do dang SAI ve don vi do (dem tram, khong dem cell) nen khong co gi de tiec;
downgrade() tao lai cot nhung KHONG khoi phuc duoc so cu.

===========================================================================
A5 - Bang moi cr_phieu_lan_thu: lich su TUNG LAN POST len CTS
===========================================================================
_ghi_ket_qua_phieu() dang GHI DE tren cung 1 dong cr_phieu: khi cell chuyen
tu FAILED sang SUCCESS thi error_message bi set None -> MAT ly do CTS tu
choi o lan truoc. Da xay ra that voi 3 cell SSN121M*: nhin vao DB chi thay
SUCCESS, khong con dau vet vi sao 2 lan dau hong.

Bang nay ghi THEM 1 DONG moi lan POST, khong bao gio ghi de - nen giu duoc
TOAN BO lich su: lan nao, ai chay (job tu dong hay nguoi bam tay), gui gi,
CTS tra ve gi. cr_phieu van giu nguyen vai tro "trang thai HIEN TAI cua cell",
bang nay la "chuyen gi da xay ra".

FK cr_phieu_id -> cr_phieu.id dat ON DELETE CASCADE. LY DO + DANH DOI:
xoa_phieu_use_case dang chay DELETE FROM cr_phieu WHERE id = ? (hard delete,
xem adapters/postgres/cr_phieu_repo.py::xoa). Neu de FK mac dinh (NO ACTION)
thi ngay khi 1 phieu co lich su lan thu, endpoint DELETE /phieu/{id} se chet
vi vi pham FK - tinh nang dang chay se hong am tham. CASCADE giu tinh nang do
song, doi lai lich su lan thu cua phieu bi xoa cung mat theo. Chap nhan duoc
vi ban than dong cr_phieu (thu ma lich su nay mo ta) cung da bi xoa.

request_payload/response_body deu NULLABLE (khac cr_phieu.request_payload la
NOT NULL): co nhung lan that bai TRUOC khi kip dung payload hoac chua nhan
duoc response (timeout, dut ket noi) - ep NOT NULL se khien chinh nhung lan
hong nang nhat lai khong ghi lai duoc, tuc la mat dung du lieu can nhat.

thoi_diem KHONG co server_default=now(): Postgres server co TimeZone GUC =
Asia/Ho_Chi_Minh nen now() se ghi gio VN vao cot TIMESTAMPTZ thay vi UTC -
lenh cam nay ap dung cho MOI cot thoi gian trong project (C1.4-fix9). Gia tri
luon do Python gan bang datetime.now(timezone.utc).

ket_qua de VARCHAR(30) chu khong phai 20: bai hoc tu cr_phieu.trang_thai
(migration b7f4c2a91d38) - de 20 roi phai chay them 1 migration nua chi vi
mot gia tri dai 24 ky tu.

Chi 1 index tren cr_phieu_id: truy van duy nhat cua bang nay la "lay lich su
cua 1 phieu", khong co cho nao loc theo thoi_diem/ket_qua doc lap. Them index
chua dung toi chi lam cham INSERT (bang nay ghi moi lan POST).

===========================================================================
A6 - cr_session.duong_dan_log VARCHAR(500) NULL
===========================================================================
Tro toi file log NetAct trong docs/logs/netact_runs/. NULL o session cu va o
session chua chay xong. VARCHAR(500) du cho duong dan tuong doi + ten file co
timestamp; khong dung TEXT vi day la duong dan co do dai bi chan boi he dieu
hanh, khong phai noi dung tu do.

===========================================================================
GHI CHU VE AUTOGENERATE
===========================================================================
Alembic autogenerate tren schema nay LUON de xuat kem 8 thay doi index/FK
khong lien quan (drift giua model va DB that, da biet tu cac dot truoc). File
nay da CAT BO toan bo nhung de xuat do, chi giu dung 3 viec A2/A5/A6.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3f7d21ac504'
down_revision: Union[str, Sequence[str], None] = '4ae6f4d7503b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "system_nsn_nqmproactivecc"


def upgrade() -> None:
    """Upgrade schema."""
    # --- A2: doi don vi dem tu DN (tram) sang CELL ---
    # Them cot moi TRUOC khi xoa cot cu: neu co su co giua chung thi bang van
    # con it nhat mot bo cot doc duoc, khong roi vao trang thai khong con cot nao
    op.add_column(
        'cr_session',
        sa.Column('so_cell_thanh_cong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_session',
        sa.Column('so_cell_tong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    # Xoa han 2 cot cu - KHONG copy gia tri sang cot moi (xem ly do o docstring:
    # so cu dem theo tram, copy sang la bien no thanh so cell noi doi)
    op.drop_column('cr_session', 'so_dn_tong', schema=_SCHEMA)
    op.drop_column('cr_session', 'so_dn_thanh_cong', schema=_SCHEMA)

    # --- A6: duong dan file log NetAct ---
    op.add_column(
        'cr_session',
        sa.Column('duong_dan_log', sa.VARCHAR(length=500), nullable=True),
        schema=_SCHEMA,
    )

    # --- A5: bang lich su tung lan POST phieu len CTS ---
    op.create_table(
        'cr_phieu_lan_thu',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cr_phieu_id', sa.INTEGER(), nullable=False),
        sa.Column('thoi_diem', sa.TIMESTAMP(timezone=True), nullable=False),
        # JOB_AUTO | MANUAL - de VARCHAR chu khong phai ENUM Postgres: them gia
        # tri moi chi la them chuoi, khong phai migration doi kieu (cung quy uoc
        # voi cr_session.status / cr_phieu.trang_thai)
        sa.Column('nguoi_thuc_hien', sa.VARCHAR(length=20), nullable=False),
        # SUCCESS | FAILED
        sa.Column('ket_qua', sa.VARCHAR(length=30), nullable=False),
        sa.Column('phieu_id', sa.VARCHAR(length=100), nullable=True),
        sa.Column('error_message', sa.TEXT(), nullable=True),
        sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ['cr_phieu_id'], [f'{_SCHEMA}.cr_phieu.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=_SCHEMA,
    )
    op.create_index(
        'idx_cr_phieu_lan_thu_phieu',
        'cr_phieu_lan_thu',
        ['cr_phieu_id'],
        unique=False,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Thu tu NGUOC voi upgrade() - giu quy uoc de doc doi chieu cho de
    op.drop_index('idx_cr_phieu_lan_thu_phieu', table_name='cr_phieu_lan_thu', schema=_SCHEMA)
    op.drop_table('cr_phieu_lan_thu', schema=_SCHEMA)

    op.drop_column('cr_session', 'duong_dan_log', schema=_SCHEMA)

    # Tao lai 2 cot DN cu de schema khop lai voi ban truoc. CANH BAO: chi tao
    # lai CAU TRUC, gia tri cu da mat tu luc upgrade() - moi dong se la NULL
    op.add_column(
        'cr_session',
        sa.Column('so_dn_thanh_cong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        'cr_session',
        sa.Column('so_dn_tong', sa.INTEGER(), nullable=True),
        schema=_SCHEMA,
    )
    op.drop_column('cr_session', 'so_cell_tong', schema=_SCHEMA)
    op.drop_column('cr_session', 'so_cell_thanh_cong', schema=_SCHEMA)
