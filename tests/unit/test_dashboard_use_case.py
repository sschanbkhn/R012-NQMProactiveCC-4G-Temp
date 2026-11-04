"""
Unit test DashboardUseCase + router /dashboard/* + ten file Excel (18/10/2026,
DOT 2). MOCK repo. Trong tam: gop ma_tinh -> KV, %, loc KV x ma_tinh, moc qua
han, xu huong du diem, chi tiet them ten tinh/KV, ten file 2 dang.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import httpx

import main
from api.routers.tai_file import lam_sach
from application.dashboard_use_case import TRANG_THAI_DEM, DashboardUseCase
from infrastructure.dependencies import get_dashboard_use_case, get_xuat_excel_hau_kiem_use_case

_COT = (
    "so_session", "done", "partial_success", "khong_chay", "failed", "dang_chay",
    "so_tram", "so_cell_cr",
    "qos_tong", "qos_dat", "qos_kd_san", "qos_kd_lech", "qos_thieu",
    "qoe_tong", "qoe_dat", "qoe_kd_san", "qoe_kd_lech", "qoe_thieu",
    "phieu_he_thong", "phieu_hien_truong", "phieu_success", "phieu_cho_xuat_tay", "phieu_loi",
)
_TU, _DEN = date(2026, 10, 1), date(2026, 10, 18)


def _dong(nhom: str, gia_tri, **kw) -> dict:
    return {"nhom": nhom, "gia_tri": gia_tri, **{c: 0 for c in _COT}, **kw}


def _uc(rows, can=None, chi_tiet=None):
    repo = AsyncMock()
    repo.tong_hop.return_value = rows
    repo.can_xu_ly.return_value = can or {"qua_han": [], "khong_chay": []}
    repo.chi_tiet.return_value = chi_tiet or ([], 0)
    return DashboardUseCase(repo), repo


async def test_theo_nhom_bo_UNKNOWN_KHONG_XAC_DINH_nhung_tong_chung_giu_nguyen():
    rows = [
        _dong("tong", None, so_session=4, qos_tong=12),
        _dong("ma_tinh", "HNI", so_session=2, qos_tong=8),
        _dong("ma_tinh", "XYZ", so_session=1, qos_tong=2),   # ma la -> KV khong xac dinh
        _dong("ma_tinh", None, so_session=1, qos_tong=2),    # tram khong co ma_tinh
        _dong("vendor", "NOKIA", so_session=4, qos_tong=11),
        _dong("vendor", "UNKNOWN", qos_tong=1),
    ]
    uc, _ = _uc(rows)

    r = await uc.execute(_TU, _DEN)

    assert [x["gia_tri"] for x in r["theo_nhom"]["khu_vuc"]] == ["KV1"]
    assert [x["gia_tri"] for x in r["theo_nhom"]["ma_tinh"]] == ["HNI"]
    assert [x["gia_tri"] for x in r["theo_nhom"]["vendor"]] == ["NOKIA"]
    # Tong chung VAN tinh cell/tram khong xac dinh.
    assert r["tong"]["so_session"] == 4 and r["hau_kiem"]["qos"]["so_cell"] == 12


async def test_gop_ma_tinh_thanh_khu_vuc():
    rows = [
        _dong("tong", None, so_session=4),
        _dong("ma_tinh", "HNI", so_session=2, so_tram=2, qos_tong=10, qos_dat=8),
        _dong("ma_tinh", "HPG", so_session=1, so_tram=1, qos_tong=10, qos_dat=2),
        _dong("ma_tinh", "XYZ", so_session=1, so_tram=1),
    ]
    uc, _ = _uc(rows)

    r = await uc.execute(_TU, _DEN)

    kv = {x["gia_tri"]: x for x in r["theo_nhom"]["khu_vuc"]}
    assert set(kv) == {"KV1"}  # XYZ (KV khong xac dinh) bi bo khoi theo_nhom (19/10/2026)
    assert kv["KV1"]["tong"]["so_session"] == 3
    assert kv["KV1"]["hau_kiem"]["qos"]["dat"] == {"so": 10, "ty_le": 50.0}
    hni = r["theo_nhom"]["ma_tinh"][0]
    assert (hni["gia_tri"], hni["ten_tinh"], hni["khu_vuc"]) == ("HNI", "Ha Noi", "KV1")


async def test_theo_nhom_vendor_thay_netact():
    uc, _ = _uc([_dong("tong", None), _dong("vendor", "NOKIA", so_session=3)])

    r = await uc.execute(_TU, _DEN)

    assert set(r["theo_nhom"]) == {"khu_vuc", "ma_tinh", "vendor"}
    assert r["theo_nhom"]["vendor"][0]["tong"]["so_session"] == 3


async def test_nhom_rong_sum_NULL_khong_vo_va_trang_thai_khac_bu_du_tong():
    rong = {k: None for k in _COT}
    uc, _ = _uc([{"nhom": "tong", "gia_tri": None, **rong}])
    assert (await uc.execute(_TU, _DEN))["hau_kiem"]["qos"]["dat"] == {"so": 0, "ty_le": None}

    uc, _ = _uc([_dong("tong", None, so_session=5, done=2, failed=1)])
    r = await uc.execute(_TU, _DEN)
    assert r["tong"]["theo_trang_thai"]["khac"] == 2
    assert sum(r["tong"]["theo_trang_thai"].values()) == 5
    # Muc 6 DOT 2: danh sach trang thai FE can map nhan.
    assert tuple(r["tong"]["theo_trang_thai"]) == TRANG_THAI_DEM


async def test_khong_dat_tach_2_ly_do():
    uc, _ = _uc([_dong("tong", None, qoe_tong=10, qoe_kd_san=2, qoe_kd_lech=3, qoe_dat=5)])

    kd = (await uc.execute(_TU, _DEN))["hau_kiem"]["qoe"]["khong_dat"]

    assert (kd["so"], kd["ty_le"], kd["tb_sau_duoi_muc"], kd["lech_qua_nguong"]) == (5, 50.0, 2, 3)


async def test_loc_khu_vuc_va_ma_tinh_lay_GIAO_vendor_va_moc_qua_han():
    uc, repo = _uc([_dong("tong", None)])

    await uc.execute(
        _TU, _DEN, khu_vuc=["KV1"], ma_tinh=["HNI", "HCM"], vendor=["ZTE"],
        bay_gio=datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc),
    )

    loc = repo.tong_hop.call_args.args[0]
    assert loc.ma_tinh == ["HNI"]  # HCM thuoc KV2 -> loai
    assert loc.vendor == ["ZTE"]
    # hom nay VN 18/10 - XUAT_PHIEU_AFTER_DAYS (8) = 10/10, giong ?qua_han=true
    assert repo.can_xu_ly.call_args.args[1] == date(2026, 10, 10)


async def test_xu_huong_theo_ngay_DU_diem_ke_ca_ngay_trong():
    uc, repo = _uc([_dong("tong", None), _dong("moc", "2026-10-05", so_session=2, qos_tong=4, qos_dat=3,
                                              qos_kd_lech=1, phieu_success=1)])

    xh = (await uc.execute(_TU, _DEN))["xu_huong"]

    assert repo.tong_hop.call_args.args[2] == "day"
    assert len(xh) == 18 and xh[0]["moc"] == "2026-10-01" and xh[-1]["moc"] == "2026-10-18"
    d5 = next(d for d in xh if d["moc"] == "2026-10-05")
    assert (d5["so_cr"], d5["so_phieu"], d5["ty_le_dat_qos"], d5["so_cell_khong_dat_qos"]) == (2, 1, 75.0, 1)
    assert xh[0] == {"moc": "2026-10-01", "so_cr": 0, "so_phieu": 0, "ty_le_dat_qos": None,
                     "ty_le_dat_qoe": None, "so_cell_khong_dat_qos": 0, "so_cell_khong_dat_qoe": 0}


async def test_xu_huong_theo_tuan_bat_dau_thu_hai():
    uc, repo = _uc([_dong("tong", None)])

    xh = (await uc.execute(_TU, _DEN, chi_tiet_thoi_gian="tuan"))["xu_huong"]

    assert repo.tong_hop.call_args.args[2] == "week"
    # 01/10/2026 la thu Tu -> moc dau la thu Hai 28/09.
    assert [d["moc"] for d in xh] == ["2026-09-28", "2026-10-05", "2026-10-12"]


async def test_khong_chay_dem_theo_ma_loi():
    can = {
        "qua_han": [],
        "khong_chay": [
            {"id": 1, "tram_id": "1", "tram_name": "A", "ma_loi": "KHONG_CO_DU_LIEU_HO", "created_at": None},
            {"id": 2, "tram_id": "2", "tram_name": "B", "ma_loi": "KHONG_CO_DU_LIEU_HO", "created_at": None},
            {"id": 3, "tram_id": "3", "tram_name": "C", "ma_loi": None, "created_at": None},
        ],
    }
    uc, _ = _uc([_dong("tong", None)], can)

    r = await uc.execute(_TU, _DEN)

    assert r["can_xu_ly"]["khong_chay"]["theo_ma_loi"] == {"KHONG_CO_DU_LIEU_HO": 2, "KHONG_RO": 1}


async def test_chi_tiet_phan_trang_ten_tinh_kv_lay_tu_repo():
    # Tu 19/10/2026 ten_tinh/khu_vuc do SQL tra (JOIN danh muc tinh) - use case
    # chi chuyen tiep, khong anh xa lai.
    uc, repo = _uc([], chi_tiet=([{"session_id": 1, "ma_tinh": "HCM", "ten_tinh": "TP Ho Chi Minh",
                                   "khu_vuc": "KV2", "ngay_cr": date(2026, 10, 5)}], 41))

    r = await uc.chi_tiet("cr", _TU, _DEN, trang=3, kich_thuoc=20, loc_con={"trang_thai": ["DONE"]})

    assert repo.chi_tiet.call_args.args[5:] == (40, 20)  # offset, limit
    assert r["tong"] == 41 and r["dong"][0]["ten_tinh"] == "TP Ho Chi Minh"
    assert r["dong"][0]["khu_vuc"] == "KV2" and r["dong"][0]["ngay_cr"] == "2026-10-05"


def test_lam_sach_ten_file():
    assert lam_sach("4G-TXN250M-HNI") == "4G-TXN250M-HNI"
    assert lam_sach("Tram Ha Noi/01 (moi)") == "Tram_Ha_Noi_01_moi"
    assert lam_sach("Trạm") == "Tr_m"


async def _get(url, overrides):
    main.app.dependency_overrides.update(overrides)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
            return await c.get(url)
    finally:
        main.app.dependency_overrides.clear()


async def test_router_422_va_vendor_whitelist():
    ov = {get_dashboard_use_case: lambda: _uc([_dong("tong", None)])[0]}
    assert (await _get("/api/v1/dashboard/tong-quan?tu_ngay=2026-10-18&den_ngay=2026-10-01", ov)).status_code == 422
    assert (await _get("/api/v1/dashboard/tong-quan?tu_ngay=2026-10-01&den_ngay=2026-10-18&vendor=SIEMENS", ov)).status_code == 422
    assert (await _get("/api/v1/dashboard/chi-tiet?loai=abc&tu_ngay=2026-10-01&den_ngay=2026-10-18", ov)).status_code == 422
    r = await _get("/api/v1/dashboard/tong-quan?tu_ngay=2026-10-01&den_ngay=2026-10-18&vendor=NOKIA&vendor=ZTE", ov)
    assert r.status_code == 200 and r.json()["tong"]["so_session"] == 0


async def test_ten_file_hau_kiem_nhieu_session_va_filename_utf8():
    uc = AsyncMock()
    uc.execute.return_value = []
    r = await _get("/api/v1/hau-kiem/excel?tu_ngay=2026-10-01&den_ngay=2026-10-18",
                   {get_xuat_excel_hau_kiem_use_case: lambda: uc})

    cd = r.headers["content-disposition"]
    assert r.status_code == 200
    assert 'filename="hau_kiem_20261001_den_20261018_' in cd and "filename*=UTF-8''hau_kiem_20261001_den_20261018_" in cd


async def test_ten_file_dashboard_chi_tiet():
    uc, _ = _uc([], chi_tiet=([], 0))
    r = await _get("/api/v1/dashboard/chi-tiet/excel?loai=qos&tu_ngay=2026-10-01&den_ngay=2026-10-18",
                   {get_dashboard_use_case: lambda: uc})

    assert 'filename="dashboard_qos_20261001_den_20261018_' in r.headers["content-disposition"]


# === TIM + SAP XEP (18/10/2026) ===


async def test_tim_bo_dau_va_khop_ten_tinh_truyen_xuong_repo():
    uc, repo = _uc([])

    await uc.chi_tiet("cr", _TU, _DEN, q="  Hà Nội ", sap_xep="tram_name", chieu="asc")

    kw = repo.chi_tiet.call_args.kwargs
    assert kw["tim"] == {"q": "ha noi", "ma_tinh": ["HNI"]}
    assert (kw["sap_xep"], kw["chieu"]) == ("tram_name", "asc")


async def test_q_rong_khong_tim():
    uc, repo = _uc([])
    await uc.chi_tiet("qos", _TU, _DEN, q="   ")
    assert repo.chi_tiet.call_args.kwargs["tim"] is None


async def test_router_sap_xep_cot_la_422_kich_thuoc_toi_da_200():
    ov = {get_dashboard_use_case: lambda: _uc([])[0]}
    base = "/api/v1/dashboard/chi-tiet?tu_ngay=2026-10-01&den_ngay=2026-10-18"
    r = await _get(f"{base}&loai=cr&sap_xep=cell_name", ov)
    assert r.status_code == 422 and "tram_name" in r.json()["detail"]
    assert (await _get(f"{base}&loai=qos&sap_xep=lech&chieu=up", ov)).status_code == 422
    assert (await _get(f"{base}&loai=qos&kich_thuoc=201", ov)).status_code == 422
    assert (await _get(f"{base}&loai=qos&sap_xep=lech&chieu=asc&kich_thuoc=200", ov)).status_code == 200
