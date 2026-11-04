"""
Ve bang phieu xuat CLK (19/10/2026, yeu cau truc tiep user - duyet PHAN B).

DUNG CHUNG cho 2 file: GET /phieu/excel (ve_excel_phieu) va sheet "Phieu" cua
Excel hau kiem (ve_sheet_phieu) - cung ham dien dong + to mau nen so lieu 2
file khong the lech nhau. Input = dict tu ICrPhieuRepo.dong_excel().

CHI LO TRINH BAY. KHONG dua cac key HANG SO cua payload (TrangThai, Tsd,
Voice, NguyenNhan, MaPhuongAn, UserUpdatePa...) vao file - gia tri giong nhau
moi dong, chi lam rong bang (yeu cau user).
"""

from datetime import timedelta, timezone
from io import BytesIO

from openpyxl import Workbook

from adapters.excel.kieu import MAU, MAU_NHOM_PHIEU, o, rong_vua_noi_dung
from domain.value_objects.ten_tinh import ten_tinh_tu_ma
from domain.value_objects.trang_thai_phieu import (
    NHOM_TRANG_THAI,
    PHUONG_AN,
    Y_NGHIA_TRANG_THAI,
    nhom_trang_thai,
    ten_phuong_an,
)

_GMT7 = timezone(timedelta(hours=7))

TIEU_DE = [
    "Ma log", "Ma phieu CLK", "Cell", "Tram cua cell", "Tinh", "Vendor", "Session CR",
    "Tram tat (session)", "Tao luc", "Gui lan cuoi", "So lan thu", "Trang thai",
    "Nhom trang thai", "Phuong an", "Nguon khong dat", "QoS gui CTS (min 7 ngay sau)",
    "QoE gui CTS (min 7 ngay sau)", "So chi tieu VP", "Noi dung", "Ma loi", "Thong bao loi",
]


def _gio(dt) -> str | None:
    # openpyxl khong ghi duoc datetime co mui gio -> doi GMT+7 (gio nguoi van
    # hanh doc tren UI) roi ghi chuoi, tranh Excel hieu nham la UTC.
    return dt.astimezone(_GMT7).strftime("%d/%m/%Y %H:%M") if dt else None


def _ten_tram(ten: str | None, ma: str | None) -> str | None:
    # Tram chua sync RIMS (khong co ten) -> ghi ma, khong de trong.
    return ten or ma


def _ma_loi(r: dict) -> str | None:
    # Khong co cot ma loi rieng: HTTP status + response_body.code la 2 thu
    # khac nhau (4xx vs 200 + isError) - ghi ca 2 de khong mat tin hieu.
    phan = [f"HTTP {r['http_status']}" if r.get("http_status") else None, r.get("ma_loi_cts")]
    return " / ".join(str(p) for p in phan if p) or None


def gia_tri_dong(r: dict) -> list:
    return [
        r["id"], r.get("phieu_id"), r["cell_name"],
        _ten_tram(r.get("tram_cell_name"), r.get("tram_cell_id")),
        ten_tinh_tu_ma(r.get("ma_tinh")) or r.get("ma_tinh"),
        r.get("vendor"), r["cr_session_id"],
        _ten_tram(r.get("tram_tat_name"), r.get("tram_tat_id")),
        _gio(r.get("created_at")), _gio(r.get("gui_lan_cuoi")), r.get("so_lan_thu"),
        r["trang_thai"], nhom_trang_thai(r["trang_thai"]), ten_phuong_an(r.get("phuong_an")),
        r.get("nguon_khong_dat"), r.get("qos_gui"), r.get("qoe_gui"), r.get("so_chi_tieu_vp"),
        r.get("noi_dung"), _ma_loi(r), r.get("error_message"),
    ]


def ve_sheet_phieu(wb, rows: list[dict], ten_sheet: str = "Phieu") -> None:
    ws = wb.create_sheet(ten_sheet)
    for i, t in enumerate(TIEU_DE, start=1):
        o(ws, 1, i, t, mau="tieu_de", dam=True)
    for r_i, r in enumerate(rows, start=2):
        # To CA DONG theo nhom - loc nhanh bang mat dong nao can xu ly. PENDING
        # (khong nhom) de trang: bat thuong, khong gop vao nhom nao.
        mau = MAU_NHOM_PHIEU.get(nhom_trang_thai(r["trang_thai"]))
        for c_i, v in enumerate(gia_tri_dong(r), start=1):
            o(ws, r_i, c_i, v, mau=mau)
    ws.freeze_panes = "D2"
    rong_vua_noi_dung(ws)


def chu_giai_phieu(ws, dong_bat_dau: int) -> int:
    """Ghi y nghia nhom/trang thai + luu y QoS/QoE vao ws tu dong_bat_dau, tra
    dong ke tiep. Dung cho ca file phieu lan sheet Chu giai cua file hau kiem."""
    r = dong_bat_dau
    o(ws, r, 1, "Nhom / trang thai phieu", mau="tieu_de", dam=True)
    o(ws, r, 2, "Y nghia", mau="tieu_de", dam=True)
    for nhom, ds in NHOM_TRANG_THAI.items():
        for tt in ds:
            r += 1
            khoa = MAU_NHOM_PHIEU[nhom]
            o(ws, r, 1, f"{nhom}: {tt}", mau=khoa)
            o(ws, r, 2, f"{Y_NGHIA_TRANG_THAI[tt]} (mau #{MAU[khoa]})")
    r += 1
    o(ws, r, 1, "PENDING")
    o(ws, r, 2, f"{Y_NGHIA_TRANG_THAI['PENDING']} - khong thuoc nhom nao, khong to mau")
    r += 1
    o(ws, r, 1, "Phuong an")
    o(ws, r, 2, ", ".join(f"{k} -> {v}" for k, v in PHUONG_AN.items())
      + "; dong KHONG_XUAT_* khong co payload -> de trong")
    r += 1
    o(ws, r, 1, "QoS/QoE gui CTS")
    # Hay bi so voi cot TB cua file hau kiem -> phai noi ro la 2 so khac nhau.
    o(ws, r, 2, "MIN diem theo ngay trong 7 ngay sau CR, CAT phan thap phan (int) - "
                "KHAC TB trong file hau kiem, khong so truc tiep")
    r += 1
    o(ws, r, 1, "Tram cua cell")
    o(ws, r, 2, "Tram chua cell bi anh huong (cr_affected_cells), KHAC tram tat cua session; "
                "Tinh/Vendor theo tram nay")
    return r + 1


def ve_excel_phieu(rows: list[dict]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    ve_sheet_phieu(wb, rows)
    ws = wb.create_sheet("Chu giai")
    chu_giai_phieu(ws, 1)
    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 90
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
