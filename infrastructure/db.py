"""
AsyncEngine, AsyncSessionLocal, get_session() cho FastAPI Depends().
Tu: DB_SCHEMA.md Section 10 (Async engine setup); TASK_LIST.md B1.6

Chua noi vao main.py lifespan (xem B1.5, con TODO) - se noi khi xac nhan rieng.
"""
import os

import asyncpg
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# TODO: tinh den 2026-07-10, load_dotenv() duoc goi o 3 noi (day, infrastructure/logger.py
# tu B1.7, va alembic/env.py tu B1.9). ARCHITECTURE.md Section 11 khong co
# infrastructure/config.py hay settings tap trung nao duoc len ke hoach - neu sau nay them
# file do, can don load_dotenv() ve entrypoint (main.py) hoac config.py thay vi de rai rac
# tung module. Chua co quyet dinh chinh thuc trong docs.
load_dotenv()  # doc DATABASE_URL tu .env - khong co trong DB_SCHEMA.md snippet nhung can de bien ton tai

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,     # check connection health
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# CellInforRepo (quyet dinh 12/07/2026) dung raw asyncpg (.fetch() truc tiep), KHONG
# phai SQLAlchemy AsyncSession nhu cac repo khac — KHONG co provider san co
# nao cho truong hop nay truoc gio, them moi o day (12072026, xac nhan voi
# user). Mo 1 connection MOI moi lan goi (KHONG pool) — dung y het pattern da
# co san trong adapters/netact/import_cell_params_csv.py/import_4G_cell_infor.py
# (asyncpg.connect(dsn) tho, khong pool). TODO: can nhac dung asyncpg.create_pool()
# neu sau nay CellInforRepo duoc goi voi tan suat cao (moi request 1 connection
# moi kem chi phi handshake TCP+TLS) — chua toi uu o day, giu don gian truoc.
_ASYNCPG_DSN = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None


async def get_asyncpg_connection():
    conn = await asyncpg.connect(_ASYNCPG_DSN)
    try:
        yield conn
    finally:
        await conn.close()
