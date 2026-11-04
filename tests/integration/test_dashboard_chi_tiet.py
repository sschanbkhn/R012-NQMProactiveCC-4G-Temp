"""
Integration test /dashboard/chi-tiet: tim kiem + sap xep + phan trang O BE
(18/10/2026, yeu cau truc tiep user) - DU LIEU THAT 3 thang gan nhat.

Doc DB that (khong ghi): so sanh ket qua tim/sap xep voi chinh du lieu tra ve,
nen khong phu thuoc so luong cu the (tru ca TXN250M dung session 10707).
"""

from datetime import date, timedelta
from io import BytesIO

import httpx
import pytest
from openpyxl import load_workbook

import main
from adapters.postgres.dashboard_repo import DashboardRepo
from application.dashboard_use_case import DashboardUseCase
from domain.ports.outbound.repo_ports import COT_SAP_XEP_DASHBOARD

_DEN = date.today()
_TU = _DEN - timedelta(days=92)


async def _ct(db_session, loai, **kw):
    return await DashboardUseCase(DashboardRepo(db_session)).chi_tiet(loai, _TU, _DEN, **kw)


async def test_q_bo_dau_ha_noi_khop_dung_tinh_HNI(db_session):
    khong_dau = await _ct(db_session, "cr", q="ha noi", kich_thuoc=200)
    co_dau = await _ct(db_session, "cr", q="Hà Nội", kich_thuoc=200)
    loc_hni = await _ct(db_session, "cr", ma_tinh=["HNI"], kich_thuoc=200)

    if not loc_hni["tong"]:
        pytest.skip("Khong co session HNI trong 3 thang")
    # Khop qua TEN TINH (Python) - tram_name "4G-...-HNI" khong chua chu "ha noi".
    assert khong_dau["tong"] == co_dau["tong"] == loc_hni["tong"]
    assert {d["session_id"] for d in khong_dau["dong"]} == {d["session_id"] for d in loc_hni["dong"]}


async def test_q_txn250_khong_phan_biet_hoa_thuong_ra_dung_14_cell_session_10707(db_session):
    thuong = await _ct(db_session, "qos", q="txn250", kich_thuoc=200)
    hoa = await _ct(db_session, "qos", q="TXN250", kich_thuoc=200)

    if not thuong["tong"]:
        pytest.skip("Khong co session 10707 trong 3 thang")
    assert thuong["tong"] == hoa["tong"] == 14
    assert {d["session_id"] for d in thuong["dong"]} == {10707}


async def test_q_ma_phieu_va_session_id(db_session):
    phieu = await _ct(db_session, "phieu", q="32084")
    if not phieu["tong"]:
        pytest.skip("Khong co phieu 32084")
    assert phieu["dong"][0]["ma_phieu"] == "32084"
    qos = await _ct(db_session, "qos", q="32084")
    assert qos["tong"] == 1 and qos["dong"][0]["cell_name"] == "4G-TXN092M12-HNI"


def _da_sap_xep(gia_tri: list, chieu: str) -> bool:
    # NULLS LAST ca 2 chieu (xem _boc_chi_tiet()).
    co = [v for v in gia_tri if v is not None]
    if gia_tri[: len(co)] != co:
        return False
    return co == sorted(co, reverse=(chieu == "desc"))


@pytest.mark.parametrize("loai", ["cr", "qos", "phieu", "can_xu_ly"])
async def test_sap_xep_tung_cot_cho_phep_ca_2_chieu(db_session, loai):
    for cot in COT_SAP_XEP_DASHBOARD[loai]:
        for chieu in ("asc", "desc"):
            kq = await _ct(db_session, loai, sap_xep=cot, chieu=chieu, kich_thuoc=200)
            gia_tri = [d[cot] for d in kq["dong"]]
            assert _da_sap_xep(gia_tri, chieu), f"{loai}.{cot} {chieu}: {gia_tri[:10]}"


async def test_trang_2_khong_trung_trang_1_va_tong_khop(db_session):
    # Sap theo cot NHIEU gia tri trung (vendor_cell) - chi dung khi co khoa pha hoa.
    t1 = await _ct(db_session, "qos", sap_xep="vendor_cell", trang=1, kich_thuoc=20)
    t2 = await _ct(db_session, "qos", sap_xep="vendor_cell", trang=2, kich_thuoc=20)
    if t1["tong"] <= 20:
        pytest.skip("Chua du 2 trang")
    khoa = lambda d: (d["session_id"], d["cell_name"])  # noqa: E731
    assert t1["tong"] == t2["tong"]
    assert not {khoa(d) for d in t1["dong"]} & {khoa(d) for d in t2["dong"]}
    tong_quan = await DashboardUseCase(DashboardRepo(db_session)).execute(_TU, _DEN)
    assert t1["tong"] == tong_quan["hau_kiem"]["qos"]["so_cell"]


async def test_excel_xuat_dung_so_dong_khop_tim():
    tham_so = f"loai=qos&tu_ngay={_TU}&den_ngay={_DEN}&q=txn&sap_xep=lech&chieu=asc"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        trang = (await c.get(f"/api/v1/dashboard/chi-tiet?{tham_so}&kich_thuoc=5")).json()
        excel = await c.get(f"/api/v1/dashboard/chi-tiet/excel?{tham_so}")

    ws = load_workbook(BytesIO(excel.content))["QOS"]
    so_dong = ws.max_row - 1  # tru dong tieu de
    assert so_dong == trang["tong"]
    # Cung thu tu sap xep voi trang chi tiet.
    tieu_de = [c.value for c in ws[1]]
    assert [ws.cell(row=r, column=tieu_de.index("Cell") + 1).value for r in range(2, 2 + len(trang["dong"]))] == [
        d["cell_name"] for d in trang["dong"]
    ]


# === SAP XEP cr THEO ten_tinh / khu_vuc O SQL (19/10/2026) ===


async def test_cr_ten_tinh_khu_vuc_tu_SQL_khop_hang_so_python(db_session):
    from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh
    from domain.value_objects.ten_tinh import ten_tinh_tu_ma

    kq = await _ct(db_session, "cr", kich_thuoc=200)
    for d in kq["dong"]:
        assert d["ten_tinh"] == ten_tinh_tu_ma(d["ma_tinh"])
        assert d["khu_vuc"] == khu_vuc_tu_ma_tinh(d["ma_tinh"])


@pytest.mark.parametrize("cot", ["ten_tinh", "khu_vuc"])
@pytest.mark.parametrize("chieu", ["asc", "desc"])
async def test_cr_sap_ten_tinh_khu_vuc_va_trang_2_khong_trung(db_session, cot, chieu):
    tat_ca = await _ct(db_session, "cr", sap_xep=cot, chieu=chieu, kich_thuoc=200)
    assert _da_sap_xep([d[cot] for d in tat_ca["dong"]], chieu)

    # Trang nho (5 dong) - nhieu session cung tinh/KV, chi khong trung khi co
    # khoa pha hoa; va ghep cac trang phai ra dung thu tu cua ban day du.
    t1 = await _ct(db_session, "cr", sap_xep=cot, chieu=chieu, trang=1, kich_thuoc=5)
    t2 = await _ct(db_session, "cr", sap_xep=cot, chieu=chieu, trang=2, kich_thuoc=5)
    if t1["tong"] <= 5:
        pytest.skip("Chua du 2 trang")
    id1 = [d["session_id"] for d in t1["dong"]]
    id2 = [d["session_id"] for d in t2["dong"]]
    assert not set(id1) & set(id2)
    assert id1 + id2 == [d["session_id"] for d in tat_ca["dong"]][:10]
