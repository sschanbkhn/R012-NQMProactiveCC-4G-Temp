"""
Integration test cho QosSnapshotRepo/QoeSnapshotRepo — can DB that
(schema system_nsn_nqmproactivecc). Tu: yeu cau truc tiep user 20082026
(snapshot PER-CELL thay cho ban gop chung "__ALL_CELLS__").

Muc tieu: 3 thu CHI kiem duoc tren DB that, khong kiem duoc bang unit test:
  1. Nhieu cell trong CUNG 1 session KHONG dam nhau (UNIQUE co cell_name).
  2. Upsert ghi de dung cot DIEM, GIU NGUYEN created_at - day chinh la ly do
     lazy cache phai DEM SO NGAY chu khong duoc tin created_at.
  3. dem_ngay_theo_cell() tra dung {(cell, period): so_ngay} tren SQL that.
"""

from datetime import date

from sqlalchemy import select

from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.qoe_snapshot_repo import QoeSnapshotRepo
from adapters.postgres.qos_snapshot_repo import QosSnapshotRepo
from domain.entities.cr_session import CrSession, CrStatus
from models.qos_snapshot import QosSnapshot as QosSnapshotModel

CELL_A = "4G-TEST-SNAP-A"
CELL_B = "4G-TEST-SNAP-B"


async def _new_session_id(db_session, tram_id: str) -> int:
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=tram_id, action="shutdown", status=CrStatus.DONE, plan_name=None)
    )
    return created.id


def _diem_qos(cell: str, ngay_dau: date, so_ngay: int, period: str, diem: float = 4.0):
    from datetime import timedelta

    return [
        {
            "cell_name": cell,
            "snapshot_date": ngay_dau + timedelta(days=i),
            "qos_score": diem,
            "period": period,
        }
        for i in range(so_ngay)
    ]


async def test_15_ngay_x_2_cell_luu_du_30_dong_khong_dam_nhau(db_session, test_tram):
    # 15 ngay = T-7..T-1 (before) + T (cr_day) + T+1..T+7 (after).
    session_id = await _new_session_id(db_session, test_tram)
    repo = QosSnapshotRepo(db_session)

    points = []
    for cell in (CELL_A, CELL_B):
        points += _diem_qos(cell, date(2026, 7, 13), 7, "before")
        points += _diem_qos(cell, date(2026, 7, 20), 1, "cr_day")
        points += _diem_qos(cell, date(2026, 7, 21), 7, "after")
    await repo.upsert_many(session_id, points)

    rows = await repo.get_by_session_id(session_id)
    assert len(rows) == 30, "2 cell x 15 ngay - cell nay KHONG duoc ghi de cell kia"
    assert {r["cell_name"] for r in rows} == {CELL_A, CELL_B}
    assert len([r for r in rows if r["cell_name"] == CELL_A]) == 15


async def test_cr_day_dung_1_dong_moi_cell(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = QosSnapshotRepo(db_session)

    await repo.upsert_many(
        session_id,
        _diem_qos(CELL_A, date(2026, 7, 20), 1, "cr_day") + _diem_qos(CELL_B, date(2026, 7, 20), 1, "cr_day"),
    )

    rows = [r for r in await repo.get_by_session_id(session_id) if r["period"] == "cr_day"]
    assert len(rows) == 2
    assert {r["cell_name"] for r in rows} == {CELL_A, CELL_B}


async def test_upsert_lai_ghi_de_DIEM_nhung_GIU_created_at(db_session, test_tram):
    # Day la bang chung cho quyet dinh lazy cache DEM SO NGAY thay vi tin
    # created_at: chup lai lan 2 KHONG lam created_at moi lai.
    session_id = await _new_session_id(db_session, test_tram)
    repo = QosSnapshotRepo(db_session)

    async def _created_at_theo_ngay():
        # Doc THANG tu model: get_by_session_id() KHONG tra created_at (khong
        # caller nao can), nhung day dung la thu test nay phai kiem.
        stmt = select(QosSnapshotModel).where(QosSnapshotModel.cr_session_id == session_id)
        rows = (await db_session.execute(stmt)).scalars().all()
        return {r.snapshot_date: r.created_at for r in rows}

    await repo.upsert_many(session_id, _diem_qos(CELL_A, date(2026, 7, 21), 3, "after", diem=2.0))
    truoc = await _created_at_theo_ngay()

    await repo.upsert_many(session_id, _diem_qos(CELL_A, date(2026, 7, 21), 3, "after", diem=4.5))
    db_session.expire_all()  # buoc doc lai tu DB, khong lay ban cache trong identity map
    sau_created = await _created_at_theo_ngay()
    sau = {r["snapshot_date"]: r for r in await repo.get_by_session_id(session_id)}

    assert len(sau) == 3, "upsert lai KHONG duoc tao dong moi"
    for ngay, row in sau.items():
        assert float(row["qos_score"]) == 4.5, "diem PHAI duoc cap nhat"
        assert sau_created[ngay] == truoc[ngay], "created_at PHAI giu nguyen"


async def test_dem_ngay_theo_cell_tra_dung_so_ngay(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = QosSnapshotRepo(db_session)

    await repo.upsert_many(
        session_id,
        _diem_qos(CELL_A, date(2026, 7, 13), 7, "before")
        + _diem_qos(CELL_A, date(2026, 7, 21), 7, "after")
        + _diem_qos(CELL_B, date(2026, 7, 13), 7, "before")
        + _diem_qos(CELL_B, date(2026, 7, 21), 4, "after"),  # CELL_B thieu 3 ngay
    )

    dem = await repo.dem_ngay_theo_cell(session_id)
    assert dem[(CELL_A, "before")] == 7
    assert dem[(CELL_A, "after")] == 7
    assert dem[(CELL_B, "before")] == 7
    assert dem[(CELL_B, "after")] == 4, "cell thieu ngay phai lo ra o day (lazy cache goi API lai)"


async def test_qoe_repo_hanh_vi_doi_xung(db_session, test_tram):
    # QoE dung y het QoS, chi khac ten cot diem - kiem 1 luot de khong bi lech
    # khi sau nay sua 1 ben quen ben kia.
    session_id = await _new_session_id(db_session, test_tram)
    repo = QoeSnapshotRepo(db_session)

    points = [
        {"cell_name": CELL_A, "snapshot_date": date(2026, 7, 21), "qoe_score": 3.5, "period": "after"},
        {"cell_name": CELL_B, "snapshot_date": date(2026, 7, 21), "qoe_score": 4.5, "period": "after"},
    ]
    await repo.upsert_many(session_id, points)

    rows = {r["cell_name"]: r for r in await repo.get_by_session_id(session_id)}
    assert float(rows[CELL_A]["qoe_score"]) == 3.5
    assert float(rows[CELL_B]["qoe_score"]) == 4.5
    assert await repo.dem_ngay_theo_cell(session_id) == {(CELL_A, "after"): 1, (CELL_B, "after"): 1}
