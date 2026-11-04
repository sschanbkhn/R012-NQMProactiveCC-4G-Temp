"""
Fixture TU TAO du lieu cho test tien trinh (20082026, huong C da chot).

=== VI SAO BO DU LIEU MOCK SEED SAN ===
Truoc day 9 test o test_sessions_tien_trinh_integration.py ghim vao 12 session
MOCK* seed bang scripts/seed_mock_process_data.py. Van de GOC: seed dung NGAY
CO DINH, ma scheduler THAT van chay hang ngay tren cung DB - moi session mock
deu di qua buoc 2 -> buoc 4 theo thoi gian. MOCK996 da bi quet that ngay 19/08
(job_run_log id=735). Mock tu no mat gia tri phan biet, va test phai them guard
skip - tuc la xanh ma khong kiem gi.

Nay moi test TU TAO du lieu no can va TU DON o teardown: khong phu thuoc ai da
seed hay chua, khong mat gia tri theo thoi gian.

=== 2 DIEM AN TOAN PHAI GIU ===

1. executed_at KHONG BAO GIO duoc roi vao (hom nay - XUAT_PHIEU_AFTER_DAYS).
   Job xuat phieu quet theo DUNG 2 dieu kien: ngay CR == hom nay - 8 VA status
   thuoc whitelist - no KHONG xet xuat_phieu_at. Nen mot session test roi trung
   ngay do se bi scheduler THAT quet va POST PHIEU THAT len CTS.
   Chan bang 2 lop: chon offset xa (60/2/45) VA assert trong _kiem_offset_an_toan()
   - neu ai doi XUAT_PHIEU_AFTER_DAYS thanh 60 thi test FAIL NGAY thay vi am
   tham cho scheduler chay that.

2. Teardown phai xoa DU cac bang co FK toi cr_session. Thieu 1 bang la teardown
   chet giua chung -> dong tram sot lai -> lan chay sau "duplicate key tram_id"
   ngay o setup. DA GAP 2 LAN (19/08 va 20/08). O day tai dung DUNG chuoi xoa
   cua fixture test_tram trong conftest.py.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import delete, select, update as sa_update

from application.xuat_phieu_use_case import XUAT_PHIEU_AFTER_DAYS
from domain.entities.cr_session import CrStatus
from models.alert_log import AlertLog as AlertLogModel
from models.audit_log import AuditLog as AuditLogModel
from models.cell_params import CellParams as CellParamsModel
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel
from models.cr_log import CrLog as CrLogModel
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_session import CrSession as CrSessionModel
from models.qoe_snapshot import QoeSnapshot as QoeSnapshotModel
from models.qos_snapshot import QosSnapshot as QosSnapshotModel
from models.tram import Tram as TramModel

# Tien to RIENG, khong trung TEST_B5_ (fixture test_tram) va khong trung MOCK
# (du lieu seed cu). Teardown loc theo tien to nay nen no phai la duy nhat.
TIEN_TO = "TEST_TT_"

TRAM_XONG = f"{TIEN_TO}XONG"
TRAM_CHO_KPI = f"{TIEN_TO}CHOKPI"
TRAM_QUA_HAN = f"{TIEN_TO}QUAHAN"
TRAM_CR_LOI = f"{TIEN_TO}CRLOI"

# So ngay LUI so voi hom nay cho tung tinh huong. Tinh TUONG DOI, KHONG hardcode
# ngay - do chinh la loi cua bo mock cu.
#
# 2 = "vua chay CR, dang cho KPI" -> con 6 ngay nua moi den han (KHONG qua han).
# 45/60 = qua han tu lau.
_OFFSET = {
    TRAM_XONG: 60,
    TRAM_CHO_KPI: 2,
    TRAM_QUA_HAN: 45,
}


def _kiem_offset_an_toan() -> None:
    """CHAN CUNG: khong offset nao duoc trung ngay job quet.

    Neu trung, scheduler THAT se quet du lieu test va POST phieu THAT len CTS -
    khong thu hoi duoc. Fail o day (RO RANG) tot hon nhieu so voi phat hien sau
    khi phieu da len TTS.
    """
    trung = [ten for ten, n in _OFFSET.items() if n == XUAT_PHIEU_AFTER_DAYS]
    if trung:
        raise AssertionError(
            f"NGUY HIEM: offset cua {trung} trung XUAT_PHIEU_AFTER_DAYS="
            f"{XUAT_PHIEU_AFTER_DAYS} - scheduler THAT se quet du lieu test va "
            "POST phieu that len CTS. Doi so trong _OFFSET."
        )


def _luc(so_ngay_truoc: int) -> datetime:
    """Moc thoi gian tz-aware, 12h trua GMT+7 cua (hom nay - N).

    12h trua: doi mui gio khong bao gio lam lech sang ngay khac (cung ly do da
    chon trong tests/unit/test_xuat_phieu_job.py)."""
    gmt7 = timezone(timedelta(hours=7))
    ngay = (datetime.now(timezone.utc) + timedelta(hours=7)).date() - timedelta(days=so_ngay_truoc)
    return datetime(ngay.year, ngay.month, ngay.day, 12, 0, tzinfo=gmt7)


async def _don_sach(db_session) -> None:
    """Xoa moi du lieu mang tien to TIEN_TO, dung thu tu nguoc FK.

    Chay CA TRUOC lan SAU test: lan chay truoc bi Ctrl-C/crash se de lai rac
    lam lan nay "duplicate key" ngay o setup. Don dau vao la bai hoc da rut tu
    clean_job_run_log."""
    session_ids = select(CrSessionModel.id).where(CrSessionModel.tram_id.like(f"{TIEN_TO}%"))

    await db_session.execute(
        delete(QosSnapshotModel).where(QosSnapshotModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(
        delete(QoeSnapshotModel).where(QoeSnapshotModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(delete(CrPhieuModel).where(CrPhieuModel.cr_session_id.in_(session_ids)))
    await db_session.execute(delete(CrLogModel).where(CrLogModel.cr_session_id.in_(session_ids)))
    await db_session.execute(
        delete(CrAffectedCellsModel).where(CrAffectedCellsModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(
        delete(CellParamsModel).where(CellParamsModel.tram_id.like(f"{TIEN_TO}%"))
    )
    await db_session.execute(delete(AlertLogModel).where(AlertLogModel.cr_session_id.in_(session_ids)))
    # audit_log/rollback_of_id SET NULL chu KHONG xoa - xem ly do trong
    # conftest.py::test_tram (vet kiem toan phai song lau hon doi tuong bi
    # thao tac; rollback_of_id nam tren mot session KHAC).
    await db_session.execute(
        sa_update(AuditLogModel)
        .where(AuditLogModel.cr_session_id.in_(session_ids))
        .values(cr_session_id=None)
    )
    await db_session.execute(
        sa_update(CrSessionModel)
        .where(CrSessionModel.rollback_of_id.in_(session_ids))
        .values(rollback_of_id=None)
    )
    await db_session.execute(
        delete(CrSessionModel).where(CrSessionModel.tram_id.like(f"{TIEN_TO}%"))
    )
    await db_session.execute(delete(TramModel).where(TramModel.tram_id.like(f"{TIEN_TO}%")))
    await db_session.commit()


async def _tao_tram(db_session, tram_id: str) -> None:
    db_session.add(
        TramModel(tram_id=tram_id, tram_name=f"TEST TIEN TRINH {tram_id}", trang_thai="active")
    )
    await db_session.commit()


async def _tao_session(
    db_session,
    tram_id: str,
    status: CrStatus,
    executed_at: datetime | None,
    xuat_phieu_at: datetime | None = None,
) -> int:
    row = CrSessionModel(
        tram_id=tram_id,
        action="shutdown",
        status=status.value,
        plan_name=f"R012_TEST_TT_{tram_id}",
        executed_at=executed_at,
        xuat_phieu_at=xuat_phieu_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row.id


@pytest_asyncio.fixture
async def du_lieu_tien_trinh(db_session):
    """4 session dai dien 4 tinh huong tien trinh. Tra dict {ten: cr_session_id}.

    Dung 4 TRAM RIENG (khong gom vao 1 tram) de test tim duoc dung dong bang
    q=<tram_id> - `q` chi tim trong cr_session.tram_id va tram.tram_name.

    Status chon THEO DUNG NGHIEP VU (DONE/FAILED) chu khong chon status la cho
    "an toan voi scheduler": du lieu vo nghia (vd PENDING ma da co xuat_phieu_at)
    se lam nguoi doc test sau nay hieu sai luat. An toan bao dam bang NGAY thay
    vi bang status - xem _kiem_offset_an_toan().
    """
    _kiem_offset_an_toan()
    await _don_sach(db_session)

    ids = {}

    # 1) XONG DAY DU -> buoc 4. 6 cell anh huong, 4 phieu SUCCESS, 0 cho tay.
    await _tao_tram(db_session, TRAM_XONG)
    sid = await _tao_session(
        db_session,
        TRAM_XONG,
        CrStatus.DONE,
        executed_at=_luc(_OFFSET[TRAM_XONG]),
        xuat_phieu_at=_luc(_OFFSET[TRAM_XONG] - XUAT_PHIEU_AFTER_DAYS),
    )
    ids["xong"] = sid
    for i in range(6):
        db_session.add(
            CrAffectedCellsModel(
                cr_session_id=sid,
                cell_name=f"{TIEN_TO}CELL_{i}",
                tram_id=TRAM_XONG,
                huong_id="11",
                created_at=datetime.now(timezone.utc),
            )
        )
    for i in range(4):
        db_session.add(
            CrPhieuModel(
                cr_session_id=sid,
                cell_name=f"{TIEN_TO}CELL_{i}",
                trang_thai="SUCCESS",
                request_payload={"TenCell": f"{TIEN_TO}CELL_{i}"},
                phieu_id=f"TEST{i}",
                created_at=datetime.now(timezone.utc),
            )
        )
    await db_session.commit()

    # 2) DANG CHO KPI -> buoc 2, CHUA qua han (con 6 ngay). CO Y 0 cell: con so
    #    dem phai ra 0, khong duoc None hay loi.
    await _tao_tram(db_session, TRAM_CHO_KPI)
    ids["cho_kpi"] = await _tao_session(
        db_session,
        TRAM_CHO_KPI,
        CrStatus.DONE,
        executed_at=_luc(_OFFSET[TRAM_CHO_KPI]),
    )

    # 3) QUA HAN -> buoc 2, da tre han tu lau (PA A: mat vinh vien, khong quet lai).
    await _tao_tram(db_session, TRAM_QUA_HAN)
    ids["qua_han"] = await _tao_session(
        db_session,
        TRAM_QUA_HAN,
        CrStatus.DONE,
        executed_at=_luc(_OFFSET[TRAM_QUA_HAN]),
    )

    # 4) CR LOI -> buoc 1. executed_at NULL nen khong co moc de tinh ngay du kien.
    await _tao_tram(db_session, TRAM_CR_LOI)
    ids["cr_loi"] = await _tao_session(
        db_session, TRAM_CR_LOI, CrStatus.FAILED, executed_at=None
    )

    yield ids

    await _don_sach(db_session)
