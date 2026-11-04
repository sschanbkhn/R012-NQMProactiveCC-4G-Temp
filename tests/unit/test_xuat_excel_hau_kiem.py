"""
Unit test XuatExcelHauKiemUseCase + ve_excel (18/10/2026). MOCK repo/use case.
"""

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from openpyxl import load_workbook

from adapters.excel.hau_kiem_xlsx import ve_excel
from application.xuat_excel_hau_kiem_use_case import XuatExcelHauKiemUseCase
from domain.services.evaluation_service import EvaluationService

_CELLS = [f"4G-TXN{i:03d}M11-HNI" for i in range(16)]


def _item(cell, truoc, sau, attr):
    e = EvaluationService().evaluate(truoc, sau, threshold=0.5)
    return SimpleNamespace(cell_name=cell, so_ngay_before=len(truoc), so_ngay_after=len(sau), delta=e.lech,
                           **{attr: e})


def _uc(thieu: str | None = None):
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = SimpleNamespace(
        id=1, tram_id="114664", tram_name="4G-TXN250M-HNI",
        executed_at=datetime(2026, 10, 5, 2, 1, tzinfo=timezone.utc),
    )
    aff = AsyncMock()
    aff.get_by_cr_session_id.return_value = [{"cell_name": c, "tram_id": str(i // 4)} for i, c in enumerate(_CELLS)]
    cp = AsyncMock()
    cp.get_by_cr_session_id.return_value = [SimpleNamespace(cell_name=_CELLS[2])]
    phieu = AsyncMock()
    phieu.get_by_cr_session_id.return_value = [
        {"cell_name": _CELLS[0], "trang_thai": "SUCCESS", "phieu_id": "1", "deleted_at": None,
         "request_payload": {"PhuongAnXuLyDuKien": "2"}},
        {"cell_name": _CELLS[1], "trang_thai": "SUCCESS", "phieu_id": "2", "deleted_at": None,
         "request_payload": {"PhuongAnXuLyDuKien": "1"}},
        {"cell_name": _CELLS[3], "trang_thai": "FAILED", "phieu_id": None, "deleted_at": None,
         "request_payload": {"PhuongAnXuLyDuKien": "1"}},
    ]
    enodeb = AsyncMock()
    enodeb.get_by_tram_ids.return_value = [SimpleNamespace(tram_id=str(i), tram_name=f"SITE{i}") for i in range(4)]
    qos, qoe = AsyncMock(), AsyncMock()
    qos.execute.return_value = [
        _item(c, [], [], "qos_eval") if c == thieu else _item(c, [4.0] * 7, [4.0] * 7, "qos_eval") for c in _CELLS
    ]
    qoe.execute.return_value = [_item(c, [4.0] * 7, [4.0, 4, 4, 4, 4, 4, 2], "qoe_eval") for c in _CELLS]
    return XuatExcelHauKiemUseCase(session_repo, AsyncMock(), aff, cp, phieu, enodeb, qos, qoe)


async def test_16_cell_anh_huong_ra_16_dong_cung_ten_cung_thu_tu():
    khoi = await _uc().execute(session_id=1)

    assert [d["cell_anh_huong"] for d in khoi[0]["dong"]] == _CELLS
    assert all(d["cell_hau_kiem"] == d["cell_anh_huong"] for d in khoi[0]["dong"])
    assert khoi[0]["ngay_cr"] == "05/10/2026"


async def test_cell_khong_co_du_lieu_van_co_dong_va_ghi_chu_trong_o_so():
    khoi = await _uc(thieu=_CELLS[5]).execute(session_id=1)
    d = khoi[0]["dong"][5]

    assert d["qos"]["danh_gia"] == "Thieu du lieu"
    assert d["qos"]["tb_sau"] is None and d["qos"]["so_ngay_co_dl"] is None  # trong, khong ghi 0
    assert d["ghi_chu"] == "Thieu du lieu"


async def test_cot_E_cell_params_phieu_O_P_va_thong_ke_so_ngay():
    dong = (await _uc().execute(session_id=1))[0]["dong"]

    assert [d["cell_cr"] for d in dong].count(None) == 15 and dong[2]["cell_cr"] == _CELLS[2]
    assert dong[0]["phieu"] == {"ma": "1", "phuong_an": "Hien truong", "trang_thai": "SUCCESS"}
    assert dong[1]["phieu"] == {"ma": "2", "phuong_an": "He thong", "trang_thai": "SUCCESS"}
    # 19/10/2026: FAILED VAN hien (khong ma phieu) - biet cell da thu xuat.
    assert dong[3]["phieu"] == {"ma": None, "phuong_an": "He thong", "trang_thai": "FAILED"}
    assert dong[4]["phieu"] is None
    assert (dong[0]["qoe"]["so_ngay_co_dl"], dong[0]["qoe"]["so_ngay_dat"]) == ("7/7", "6/7")
    # Ve truoc: TB tu snapshot (avg_before), lech = round(tho truoc - tho sau, 2).
    assert (dong[0]["qoe"]["tb_truoc"], dong[0]["qoe"]["so_ngay_co_dl_truoc"]) == (4.0, "7/7")
    assert (dong[0]["qoe"]["tb_sau"], dong[0]["qoe"]["lech"]) == (3.71, 0.29)
    # Site DISTINCT theo thu tu, xep tu dong dau.
    assert [d.get("site") for d in dong[:5]] == ["SITE0", "SITE1", "SITE2", "SITE3", None]


async def test_ve_excel_gop_A_B_theo_khoi_va_cach_1_dong():
    khoi = await _uc().execute(session_id=1)
    wb = load_workbook(BytesIO(ve_excel(khoi + khoi, ["luat 1"])))
    ws = wb["Hau kiem"]

    gop = {str(m) for m in ws.merged_cells.ranges}
    assert {"A4:A19", "B4:B19", "A21:A36", "B21:B36"} <= gop  # dong 20 trong
    assert (ws["U4"].value, ws["V4"].value, ws["W4"].value) == ("1", "Hien truong", "SUCCESS")
    assert (ws["U5"].value, ws["V5"].value) == ("2", "He thong")
    assert ws["X3"].value is None and ws["X1"].value == "Ghi chu"
    # TB truoc, TB sau, Lech cua ca 2 nhom deu 2 so le.
    assert all(ws[f"{c}4"].number_format == "0.00" for c in "GHINOP")
    assert (ws["G3"].value, ws["K3"].value, ws["M3"].value) == (
        "TB truoc CR", "So ngay co du lieu truoc CR", "So ngay >= 3")


def _mau(c) -> str:
    return c.fill.start_color.rgb[-6:]


async def test_ve_excel_to_mau_sang_freeze_va_sheet_chu_giai():
    khoi = await _uc(thieu=_CELLS[5]).execute(session_id=1)
    khoi[0]["dong"][1]["qos"]["danh_gia"] = "Khong dat"
    wb = load_workbook(BytesIO(ve_excel(khoi + khoi, ["Lech > 0.5 -> Khong dat"])))
    ws = wb["Hau kiem"]

    assert _mau(ws["A1"]) == "DDEBF7" and ws["A1"].font.bold
    assert (_mau(ws["G2"]), _mau(ws["N2"]), _mau(ws["U2"])) == ("E2EFDA", "EDE7F6", "FFF2CC")
    assert _mau(ws["J4"]) == "E8F5E9"  # Dat
    assert _mau(ws["J5"]) == "FDECEA" and ws["J5"].font.bold and ws["J5"].font.color.rgb[-6:] == "C00000"
    assert _mau(ws["J9"]) == "F2F2F2"  # Thieu du lieu (cell thu 6)
    assert _mau(ws["U4"]) == "FFF8E1"  # co ma phieu
    assert _mau(ws["W4"]) == "E8F5E9" and _mau(ws["W7"]) == "FDECEA"  # SUCCESS / FAILED theo nhom
    assert wb.sheetnames == ["Hau kiem", "Phieu", "Chu giai"]
    assert _mau(ws["D21"]) == "FAFAFA" and _mau(ws["D4"]) == "000000"  # khoi 2 xam, khoi 1 trang
    assert ws.freeze_panes == "C4"
    assert ws.column_dimensions["D"].width > 8
    assert "Chu giai" in wb.sheetnames
    chu_giai = [str(c.value) for row in wb["Chu giai"].iter_rows() for c in row]
    assert any("Lech > 0.5" in v for v in chu_giai)
    assert any("So ngay >= 3" in v and "KHONG dung de danh gia" in v for v in chu_giai)
