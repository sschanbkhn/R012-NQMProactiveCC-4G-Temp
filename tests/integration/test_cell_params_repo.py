"""
Integration test cho CellParamsRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: ARCHITECTURE.md Section 10; TASK_LIST.md B5.3
"""

from adapters.postgres.cell_params_repo import CellParamsRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrSession, CrStatus
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel

TEST_CELL_NAME = "TEST_B5_CELL_A"


async def test_upsert_sync_netact_ghi_current(db_session, test_tram):
    repo = CellParamsRepo(db_session)
    await repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(0.0),
                qrxlevmin_current=Qrxlevmin(-128),
            )
        ]
    )

    cells = await repo.get_by_tram_id(test_tram)
    assert len(cells) == 1
    cell = cells[0]
    assert cell.rsboost_current == RsboostLevel(0.0)
    assert cell.qrxlevmin_current == Qrxlevmin(-128)
    assert cell.rsboost_before_cr is None
    assert cell.cr_session_id is None


async def test_upsert_conflict_khong_ghi_de_field_khong_truyen(db_session, test_tram):
    repo = CellParamsRepo(db_session)
    await repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(0.0),
                qrxlevmin_current=Qrxlevmin(-128),
            )
        ]
    )

    # Lan sync thu 2: chi gui rsboost_current moi, qrxlevmin_current=None
    # (mo phong payload sync-netact khong day du) -> qrxlevmin_current cu PHAI giu nguyen
    await repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(3.0),
            )
        ]
    )

    cell = (await repo.get_by_tram_id(test_tram))[0]
    assert cell.rsboost_current == RsboostLevel(3.0)
    assert cell.qrxlevmin_current == Qrxlevmin(-128)


async def test_snapshot_before_cr_dong_bang_gia_tri_va_gan_cr_session_id(db_session, test_tram):
    cell_repo = CellParamsRepo(db_session)
    session_repo = CrSessionRepo(db_session)

    await cell_repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(3.0),
                qrxlevmin_current=Qrxlevmin(-132),
            )
        ]
    )
    cr_session = await session_repo.create(
        CrSession(id=0, tram_id=test_tram, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
    )

    await cell_repo.snapshot_before_cr(cr_session.id)

    cell = (await cell_repo.get_by_tram_id(test_tram))[0]
    assert cell.rsboost_before_cr == RsboostLevel(3.0)
    assert cell.qrxlevmin_before_cr == Qrxlevmin(-132)
    assert cell.cr_session_id == cr_session.id


async def test_upsert_sau_snapshot_khong_ghi_de_before_cr(db_session, test_tram):
    # DB_SCHEMA.md dong 128-129 — sync-netact tiep tuc chay sau khi CR da snapshot,
    # chi duoc doi *_current, KHONG duoc doi *_before_cr da dong bang.
    cell_repo = CellParamsRepo(db_session)
    session_repo = CrSessionRepo(db_session)

    await cell_repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(3.0),
                qrxlevmin_current=Qrxlevmin(-132),
            )
        ]
    )
    cr_session = await session_repo.create(
        CrSession(id=0, tram_id=test_tram, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
    )
    await cell_repo.snapshot_before_cr(cr_session.id)

    # sync-netact chay tiep hom sau: gia tri current thay doi tren NetAct that
    await cell_repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(6.0),
                qrxlevmin_current=Qrxlevmin(-144),
            )
        ]
    )

    cell = (await cell_repo.get_by_tram_id(test_tram))[0]
    assert cell.rsboost_current == RsboostLevel(6.0)
    assert cell.qrxlevmin_current == Qrxlevmin(-144)
    assert cell.rsboost_before_cr == RsboostLevel(3.0)
    assert cell.qrxlevmin_before_cr == Qrxlevmin(-132)
    assert cell.cr_session_id == cr_session.id


async def test_get_by_cell_names_tim_dung_theo_ten_khong_loc_theo_tram_id(db_session, test_tram):
    # Bo sung o C2.1 (12072026) — get_by_cell_names() PHAI tim dung du KHONG
    # truyen tram_id nao ca (khac get_by_tram_id()) — mo phong dung ly do bug
    # that: cell lan gieng thuoc tram_id vat ly khac voi tram cua CR session.
    repo = CellParamsRepo(db_session)
    await repo.upsert(
        [
            CellParam(
                tram_id=test_tram,
                cell_name=TEST_CELL_NAME,
                rsboost_current=RsboostLevel(3.0),
                qrxlevmin_current=Qrxlevmin(-132),
            )
        ]
    )

    cells = await repo.get_by_cell_names([TEST_CELL_NAME])

    assert len(cells) == 1
    assert cells[0].cell_name == TEST_CELL_NAME
    assert cells[0].rsboost_current == RsboostLevel(3.0)
    assert cells[0].qrxlevmin_current == Qrxlevmin(-132)


async def test_get_by_cell_names_khong_tim_thay_tra_ve_rong(db_session, test_tram):
    repo = CellParamsRepo(db_session)
    cells = await repo.get_by_cell_names(["CELL_KHONG_TON_TAI_990099"])
    assert cells == []


async def test_get_by_cell_names_danh_sach_rong_tra_ve_rong_khong_loi(db_session):
    repo = CellParamsRepo(db_session)
    cells = await repo.get_by_cell_names([])
    assert cells == []
