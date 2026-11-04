"""
Integration test cho CrAffectedCellsRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: DB_SCHEMA.md Section 8.1; Phuong an B (22072026, DA DUYET thiet ke).
"""

from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from domain.entities.cr_session import CrSession, CrStatus


async def _new_session_id(db_session, tram_id: str) -> int:
    # cr_affected_cells.cr_session_id la FK NOT NULL -> can 1 cr_session that
    # truoc, dung lai CrSessionRepo (da co test rieng) thay vi insert tay.
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=tram_id, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
    )
    return created.id


async def test_bulk_insert_ghi_dung_so_dong_va_field(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrAffectedCellsRepo(db_session)

    cells = [
        {
            "cell_name": "TEST_B5_AFFECTED_A",
            "tram_id": "999001",
            "huong_id": "11",
            "dist_name": "PLMN-PLMN/MRBTS-999001/LNBTS-999001/LNCEL-11",
        },
        # tram_id/huong_id/dist_name None hop le - LNBTS chua join duoc bang
        # tram (site chua sync RIMS), van luu cell_name (xem migration).
        {"cell_name": "TEST_B5_AFFECTED_B", "tram_id": None, "huong_id": None, "dist_name": None},
    ]
    inserted = await repo.bulk_insert(session_id, cells)
    assert inserted == 2

    rows = await repo.get_by_cr_session_id(session_id)
    assert {r["cell_name"] for r in rows} == {"TEST_B5_AFFECTED_A", "TEST_B5_AFFECTED_B"}
    cell_a = next(r for r in rows if r["cell_name"] == "TEST_B5_AFFECTED_A")
    assert cell_a["tram_id"] == "999001"
    assert cell_a["huong_id"] == "11"
    cell_b = next(r for r in rows if r["cell_name"] == "TEST_B5_AFFECTED_B")
    assert cell_b["tram_id"] is None
    assert cell_b["huong_id"] is None


async def test_bulk_insert_list_rong_khong_loi_tra_0(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrAffectedCellsRepo(db_session)
    assert await repo.bulk_insert(session_id, []) == 0


async def test_bulk_insert_trung_cell_name_cung_session_on_conflict_do_nothing(db_session, test_tram):
    # UNIQUE(cr_session_id, cell_name) - goi bulk_insert() 2 LAN cung
    # cell_name trong CUNG 1 session PHAI khong crash (ON CONFLICT DO
    # NOTHING), khong tao dong trung.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrAffectedCellsRepo(db_session)
    cells = [{"cell_name": "TEST_B5_AFFECTED_DUP", "tram_id": "999001", "huong_id": "11", "dist_name": None}]

    await repo.bulk_insert(session_id, cells)
    await repo.bulk_insert(session_id, cells)  # lan 2, cung cell_name

    rows = await repo.get_by_cr_session_id(session_id)
    assert len(rows) == 1


async def test_get_by_cr_session_id_khong_ton_tai_tra_rong(db_session, test_tram):
    repo = CrAffectedCellsRepo(db_session)
    assert await repo.get_by_cr_session_id(999_999_999) == []


async def test_get_by_cr_session_id_giu_DUNG_thu_tu_luc_ghi(db_session, test_tram):
    # SUA 18/10/2026: bang hau kiem/xuat Excel phai giu thu tu cell anh huong
    # luc chay CR - ghi KHONG theo thu tu ABC de bat duoc ca truong hop DB tra
    # theo index (cr_session_id, cell_name) thay vi theo id.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrAffectedCellsRepo(db_session)
    ten = [f"TEST_B5_THU_TU_{c}" for c in "QWERTYUIOPASDFGH"]  # 16 cell
    await repo.bulk_insert(session_id, [{"cell_name": t} for t in ten])

    rows = await repo.get_by_cr_session_id(session_id)

    assert [r["cell_name"] for r in rows] == ten
