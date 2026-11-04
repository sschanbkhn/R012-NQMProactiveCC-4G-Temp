"""
Integration test cho xoa_cascade() / xoa() — DB THAT.
Tu: yeu cau truc tiep user 20082026.

VI SAO PHAI TEST TREN DB THAT: unit test mock repo khong the bat duoc loi
THU TU XOA. Moi FK tro toi cr_session deu la ON DELETE NO ACTION (da kiem
20/08) nen bo sot 1 bang = FK violation - va bang bi sot chi lo ra khi co dong
that trong no. Test nay tao du lieu that o CA 6 bang con roi xoa.
"""

from datetime import date, datetime, timezone

import pytest

from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_log_repo import CrLogRepo
from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.qoe_snapshot_repo import QoeSnapshotRepo
from adapters.postgres.qos_snapshot_repo import QosSnapshotRepo
from application.xoa_phieu_use_case import XoaPhieuUseCase
from application.xoa_session_use_case import XoaSessionUseCase
from domain.entities.cr_session import CrSession, CrStatus

CELL_A = "4G-TEST-XOA-A"
CELL_B = "4G-TEST-XOA-B"


async def _tao_session_day_du(db_session, tram_id: str, status: CrStatus) -> int:
    """Tao 1 session co dong o TAT CA bang con - de xoa phai don het."""
    session_repo = CrSessionRepo(db_session)
    s = await session_repo.create(
        CrSession(id=0, tram_id=tram_id, action="shutdown", status=status, plan_name="plan_xoa_test")
    )
    sid = s.id

    await CrAffectedCellsRepo(db_session).bulk_insert(
        sid, [{"cell_name": CELL_A, "tram_id": tram_id, "huong_id": "11"},
              {"cell_name": CELL_B, "tram_id": tram_id, "huong_id": "12"}]
    )

    log_repo = CrLogRepo(db_session)
    for buoc in (1, 2, 3):
        await log_repo.insert(sid, buoc, f"Buoc {buoc}", "success", "ok", buoc * 5)

    phieu_repo = CrPhieuRepo(db_session)
    for cell in (CELL_A, CELL_B):
        await phieu_repo.insert(
            {"cr_session_id": sid, "cell_name": cell, "trang_thai": "FAILED",
             "request_payload": {"TenCell": cell}, "response_body": None,
             "phieu_id": None, "error_message": "loi test"}
        )

    await QosSnapshotRepo(db_session).upsert_many(
        sid,
        [{"cell_name": c, "snapshot_date": date(2026, 7, 21), "qos_score": 4.0, "period": "after"}
         for c in (CELL_A, CELL_B)],
    )
    await QoeSnapshotRepo(db_session).upsert_many(
        sid,
        [{"cell_name": CELL_A, "snapshot_date": date(2026, 7, 21), "qoe_score": 3.5, "period": "after"}],
    )
    return sid


async def test_xoa_session_FAILED_don_het_moi_bang_dem_dung(db_session, test_tram):
    sid = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)
    repo = CrSessionRepo(db_session)

    so_dong = await XoaSessionUseCase(repo).execute(sid)

    # Dem PHAI khop chinh xac so dong da tao o tren - day la thu nguoi van hanh
    # doi chieu voi UI truoc khi bam xoa.
    assert so_dong["cr_affected_cells"] == 2
    assert so_dong["cr_log"] == 3
    assert so_dong["cr_phieu"] == 2
    assert so_dong["qos_snapshot"] == 2
    assert so_dong["qoe_snapshot"] == 1
    assert so_dong["cr_session"] == 1

    # Session that su bien mat, khong con dong con nao mo coi.
    assert await repo.get_by_id(sid) is None
    assert await CrPhieuRepo(db_session).get_by_cr_session_id(sid) == []
    assert await CrLogRepo(db_session).get_by_cr_session_id(sid) == []
    assert await CrAffectedCellsRepo(db_session).get_by_cr_session_id(sid) == []
    assert await QosSnapshotRepo(db_session).get_by_session_id(sid) == []
    assert await QoeSnapshotRepo(db_session).get_by_session_id(sid) == []


async def test_xoa_session_KHONG_dong_toi_bang_tram(db_session, test_tram):
    # 1 tram dung chung cho nhieu session - xoa session KHONG duoc xoa tram.
    from sqlalchemy import select

    from models.tram import Tram as TramModel

    sid = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)
    await XoaSessionUseCase(CrSessionRepo(db_session)).execute(sid)

    con_tram = (
        await db_session.execute(select(TramModel).where(TramModel.tram_id == test_tram))
    ).scalar_one_or_none()
    assert con_tram is not None, "xoa session KHONG duoc keo theo tram"


async def test_xoa_session_khac_khong_bi_anh_huong(db_session, test_tram):
    # Bat bug WHERE thieu dieu kien: xoa session A khong duoc cham dong cua B.
    sid_a = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)
    sid_b = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)

    await XoaSessionUseCase(CrSessionRepo(db_session)).execute(sid_a)

    assert await CrSessionRepo(db_session).get_by_id(sid_b) is not None
    assert len(await CrPhieuRepo(db_session).get_by_cr_session_id(sid_b)) == 2
    assert len(await CrLogRepo(db_session).get_by_cr_session_id(sid_b)) == 3
    assert len(await QosSnapshotRepo(db_session).get_by_session_id(sid_b)) == 2


async def test_xoa_phieu_mem_khong_con_hien_va_khong_tao_lai_duoc(db_session, test_tram):
    """SUA 04/10/2026 (quyet dinh 04/10/2026) - DAO NGUOC muc dich cu cua
    DELETE /phieu/{id}. Truoc day (hard delete) xoa xong cell "quay lai chua
    xu ly, xuat lai duoc". Gio xoa la QUYET DINH CUOI CUNG: dong van CON trong
    DB (get_by_session_cell() PHAI THAY, KHONG duoc tra None) va INSERT LAI
    PHAI bi chan boi UNIQUE(cr_session_id, cell_name) - dung LA co che thuc
    hien "khong bao gio tao lai" (XuatPhieuUseCase.execute() dua vao chinh dieu
    nay de phat hien va tu choi 409, xem domain/errors.py::PhieuDaXoaError).
    """
    sid = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)
    phieu_repo = CrPhieuRepo(db_session)

    truoc = await phieu_repo.get_by_session_cell(sid, CELL_A)
    assert truoc is not None
    assert truoc["deleted_at"] is None

    await XoaPhieuUseCase(phieu_repo).execute(truoc["id"])

    sau = await phieu_repo.get_by_session_cell(sid, CELL_A)
    assert sau is not None, "dong PHAI con trong DB - xoa mem, khong phai hard delete"
    assert sau["deleted_at"] is not None
    assert sau["id"] == truoc["id"]

    # KHONG tao lai duoc: UNIQUE(cr_session_id, cell_name) con nguyen hieu luc
    # vi dong cu VAN O DO (chi danh dau, khong xoa that).
    with pytest.raises(Exception):
        await phieu_repo.insert(
            {"cr_session_id": sid, "cell_name": CELL_A, "trang_thai": "SUCCESS",
             "request_payload": {"TenCell": CELL_A}, "response_body": {"data": 19999},
             "phieu_id": "19999", "error_message": None}
        )
    await db_session.rollback()  # transaction bi abort sau IntegrityError (giong test_unique_cr_session_cell_chan_trung)


async def test_xoa_phieu_SUCCESS_bi_chan_tren_du_lieu_that(db_session, test_tram):
    import pytest

    from domain.errors import XoaPhieuKhongHopLeError

    sid = await _tao_session_day_du(db_session, test_tram, CrStatus.FAILED)
    phieu_repo = CrPhieuRepo(db_session)
    row = await phieu_repo.insert(
        {"cr_session_id": sid, "cell_name": "4G-TEST-XOA-C", "trang_thai": "SUCCESS",
         "request_payload": {}, "response_body": {"data": 19207}, "phieu_id": "19207",
         "error_message": None}
    )

    with pytest.raises(XoaPhieuKhongHopLeError):
        await XoaPhieuUseCase(phieu_repo).execute(row["id"])

    # Dong VAN CON trong DB - chan that su, khong phai chan xong van xoa.
    assert await phieu_repo.get_by_id(row["id"]) is not None


async def test_xoa_session_DONE_bi_chan_tren_du_lieu_that(db_session, test_tram):
    import pytest

    from domain.errors import XoaSessionKhongHopLeError

    sid = await _tao_session_day_du(db_session, test_tram, CrStatus.DONE)
    repo = CrSessionRepo(db_session)

    with pytest.raises(XoaSessionKhongHopLeError):
        await XoaSessionUseCase(repo).execute(sid)

    assert await repo.get_by_id(sid) is not None
    assert len(await CrPhieuRepo(db_session).get_by_cr_session_id(sid)) == 2
