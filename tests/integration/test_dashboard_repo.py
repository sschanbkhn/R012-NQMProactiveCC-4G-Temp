"""
Integration test DashboardRepo (GET /dashboard/*, 18/10/2026 + DOT 2) - DB that.

Dieu phai giu:
  1. Ban SQL cua luat danh gia ra CUNG ket qua voi EvaluationService.evaluate()
     tren cung du lieu (ke ca bien lech = 0.5 sau lam tron).
  2. Vendor: chi so CR theo vendor TRAM TAT, hau kiem + phieu theo vendor CELL.
  3. Chi tiet theo card: tong (khong loc con) KHOP so tren tong quan, phan trang.
  4. So lieu tong khop dem truc tiep tren DB; bo-loc du 34 tinh.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update

from adapters.postgres.dashboard_repo import DashboardRepo
from application.dashboard_use_case import DashboardUseCase
from application.get_qoe_cells_use_case import _QOE_CELL_THRESHOLD_DELTA  # noqa: PLC2701
from application.xuat_phieu_use_case import _XUAT_PHIEU_QOS_THRESHOLD_DELTA  # noqa: PLC2701
from domain.ports.outbound.repo_ports import BoLocDashboard
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, MUC_TOI_THIEU, EvaluationService
from domain.value_objects.ten_tinh import TEN_TINH_THEO_MA
from models.cell_params import CellParams as CellParamsModel
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_session import CrSession as CrSessionModel
from models.qoe_snapshot import QoeSnapshot as QoeSnapshotModel
from models.qos_snapshot import QosSnapshot as QosSnapshotModel
from models.tram import Tram as TramModel

# ma_tinh GIA rieng cho tram test -> loc dung session test, khong lan du lieu that.
_TINH_TEST = "TST"
# Tram THAT vendor NOKIA (session 10707) - CHI doc, gan lam tram cua cell de
# kiem "vendor theo CELL" khac "vendor tram tat" (tram test = ZTE).
_TRAM_NOKIA_THAT = "114664"
_NGUONG = {
    "min_ngay": MIN_DAYS_REQUIRED,
    "muc_toi_thieu": MUC_TOI_THIEU,
    "lech_qos": _XUAT_PHIEU_QOS_THRESHOLD_DELTA,
    "lech_qoe": _QOE_CELL_THRESHOLD_DELTA,
}
_NGAY_CR = date.today() - timedelta(days=10)

# cell -> (diem truoc, diem sau). Diem nguyen 1-5 giong CTS/CEM that.
_DU_LIEU = {
    # 25/6 - 22/6 = 0.5000000000000004 trong float (= TXN092M12 session 10707)
    # -> SAU LAM TRON (18/10/2026) 0.50 -> DAT.
    "TEST_DASH_BIEN_FLOAT": ([5, 5, 4, 4, 4, 3], [4, 4, 4, 4, 3, 3]),
    "TEST_DASH_LECH_051": ([4] * 6, [3.49] * 6),  # 0.51 > 0.5 -> KHONG DAT
    "TEST_DASH_BIEN_DUNG": ([4, 4, 4, 4, 4, 4], [4, 3, 4, 3, 4, 3]),  # lech dung 0.5
    "TEST_DASH_SAN": ([3] * 7, [2] * 7),
    "TEST_DASH_THIEU": ([4] * 7, [4] * 4),
    "TEST_DASH_KHONG_SNAPSHOT": None,  # cell DUY NHAT cua tram ZTE (tram test)
}


def _loc(**kw) -> BoLocDashboard:
    return BoLocDashboard(_NGAY_CR - timedelta(days=1), date.today(), ma_tinh=[_TINH_TEST], **kw)


def _python_kq(before, after, nguong_lech) -> str:
    e = EvaluationService().evaluate([float(x) for x in before], [float(x) for x in after], threshold=nguong_lech)
    if e.result == "INSUFFICIENT_DATA":
        return "thieu"
    if e.result == "PASS":
        return "dat"
    return "kd_san" if e.avg_after < MUC_TOI_THIEU else "kd_lech"


async def _tao_session(db_session, tram_id: str) -> int:
    # Tram test: tinh gia + vendor ZTE viet KHONG chuan (thuong, du dau cach)
    # de kiem UPPER(TRIM) giong find_stations().
    await db_session.execute(
        update(TramModel).where(TramModel.tram_id == tram_id).values(ma_tinh=_TINH_TEST, ten_thiet_bi=" zte ")
    )
    executed = datetime.combine(_NGAY_CR, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=3)
    row = CrSessionModel(tram_id=tram_id, action="shutdown", status="DONE", executed_at=executed, created_at=executed)
    db_session.add(row)
    await db_session.flush()
    for cell, du_lieu in _DU_LIEU.items():
        tram_cell = tram_id if du_lieu is None else _TRAM_NOKIA_THAT
        db_session.add(CrAffectedCellsModel(cr_session_id=row.id, cell_name=cell, tram_id=tram_cell, created_at=executed))
        if du_lieu is None:
            continue
        for period, diem, goc in (("before", du_lieu[0], -7), ("after", du_lieu[1], 1)):
            for i, d in enumerate(diem):
                ngay = _NGAY_CR + timedelta(days=goc + i)
                db_session.add(QosSnapshotModel(cr_session_id=row.id, cell_name=cell, snapshot_date=ngay,
                                                qos_score=d, period=period))
                # QoE = 5 diem moi ngay, du so ngay nhu QoS -> DAT tru cell thieu ngay.
                db_session.add(QoeSnapshotModel(cr_session_id=row.id, cell_name=cell, snapshot_date=ngay,
                                                qoe_score=5, period=period))
    for cell, tt, pa, xoa in (
        ("TEST_DASH_SAN", "SUCCESS", "2", None),
        ("TEST_DASH_BIEN_FLOAT", "SUCCESS", "1", None),
        ("TEST_DASH_THIEU", "KHONG_XUAT_THIEU_DU_LIEU", None, None),
        ("TEST_DASH_BIEN_DUNG", "FAILED", "1", None),
        # Dong da xoa mem KHONG duoc dem (giong Lich su CR).
        ("TEST_DASH_KHONG_SNAPSHOT", "KHONG_XUAT_VUOT_GIOI_HAN", None, executed),
    ):
        db_session.add(CrPhieuModel(cr_session_id=row.id, cell_name=cell, trang_thai=tt,
                                    request_payload={"PhuongAnXuLyDuKien": pa} if pa else {},
                                    phieu_id="9" if tt == "SUCCESS" else None, deleted_at=xoa))
    for cell in ("TEST_DASH_SAN", "TEST_DASH_BIEN_FLOAT"):
        db_session.add(CellParamsModel(tram_id=tram_id, cell_name=cell, cr_session_id=row.id))
    await db_session.commit()
    return row.id


def _tong(rows) -> dict:
    return next(r for r in rows if r["nhom"] == "tong")


async def test_luat_SQL_khop_EvaluationService_ke_ca_lam_tron_bien_0_5(db_session, test_tram):
    await _tao_session(db_session, test_tram)
    tong = _tong(await DashboardRepo(db_session).tong_hop(_loc(), _NGUONG, "day"))

    mong_doi = {"dat": 0, "kd_san": 0, "kd_lech": 0, "thieu": 0}
    for du_lieu in _DU_LIEU.values():
        mong_doi[_python_kq(*(du_lieu or ([], [])), _XUAT_PHIEU_QOS_THRESHOLD_DELTA)] += 1
    assert mong_doi == {"dat": 2, "kd_san": 1, "kd_lech": 1, "thieu": 2}  # chot du lieu test
    assert (tong["qos_dat"], tong["qos_kd_san"], tong["qos_kd_lech"], tong["qos_thieu"]) == (
        mong_doi["dat"], mong_doi["kd_san"], mong_doi["kd_lech"], mong_doi["thieu"]
    )
    assert tong["qos_tong"] == 6  # cell khong snapshot van duoc dem
    assert (tong["qoe_dat"], tong["qoe_thieu"]) == (4, 2)


async def test_dem_session_phieu_cell_cr(db_session, test_tram):
    await _tao_session(db_session, test_tram)
    tong = _tong(await DashboardRepo(db_session).tong_hop(_loc(), _NGUONG, "day"))

    assert (tong["so_session"], tong["done"], tong["so_tram"], tong["so_cell_cr"]) == (1, 1, 1, 2)
    assert (tong["phieu_success"], tong["phieu_he_thong"], tong["phieu_hien_truong"]) == (2, 1, 1)
    assert (tong["phieu_cho_xuat_tay"], tong["phieu_loi"]) == (1, 1)


async def test_vendor_CR_theo_tram_tat_hau_kiem_phieu_theo_CELL(db_session, test_tram):
    await _tao_session(db_session, test_tram)
    repo = DashboardRepo(db_session)

    zte = _tong(await repo.tong_hop(_loc(vendor=["ZTE"]), _NGUONG, "day"))
    nokia = _tong(await repo.tong_hop(_loc(vendor=["NOKIA"]), _NGUONG, "day"))

    # Tram tat ZTE: session/cell CR tinh cho ZTE; chi 1 cell anh huong la ZTE.
    assert (zte["so_session"], zte["so_cell_cr"], zte["qos_tong"], zte["phieu_success"]) == (1, 2, 1, 0)
    # 5 cell + 2 phieu SUCCESS thuoc tram NOKIA cua cell - KHONG co session CR nao.
    assert (nokia["so_session"], nokia["qos_tong"], nokia["phieu_success"]) == (0, 5, 2)

    nhom = {r["gia_tri"]: r for r in await repo.tong_hop(_loc(), _NGUONG, "day") if r["nhom"] == "vendor"}
    assert (nhom["ZTE"]["so_session"], nhom["ZTE"]["qos_tong"]) == (1, 1)
    assert (nhom["NOKIA"]["so_session"], nhom["NOKIA"]["qos_tong"]) == (0, 5)


async def test_chi_tiet_tong_khop_tong_quan_va_loc_con(db_session, test_tram):
    await _tao_session(db_session, test_tram)
    repo = DashboardRepo(db_session)
    tong = _tong(await repo.tong_hop(_loc(), _NGUONG, "day"))
    hom_qua = date.today() - timedelta(days=8)

    async def ct(loai, loc_con=None, offset=0, limit=50):
        return await repo.chi_tiet(loai, _loc(), _NGUONG, loc_con or {}, hom_qua, offset, limit)

    assert (await ct("qos"))[1] == tong["qos_tong"]
    assert (await ct("cr"))[1] == tong["so_session"]
    assert (await ct("qos", {"ket_qua": ["KHONG_DAT"], "ly_do": ["tut"]}))[1] == tong["qos_kd_lech"]
    assert (await ct("qos", {"ket_qua": ["INSUFFICIENT_DATA"]}))[1] == tong["qos_thieu"]
    assert (await ct("phieu", {"trang_thai": ["SUCCESS"], "phuong_an": ["2"]}))[1] == tong["phieu_hien_truong"]
    dong, _ = await ct("qos", {"ket_qua": ["KHONG_DAT"], "ly_do": ["duoi_muc"]})
    assert dong[0]["cell_name"] == "TEST_DASH_SAN" and dong[0]["ma_phieu"] == "9"
    assert float(dong[0]["tb_sau"]) == 2.0 and float(dong[0]["lech"]) == 1.0

    # Phan trang: 2 trang 4 dong khong trung, tong khong doi; trang qua cuoi van co tong.
    t1, n1 = await ct("qos", offset=0, limit=4)
    t2, n2 = await ct("qos", offset=4, limit=4)
    t9, n9 = await ct("qos", offset=40, limit=4)
    assert n1 == n2 == n9 == 6 and len(t1) == 4 and len(t2) == 2 and t9 == []
    assert not {r["cell_name"] for r in t1} & {r["cell_name"] for r in t2}


async def test_xu_huong_theo_ngay_moc_dung_ngay_CR(db_session, test_tram):
    await _tao_session(db_session, test_tram)
    rows = await DashboardRepo(db_session).tong_hop(_loc(), _NGUONG, "day")

    moc = {r["gia_tri"]: r for r in rows if r["nhom"] == "moc"}
    assert list(moc) == [_NGAY_CR.isoformat()] and moc[_NGAY_CR.isoformat()]["so_session"] == 1


async def test_qua_han_giong_dieu_kien_lich_su_CR(db_session, test_tram):
    await _tao_session(db_session, test_tram)  # executed 10 ngay truoc, chua xuat phieu
    repo = DashboardRepo(db_session)

    qua = await repo.can_xu_ly(_loc(), date.today() - timedelta(days=8))
    chua = await repo.can_xu_ly(_loc(), _NGAY_CR)

    assert len(qua["qua_han"]) == 1
    assert chua["qua_han"] == []


async def test_bo_loc_du_34_tinh_co_ten_va_khu_vuc(db_session):
    kq = await DashboardUseCase(DashboardRepo(db_session)).bo_loc()

    ma = {m["ma"] for m in kq["ma_tinh"]}
    assert set(TEN_TINH_THEO_MA) <= ma
    chinh_thuc = [m for m in kq["ma_tinh"] if m["ma"] in TEN_TINH_THEO_MA]
    assert len(chinh_thuc) == 34 and all(m["ten"] and m["khu_vuc"] for m in chinh_thuc)
    assert kq["khu_vuc"] == ["KV1", "KV2", "KV3"]
    assert set(kq["vendor"]) >= {"NOKIA", "ERICSSON", "HUAWEI", "ZTE"}


async def test_so_lieu_tong_khop_dem_truc_tiep_tren_DB_3_thang(db_session):
    # Du lieu THAT - so voi COUNT viet rieng bang ORM tren cung khoang.
    den = date.today()
    tu = den - timedelta(days=92)
    repo = DashboardRepo(db_session)
    tong = _tong(await repo.tong_hop(BoLocDashboard(tu, den), _NGUONG, "day"))

    ids = select(CrSessionModel.id).where(
        func.date(func.timezone("Asia/Ho_Chi_Minh", CrSessionModel.created_at)).between(tu, den)
    )
    so_session = (await db_session.execute(select(func.count()).select_from(ids.subquery()))).scalar_one()
    so_done = (await db_session.execute(
        select(func.count()).where(CrSessionModel.id.in_(ids), CrSessionModel.status == "DONE")
    )).scalar_one()
    so_cp = (await db_session.execute(
        select(func.count()).select_from(CellParamsModel).where(CellParamsModel.cr_session_id.in_(ids))
    )).scalar_one()
    so_aff = (await db_session.execute(
        select(func.count()).select_from(CrAffectedCellsModel).where(CrAffectedCellsModel.cr_session_id.in_(ids))
    )).scalar_one()
    so_phieu = (await db_session.execute(
        select(func.count()).select_from(CrPhieuModel).where(
            CrPhieuModel.cr_session_id.in_(ids), CrPhieuModel.trang_thai == "SUCCESS",
            CrPhieuModel.deleted_at.is_(None),
        )
    )).scalar_one()

    assert tong["so_session"] == so_session
    assert tong["done"] == so_done
    assert tong["so_cell_cr"] == so_cp
    assert tong["qos_tong"] == so_aff and tong["qoe_tong"] == so_aff
    assert tong["phieu_success"] == so_phieu
    assert tong["qos_dat"] + tong["qos_kd_san"] + tong["qos_kd_lech"] + tong["qos_thieu"] == so_aff
