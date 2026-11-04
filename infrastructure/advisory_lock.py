"""
Advisory lock dung chung cho job xuat phieu.
Tach ra khoi infrastructure/scheduler.py 20082026 (yeu cau truc tiep user).

=== VI SAO TACH RA ===
Tu 20/08 co 2 duong cung chay job xuat phieu:
  1. scheduler tu dong (8h00 hang ngay)
  2. POST /jobs/xuat-phieu-auto (chay bu bang tay khi job lo ngay)
Ca hai PHAI dung CHUNG mot khoa, neu khong thi 2 duong chay chong nhau va
cung 1 cell bi POST 2 phieu len CTS. Copy doan lock sang router se thanh 2
ban cung co che - sua 1 cho quen cho kia.

=== VI SAO CONNECTION ASYNCPG THO, NGOAI POOL SQLALCHEMY ===
(Chep nguyen tu scheduler.py - day la ly do KHONG duoc doi cach lam.)
Advisory lock gan voi CONNECTION, khong phai transaction. Phai giu DUNG 1
connection RIENG suot vong doi job - KHONG dung AsyncSession cua repo:
session tra connection ve pool sau moi commit() (repo commit nhieu lan trong
1 luot), luc do lock se di theo connection vao pool va co the bi request khac
"thua ke", con unlock thi goi tren connection khac -> khong nha khoa.
Vi vay: 1 asyncpg connection tho, chi dung cho lock, dong tay o finally.
"""

import logging
from contextlib import asynccontextmanager

import asyncpg

from infrastructure.db import _ASYNCPG_DSN

logger = logging.getLogger(__name__)

# Khoa advisory cho job xuat phieu (tu dong VA chay tay - CUNG MOT KHOA, do
# la muc dich). So co dinh, KHONG duoc trung voi khoa cua he thong khac tren
# CUNG Postgres instance (DB dung chung 11+ schema, advisory lock la pham vi
# TOAN INSTANCE chu khong theo database/schema).
# Quy uoc tu dat: 7012 = R012 + tien to 7 cho "job". Neu them job khac dung
# advisory lock, PHAI chon so khac va ghi vao day.
KHOA_XUAT_PHIEU = 7012


@asynccontextmanager
async def giu_khoa(lock_key: int = KHOA_XUAT_PHIEU):
    """Thu lay advisory lock. Yield True neu lay duoc, False neu dang bi giu.

    LUON yield (khong raise khi khong lay duoc) - de caller tu quyet dinh:
    scheduler thoat em (khong phai loi), router tra 409. Hai phan ung khac
    nhau tren cung mot tinh huong, nen day khong phai viec cua ham nay.

    Connection LUON duoc dong o finally, ke ca khi than `with` nem loi.
    """
    conn = await asyncpg.connect(_ASYNCPG_DSN)
    da_lay_duoc = False
    try:
        da_lay_duoc = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_key)
        yield da_lay_duoc
    finally:
        # Nha khoa TRUOC khi dong connection. Ve ky thuat dong connection cung
        # tu nha khoa, nhung goi tuong minh de y dinh ro rang va khong phu
        # thuoc hanh vi ngam cua Postgres.
        if da_lay_duoc:
            try:
                await conn.fetchval("SELECT pg_advisory_unlock($1)", lock_key)
            except Exception as exc:  # noqa: BLE001 - connection co the da chet
                logger.warning(
                    "Khong nha duoc advisory lock (connection se dong, khoa tu nha)",
                    extra={"lock_key": lock_key, "loi": str(exc)},
                )
        await conn.close()
