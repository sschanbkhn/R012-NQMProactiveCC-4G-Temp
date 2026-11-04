"""
Ve file Excel hau kiem tu cac khoi du lieu cua XuatExcelHauKiemUseCase
(18/10/2026, bo cuc theo file mau Check_4G-TXN250M-HNI.xlsx + bo sung cua user;
DOT 2: to mau sang + sheet "Chu giai", xem adapters/excel/kieu.py).

CHI LO TRINH BAY (gop o, vien, mau, dinh dang so) - khong tinh toan gi. Tach
khoi application/ vi openpyxl la chi tiet ha tang, use case khong can biet.

Bo cuc cot (sheet "Hau kiem", cac session noi nhau, cach 1 dong trong):
  A Ngay thuc hien | B Tram tac dong huy/tat | C Site anh huong | D Cell anh huong
  | E Cell chay CR (R012) | F Cell hau kiem
  | G-M QoS: TB truoc CR, TB sau CR, Lech, Danh gia, So ngay co du lieu truoc CR,
    So ngay co du lieu sau CR, So ngay >= 3
  | N-T QoE: (7 cot nhu QoS) | U-W Phieu xuat CLK: Ma phieu, Phuong an, Trang thai
  phieu | X Ghi chu
(19/10/2026: them TB truoc + so ngay truoc - Lech/Thieu du lieu phu thuoc ca ve
truoc, nguoi doc phai tu kiem lai duoc ket luan tu chinh file. Cung ngay: 2 cot
Hien truong/He thong -> 3 cot Ma phieu/Phuong an/Trang thai de thay ca phieu
FAILED/KHONG_XUAT_*; them sheet "Phieu" ve bang adapters/excel/phieu_xlsx.py.)
"""

from io import BytesIO

from openpyxl import Workbook

from adapters.excel.kieu import MAU_NHOM_PHIEU, gop, nen, o, rong_vua_noi_dung, sheet_chu_giai, to_danh_gia
from adapters.excel.phieu_xlsx import chu_giai_phieu, ve_sheet_phieu
from domain.value_objects.trang_thai_phieu import nhom_trang_thai

_TIEU_DE_CHI_SO = ["TB truoc CR", "TB sau CR", "Lech", "Danh gia", "So ngay co du lieu truoc CR",
                   "So ngay co du lieu sau CR", "So ngay >= 3"]
_N = len(_TIEU_DE_CHI_SO)
_QOS, _QOE = 7, 7 + _N  # cot dau nhom
_PHIEU = _QOE + _N  # 3 cot phieu: Ma phieu, Phuong an, Trang thai phieu
_GHI_CHU = _PHIEU + 3
_COT_DANH_GIA = {_QOS + 3, _QOE + 3}
_COT_MA_PHIEU = _PHIEU
_COT_TT_PHIEU = _PHIEU + 2
_COT_SO = {c + i for c in (_QOS, _QOE) for i in range(3)}  # TB truoc, TB sau, Lech

# "So ngay >= 3" de canh "Danh gia" de bi hieu nham la tieu chi - ghi ro o Chu
# giai. Chi file hau kiem co cot nay nen khong dua vao luat_danh_gia dung chung.
_GHI_CHU_SO_NGAY_DAT = "\"So ngay >= 3\" chi la thong ke tham khao, KHONG dung de danh gia."


def _tieu_de(ws) -> None:
    gop(ws, 1, 1, 1, 5, "TAC DONG", mau="tieu_de")
    gop(ws, 1, 6, 1, _GHI_CHU - 1, "HAU KIEM (Trung binh QoS, QoE 7 ngay truoc / sau CR)", mau="tieu_de")
    gop(ws, 1, _GHI_CHU, 3, _GHI_CHU, "Ghi chu", mau="tieu_de")
    for cot, ten in enumerate(
        ["Ngay thuc hien", "Tram tac dong huy/tat", "Site anh huong", "Cell anh huong",
         "Cell chay CR (R012)", "Cell hau kiem"], start=1,
    ):
        gop(ws, 2, cot, 3, cot, ten, mau="tieu_de")
    for bat_dau, nhom, mau in ((_QOS, "QoS", "qos"), (_QOE, "QoE", "qoe")):
        gop(ws, 2, bat_dau, 2, bat_dau + _N - 1, nhom, mau=mau)
        for i, ten in enumerate(_TIEU_DE_CHI_SO):
            o(ws, 3, bat_dau + i, ten, mau=mau, dam=True)
    gop(ws, 2, _PHIEU, 2, _PHIEU + 2, "Phieu xuat CLK", mau="phieu")
    for i, ten in enumerate(["Ma phieu", "Phuong an", "Trang thai phieu"]):
        o(ws, 3, _PHIEU + i, ten, mau="phieu", dam=True)


def _gia_tri_dong(d: dict) -> list:
    """Gia tri cot C..X cua 1 dong."""
    def cs(x):
        x = x or {}
        return [x.get("tb_truoc"), x.get("tb_sau"), x.get("lech"), x.get("danh_gia"),
                x.get("so_ngay_co_dl_truoc"), x.get("so_ngay_co_dl"), x.get("so_ngay_dat")]
    ph = d.get("phieu") or {}
    return [d.get("site"), d["cell_anh_huong"], d["cell_cr"], d["cell_hau_kiem"],
            *cs(d["qos"]), *cs(d["qoe"]), ph.get("ma"), ph.get("phuong_an"), ph.get("trang_thai"),
            d["ghi_chu"]]


def ve_excel(khoi_list: list[dict], luat: list[str], phieu: list[dict] | None = None) -> bytes:
    """luat: cac cau luat danh gia cho sheet "Chu giai" (caller dien nguong).
    phieu: dong tu ICrPhieuRepo.dong_excel() cho sheet "Phieu"."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Hau kiem"
    _tieu_de(ws)

    r = 4
    for stt, k in enumerate(x for x in khoi_list if x["dong"]):
        dong = k["dong"]
        r_cuoi = r + len(dong) - 1
        # Khoi xen ke trang / xam rat nhat - nhieu session lien nhau van tach
        # duoc bang mat. Mau nhom QoS/QoE/phieu chi to o tieu de; o du lieu
        # dung mau khoi, de mau danh gia/phieu noi bat.
        mau_khoi = "khoi_xen_ke" if stt % 2 else None
        gop(ws, r, 1, r_cuoi, 1, k["ngay_cr"], mau=mau_khoi, dam=False)
        gop(ws, r, 2, r_cuoi, 2, k["tram"], mau=mau_khoi, dam=False)
        for i, d in enumerate(dong):
            for cot, v in enumerate(_gia_tri_dong(d), start=3):
                mau = "co_phieu" if cot == _COT_MA_PHIEU and v else mau_khoi
                c = o(ws, r + i, cot, v, mau=mau, dinh_dang="0.00" if cot in _COT_SO else None)
                if cot in _COT_DANH_GIA:
                    to_danh_gia(c)
                # Trang thai phieu to theo NHOM - cung mau voi file phieu.
                if cot == _COT_TT_PHIEU and MAU_NHOM_PHIEU.get(nhom_trang_thai(v)):
                    c.fill = nen(MAU_NHOM_PHIEU[nhom_trang_thai(v)])
        r = r_cuoi + 2  # cach 1 dong giua 2 session
    # Co dinh 3 dong tieu de + 2 cot ngay/tram khi cuon.
    ws.freeze_panes = "C4"
    rong_vua_noi_dung(ws, tu_dong=2)
    ve_sheet_phieu(wb, phieu or [])
    sheet_chu_giai(wb, [*luat, _GHI_CHU_SO_NGAY_DAT])
    cg = wb["Chu giai"]
    chu_giai_phieu(cg, cg.max_row + 2)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
