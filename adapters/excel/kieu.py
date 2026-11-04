"""
Kieu trinh bay Excel DUNG CHUNG (DOT 2, 18/10/2026, yeu cau user: to mau sang).

Gom 1 cho de file hau kiem va cac file dashboard CUNG bang mau - nguoi doc
quen 1 quy uoc mau, khong phai doc lai chu giai moi file. Chi lo trinh bay.
"""

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from domain.value_objects.trang_thai_phieu import CHO_XUAT_TAY, LOI, THANH_CONG

# Bang mau (ma hex user chot). Ten = y nghia, khong phai ten mau, de doi mau
# khong phai sua cho dung.
MAU = {
    "tieu_de": "DDEBF7",
    "qos": "E2EFDA",
    "qoe": "EDE7F6",
    "phieu": "FFF2CC",
    "dat": "E8F5E9",
    "khong_dat": "FDECEA",
    "thieu": "F2F2F2",
    "co_phieu": "FFF8E1",
    "khoi_xen_ke": "FAFAFA",
}
# Chu do dam cho o "Khong dat" - nen do nhat mot minh de bi lan voi o trong.
CHU_KHONG_DAT = "C00000"

VIEN = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
GIUA = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Gia tri hien thi -> khoa mau o "Danh gia"/"ket_qua" (ca dang Excel hau kiem
# lan ma API dashboard).
MAU_DANH_GIA = {
    "Dat": "dat", "DAT": "dat",
    "Khong dat": "khong_dat", "KHONG_DAT": "khong_dat",
    "Thieu du lieu": "thieu", "INSUFFICIENT_DATA": "thieu",
}


# Nhom trang thai phieu -> khoa MAU (19/10/2026, user chot): dung lai ma mau
# san co thay vi them ma moi - xanh = xong, do = loi, vang = can nguoi xu ly.
MAU_NHOM_PHIEU = {THANH_CONG: "dat", LOI: "khong_dat", CHO_XUAT_TAY: "phieu"}


def nen(ma: str) -> PatternFill:
    return PatternFill("solid", start_color=MAU.get(ma, ma), end_color=MAU.get(ma, ma))


def o(ws, dong: int, cot: int, gia_tri=None, *, mau: str | None = None, dam: bool = False,
      dinh_dang: str | None = None):
    c = ws.cell(row=dong, column=cot, value=gia_tri)
    c.border = VIEN
    c.alignment = GIUA
    if mau:
        c.fill = nen(mau)
    if dam:
        c.font = Font(bold=True)
    if dinh_dang:
        c.number_format = dinh_dang
    return c


def to_danh_gia(c) -> None:
    """To o Dat/Khong dat/Thieu du lieu theo MAU_DANH_GIA (de mau nen khoi)."""
    khoa = MAU_DANH_GIA.get(c.value)
    if not khoa:
        return
    c.fill = nen(khoa)
    if khoa == "khong_dat":
        c.font = Font(bold=True, color=CHU_KHONG_DAT)


def gop(ws, r1: int, c1: int, r2: int, c2: int, gia_tri, *, mau: str | None = None, dam: bool = True):
    # Ke vien + to ca vung TRUOC khi gop - openpyxl chi giu style o goc trai,
    # cac o con lai mat vien neu khong ke rieng.
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            o(ws, r, c, mau=mau, dam=dam)
    ws.cell(row=r1, column=c1, value=gia_tri)
    if r1 != r2 or c1 != c2:
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def rong_vua_noi_dung(ws, tu_dong: int = 1, toi_thieu: int = 8, toi_da: int = 45) -> None:
    """Do rong cot theo chuoi dai nhat. Bo qua o gop ngang (tieu de nhom) - do
    dai cua no chia cho nhieu cot, tinh vao 1 cot se lam cot do rong vo ly."""
    gop_ngang = set()
    for m in ws.merged_cells.ranges:
        if m.min_col != m.max_col:
            for r in range(m.min_row, m.max_row + 1):
                for c in range(m.min_col, m.max_col + 1):
                    gop_ngang.add((r, c))
    rong: dict[int, int] = {}
    for row in ws.iter_rows(min_row=tu_dong):
        for c in row:
            if c.value is None or (c.row, c.column) in gop_ngang:
                continue
            dai = max(len(x) for x in str(c.value).split("\n"))
            rong[c.column] = max(rong.get(c.column, 0), dai)
    for cot, dai in rong.items():
        ws.column_dimensions[get_column_letter(cot)].width = max(toi_thieu, min(toi_da, dai + 2))


def bang(ws, tieu_de: list[str], dong_du_lieu: list[list], *, cot_danh_gia: set[int] = frozenset(),
         cot_phieu: set[int] = frozenset(), dinh_dang_so: dict[int, str] | None = None) -> None:
    """Bang phang 1 dong tieu de (dung cho sheet dashboard). Cot danh so tu 1."""
    for i, t in enumerate(tieu_de, start=1):
        o(ws, 1, i, t, mau="tieu_de", dam=True)
    for r, dong in enumerate(dong_du_lieu, start=2):
        for i, v in enumerate(dong, start=1):
            c = o(ws, r, i, v, dinh_dang=(dinh_dang_so or {}).get(i))
            if i in cot_danh_gia:
                to_danh_gia(c)
            if i in cot_phieu and v:
                c.fill = nen("co_phieu")
    ws.freeze_panes = "A2"
    rong_vua_noi_dung(ws)


def sheet_chu_giai(wb, luat: list[str]) -> None:
    """Sheet "Chu giai": y nghia tung mau + luat danh gia dang ap dung."""
    ws = wb.create_sheet("Chu giai")
    o(ws, 1, 1, "Mau", mau="tieu_de", dam=True)
    o(ws, 1, 2, "Y nghia", mau="tieu_de", dam=True)
    y_nghia = [
        ("tieu_de", "Dong tieu de"),
        ("qos", "Nhom cot QoS"),
        ("qoe", "Nhom cot QoE"),
        ("phieu", "Nhom cot phieu xuat CLK"),
        ("dat", "Danh gia: Dat"),
        ("khong_dat", "Danh gia: Khong dat (chu do dam)"),
        ("thieu", "Danh gia: Thieu du lieu"),
        ("co_phieu", "O co ma phieu"),
        ("khoi_xen_ke", "Khoi session xen ke (trang / xam rat nhat) de de doc"),
    ]
    for r, (khoa, mo_ta) in enumerate(y_nghia, start=2):
        c = o(ws, r, 1, f"#{MAU[khoa]}", mau=khoa)
        if khoa == "khong_dat":
            c.font = Font(bold=True, color=CHU_KHONG_DAT)
        o(ws, r, 2, mo_ta)
    r = len(y_nghia) + 3
    o(ws, r, 1, "Luat danh gia", mau="tieu_de", dam=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    for i, dong in enumerate(luat, start=r + 1):
        ws.cell(row=i, column=1, value=dong)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 70


def luat_danh_gia(min_ngay: int, muc_toi_thieu: float, lech_qos: float, lech_qoe: float) -> list[str]:
    """Cau chu giai luat - nhan NGUONG tu caller (khong go cung so)."""
    return [
        "QoS va QoE dung CHUNG 1 ham danh gia (EvaluationService).",
        "TB = trung binh cac ngay CO du lieu (khong chia cung 7), lam tron 2 chu so.",
        # Ghi ro "TB THO": nguoi doc tu tru 2 o TB da tron co the lech 0.01 so
        # voi cot Lech (4.3333 - 4.1667 = 0.17, nhung 4.33 - 4.17 = 0.16).
        "Lech = round(TB truoc THO - TB sau THO, 2), tru tren TB CHUA lam tron (duong = tut); "
        "lam tron TRUOC khi so nguong.",
        f"< {min_ngay} ngay co du lieu (truoc HOAC sau) -> Thieu du lieu.",
        f"TB sau < {muc_toi_thieu:.1f} HOAC Lech > {lech_qos:.1f} (QoS) / {lech_qoe:.1f} (QoE) -> Khong dat.",
        "Con lai -> Dat.",
        "So lieu lay tu snapshot luu luc danh gia (qos_snapshot/qoe_snapshot).",
    ]
