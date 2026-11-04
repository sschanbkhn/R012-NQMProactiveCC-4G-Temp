"""
Alembic env.py - async template (tuong thich DATABASE_URL dung asyncpg).
Tu: DB_SCHEMA.md Section 9; TASK_LIST.md B4.9

Sinh boi `alembic init -t async`, tuy bien them:
- load_dotenv() + config.set_main_option("sqlalchemy.url", ...) de doc DATABASE_URL
  tu .env, giong het pattern infrastructure/db.py (B1.6). "%" trong URL (percent-
  encoding, vd "%40") duoc escape thanh "%%" truoc khi set - configparser (dung
  boi set_main_option) hieu "%" la ky tu interpolation, neu khong se ValueError.
- target_metadata = SQLModel.metadata (B4.9) - import du 8 model (B4.1-B4.8) theo
  dung thu tu DB_SCHEMA.md Section 9 dong 428-435.
- include_schemas / include_name / version_table_schema (11072026): 8 bang R012
  chuyen sang schema rieng "system_nsn_nqmproactivecc" (models/__init__.py) - DB
  dung chung voi 11 schema he thong khac. Xem comment chi tiet ngay tren
  _include_name() ben duoi - bat buoc phai co include_name, khong phai tuy chon.

TODO: load_dotenv() call site thu 3 trong project (sau infrastructure/db.py,
infrastructure/logger.py). Chua co config.py/settings tap trung trong docs -
xem TODO tuong tu trong db.py/logger.py.
"""
import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_dotenv()
# configparser (dung boi set_main_option) hieu "%" la ky tu interpolation -
# URL co percent-encoding (VD: "%40" cho ky tu "@" trong password) phai escape
# thanh "%%" truoc khi set, neu khong ValueError "invalid interpolation syntax".
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "").replace("%", "%%"))

from models.tram import Tram
from models.cr_session import CrSession
from models.cell_params import CellParams
from models.cr_log import CrLog
from models.qoe_snapshot import QoeSnapshot
from models.qos_snapshot import QosSnapshot
from models.alert_log import AlertLog
from models.audit_log import AuditLog
from models.cr_affected_cells import CrAffectedCells  # them 22072026 - Phuong an B
from models.cr_phieu import CrPhieu  # them KHOI 2/5 SaveCellClm - audit + chong trung
# A5 (02092026) - lich su tung lan POST phieu. PHAI import o day, khong thi
# autogenerate lan sau se coi bang nay la 'thua trong DB' va de xuat DROP
from models.cr_phieu_lan_thu import CrPhieuLanThu
from models.job_run_log import JobRunLog  # them 11/08 (JOB TU DONG buoc 1/4) - lich su moi lan job chay
from sqlmodel import SQLModel

target_metadata = SQLModel.metadata

# DB dung chung 1 Postgres instance voi 11 schema khac (system_nsn_had,
# system_nsn_prbsloadcell, system_oss, system_ericsson, Reports, Common,
# system_nsn_sleepingcell, system_nsn_declare5Gzerotouch, ...). R012 dung schema
# rieng "system_nsn_nqmproactivecc" (models/__init__.py).
#
# include_schemas=True can THIET de Alembic biet quet schema khac "public" —
# nhung mac dinh, khi bat include_schemas, Alembic se reflect TAT CA schema
# trong DB roi so sanh voi target_metadata (chi co 8 bang cua R012) -> se de
# xuat DROP cho MOI bang cua 11 he thong khac (vi ho "co trong DB nhung khong
# co trong metadata cua ta"). include_name loc lai: CHI so sanh trong dung 1
# schema cua R012, bo qua hoan toan moi schema khac — bat buoc phai co, khong
# phai tuy chon, neu khong autogenerate se de xuat pha du lieu he thong khac.
#
# version_table_schema: bang alembic_version (tracking migration da chay) cung
# duoc dat trong schema rieng cua R012 thay vi public — dung tinh than "moi he
# thong 1 schema doc lap" da neu ra, tranh nhieu he thong chia chung 1 bang
# version tracking trong public (neu he thong khac cung dung Alembic).
_R012_SCHEMA = target_metadata.schema


def _include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == _R012_SCHEMA
    if type_ == "table":
        # Phong thu theo chieu sau (11072026, sau review): ve ly thuyet nhanh
        # nay khong bao gio nhan bang thuoc schema da bi loai o tren, vi
        # Alembic (verify source that, autogenerate/compare/schema.py dong
        # 36-48 + autogenerate/compare/tables.py dong 50-62, version 1.18.5)
        # loc "schemas" truoc, roi CHI enumerate get_table_names() cho schema
        # da qua loc. Nhung day la hanh vi noi bo, khong phai API duoc dam bao
        # on dinh giua cac version Alembic - check tuong minh o day de khong
        # phu thuoc vao thu tu goi ben trong. Key "schema_name" trong
        # parent_names da verify truc tiep tu source: autogenerate/api.py dong
        # 439, 445; autogenerate/compare/tables.py dong 61.
        return parent_names.get("schema_name") == _R012_SCHEMA
    return True


def include_object(object_, name, type_, reflected, compare_to):
    """Chan autogenerate de xuat DROP cho bang co THAT trong DB nhung khong co
    model SQLModel.

    BUG THAT da xay ra (buoc 1/4 job tu dong): `cell_infor` (27763 dong du lieu
    RF that, la nguon cua TOAN BO flow trigger CR) duoc tao bang script NGOAI
    Alembic va truy cap qua raw asyncpg nen KHONG co model SQLModel ->
    autogenerate coi la "thua" va sinh `op.drop_table('cell_infor')`. Lan do
    phai cat tay khoi migration 6ce3193f60b5. Neu ai do chay autogenerate roi
    `upgrade head` ma khong doc file, se mat sach 27763 dong.

    VIET GENERIC - CO Y KHONG hardcode ten "cell_infor": nguyen tac fail-safe.
    Bo sot 1 lenh drop CAN THIET thi lam tay duoc (mat vai phut), con drop nham
    1 bang co du lieu that thi mat du lieu (co the khong khoi phuc duoc). Bang
    nao roi vao dien nay sau nay (script khac tu tao bang) cung duoc bao ve san,
    khong phai nho sua ham nay.

    reflected=True nghia la object doc len TU DB THAT (khong phai tu
    target_metadata) - chi khi do moi co chuyen "co trong DB, khong co trong
    metadata". Object cua metadata (reflected=False) luon cho qua.

    LUU Y KHI THAT SU MUON DROP 1 BANG: filter nay se chan luon lenh drop do -
    phai TAM TAT filter (comment dong include_object trong context.configure())
    de sinh migration, roi bat lai ngay sau khi sinh xong.
    """
    if type_ == "table" and reflected and name not in target_metadata.tables:
        # Ten trong target_metadata.tables co dang "<schema>.<table>" vi
        # SQLModel.metadata.schema da duoc set (models/__init__.py) - phai
        # doi chieu CA 2 dang, neu chi so ten tran se chan nham MOI bang.
        if f"{_R012_SCHEMA}.{name}" not in target_metadata.tables:
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=_include_name,
        # Chan drop bang khong co model - xem docstring include_object().
        include_object=include_object,
        version_table_schema=_R012_SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
        # Chan drop bang khong co model - xem docstring include_object().
        include_object=include_object,
        version_table_schema=_R012_SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
