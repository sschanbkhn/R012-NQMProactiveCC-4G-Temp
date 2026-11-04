"""
Unit test adapters/excel/dashboard_xlsx.py (DOT 2, 18/10/2026) - Excel chi tiet
card + tong hop dashboard, CUNG bang mau voi file hau kiem.
"""

from io import BytesIO

from openpyxl import load_workbook

from adapters.excel.dashboard_xlsx import ve_chi_tiet, ve_tong_hop


def _mau(c) -> str:
    return c.fill.start_color.rgb[-6:]


def test_chi_tiet_qos_to_ket_qua_va_ma_phieu():
    dong = [
        {"session_id": 1, "cell_name": "C1", "tb_sau": 2.0, "ket_qua": "KHONG_DAT", "ma_phieu": "32084"},
        {"session_id": 1, "cell_name": "C2", "tb_sau": 4.5, "ket_qua": "DAT", "ma_phieu": None},
    ]
    wb = load_workbook(BytesIO(ve_chi_tiet("qos", dong, ["luat"])))
    ws = wb["QOS"]

    tieu_de = [c.value for c in ws[1]]
    kq, mp = tieu_de.index("Ket qua") + 1, tieu_de.index("Ma phieu") + 1
    assert _mau(ws.cell(row=2, column=kq)) == "FDECEA" and _mau(ws.cell(row=3, column=kq)) == "E8F5E9"
    assert _mau(ws.cell(row=2, column=mp)) == "FFF8E1"
    assert _mau(ws["A1"]) == "DDEBF7" and ws.freeze_panes == "A2"
    assert wb.sheetnames == ["QOS", "Chu giai"]


def test_tong_hop_du_4_sheet():
    cs = {"tong": {"so_session": 1, "so_tram": 1, "so_cell_cr": 2, "theo_trang_thai": {"DONE": 1}},
          "hau_kiem": {p: {"so_cell": 2, "dat": {"so": 1, "ty_le": 50.0}, "khong_dat": {"so": 1, "ty_le": 50.0,
                       "tb_sau_duoi_muc": 1, "lech_qua_nguong": 0}, "thieu_du_lieu": {"so": 0, "ty_le": 0.0}}
                       for p in ("qos", "qoe")},
          "phieu": {"success": 1, "he_thong": 0, "hien_truong": 1, "cho_xuat_tay": 0, "loi": 0}}
    tq = {"tu_ngay": "2026-10-01", "den_ngay": "2026-10-18", **cs,
          "theo_nhom": {"khu_vuc": [{"gia_tri": "KV1", **cs}], "ma_tinh": [{"gia_tri": "HNI", "ten_tinh": "Ha Noi", **cs}],
                        "vendor": [{"gia_tri": "NOKIA", **cs}]},
          "xu_huong": [{"moc": "2026-10-01", "so_cr": 0, "so_phieu": 0, "ty_le_dat_qos": None,
                        "ty_le_dat_qoe": None, "so_cell_khong_dat_qos": 0, "so_cell_khong_dat_qoe": 0}],
          "can_xu_ly": {"qua_han_xuat_phieu": {"sessions": [{"id": 433, "tram_id": "1", "tram_name": "A", "ngay_cr": "2026-07-22"}]},
                        "khong_chay": {"sessions": []}}}

    wb = load_workbook(BytesIO(ve_tong_hop(tq, ["luat"])))

    assert wb.sheetnames == ["Tong quan", "Theo nhom", "Xu huong", "Can xu ly", "Chu giai"]
    assert [r[0].value for r in wb["Theo nhom"].iter_rows(min_row=2)] == ["KV", "Tinh", "Vendor"]
    assert wb["Can xu ly"]["B2"].value == 433


async def test_sheet_theo_nhom_khong_co_UNKNOWN():
    # Sheet "Theo nhom" ve tu theo_nhom cua use case - UNKNOWN da bi bo o do.
    from unittest.mock import AsyncMock

    from application.dashboard_use_case import DashboardUseCase

    cot = ("so_session", "done", "partial_success", "khong_chay", "failed", "dang_chay", "so_tram",
           "so_cell_cr", "qos_tong", "qos_dat", "qos_kd_san", "qos_kd_lech", "qos_thieu", "qoe_tong",
           "qoe_dat", "qoe_kd_san", "qoe_kd_lech", "qoe_thieu", "phieu_he_thong", "phieu_hien_truong",
           "phieu_success", "phieu_cho_xuat_tay", "phieu_loi")
    rows = [{"nhom": n, "gia_tri": g, **{c: 1 for c in cot}}
            for n, g in (("tong", None), ("vendor", "NOKIA"), ("vendor", "UNKNOWN"), ("ma_tinh", None))]
    repo = AsyncMock()
    repo.tong_hop.return_value = rows
    repo.can_xu_ly.return_value = {"qua_han": [], "khong_chay": []}
    from datetime import date
    tq = await DashboardUseCase(repo).execute(date(2026, 10, 1), date(2026, 10, 2))

    ws = load_workbook(BytesIO(ve_tong_hop(tq, ["luat"])))["Theo nhom"]
    nhan = [(r[0].value, r[1].value) for r in ws.iter_rows(min_row=2)]
    assert nhan == [("Vendor", "NOKIA")]
