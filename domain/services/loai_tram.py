"""
loai_tram_tu_ten_cell() - suy LOAI TRAM (macro/small cell/...) tu 1 KY TU
ngay SAU SO SITE trong ten cell. Tu: quyet dinh 02/10/2026 (KHONG chay CR
cho small cell - du lieu van giu trong cell_infor, chi loai khoi danh sach
THUC THI CR, xem domain/services/neighbor_cell_filter.py::filter_for_cr()).

# Quyet dinh design: loai tram = ky tu NGAY SAU so site, TRUOC so cell/sector
# Tai sao: VD "4G-TPO065S11-TQG" -> "TPO065" la ma site, "S" la loai tram,
# "11" la so cell/sector, "TQG" la tinh. Day la quy uoc dat ten CO SAN cua
# VNPT (khong phai suy doan moi tu module nay) - cung HO QUY UOC voi
# domain/services/oss_routing.py (suy ma tinh cu tu TEN CELL), chi khac VI
# TRI trich xuat trong cung 1 ten.
#
# Du lieu THAT doi chieu (5 NetAct, dem theo loai tram, 02/10/2026):
#   M 74.627   W 6.087   F 2.411   S 1.413   E 106   X 11   R 6   P 1
# CHOT: CHI "S" va "P" la small cell (khong chay CR), 6 loai con lai la
# macro/cac loai tram lon khac (chay CR binh thuong) - KHONG tu suy doan
# them loai nao khac ngoai 2 gia tri da xac nhan nay.
"""

import re

# MA KHU VUC (SUA 15/10/2026, yeu cau truc tiep user, bug phat hien qua khao
# sat NA10 - tram HCM) - LUON 3 KY TU: ky tu DAU la CHU, 2 ky tu SAU la CHU
# hoac SO. Da so la 3 CHU (vd "BDH"), nhung rieng HCM dung SO cho ma QUAN
# (vd "Q01"/"Q08" = Quan 1/Quan 8) - truoc day 2 regex duoi day doi khu vuc
# la CHU THUAN ([A-Z]{2,4}), khien MOI ten dang "4G-Q01219S-HCM" khong khop
# duoc mau -> roi vao KHAC (ke ca small cell, IBS...) - anh huong ~2.442/4.789
# tram KHAC CA NUOC (51%), rieng HCM toi 2.441/2.623 (93%). DUNG CHUNG 1 dinh
# nghia giua regex ten CELL va regex ten TRAM duoi day (nhu _SITE_RE o
# domain/services/ho_delaunay.py, GIU NGUYEN - khong thuoc pham vi sua lan
# nay, xem ghi chu rieng o _LOAI_TU_TEN_TRAM_RE).
_MA_KHU_VUC = r"[A-Z][A-Z0-9]{2}"

# Tien to CHAP NHAN NHIEU DANG (4G-/UL-/UL_/LN-/SN-...) - GIONG quy uoc
# _SITE_RE (truoc day CHI nhan "4G-" cho ten CELL, gio mo rong cho DONG BO
# voi regex ten TRAM duoi day - KHONG anh huong nguoc, moi ten "4G-..." cu
# van khop binh thuong, chi THEM kha nang nhan dang khac neu co).
_LOAI_TRAM_RE = re.compile(rf"^[A-Za-z0-9]+[-_]{_MA_KHU_VUC}[0-9]+([A-Z])[0-9]+-[A-Z]{{3}}$")

LOAI_TRAM_SMALL_CELL = {"S", "P"}


def loai_tram_tu_ten_cell(cell_name: str) -> str | None:
    """Tra 1 ky tu loai tram (vd "M", "S"...) tu ten cell, hoac None neu ten
    KHONG dung mau "4G-<ma site><loai tram><so cell>-<tinh>".

    CO Y tra None thay vi raise - cung tinh than voi
    domain/services/oss_routing.py::ma_tinh_cu_tu_ten_cell(): 1 cell sai mau
    KHONG duoc lam hong toan bo request, caller (neighbor_cell_filter.py) tu
    quyet dinh loai rieng cell do, van chay tiep voi cac cell con lai.
    """
    if not cell_name:
        return None
    m = _LOAI_TRAM_RE.match(cell_name)
    return m.group(1) if m else None


# === PHAN LOAI TRAM DE HIEN THI (THEM 11-12/10/2026, yeu cau truc tiep user:
# "PHAN LOAI TRAM + DO ANH HUONG") ===
#
# Quyet dinh 11-12/10/2026: GIU NGUYEN cach tinh L1/L2 hien tai (Delaunay,
# domain/services/ho_delaunay.py) - phan loai duoi day CHI de HIEN THI tren
# ban do/API, KHONG duoc dung de doi logic chon L1/L2/vung Z/danh sach B o bat
# ky noi nao. Quyet dinh co dung lam tieu chi loc L1/L2 (vd "CHI macro") hay
# khong se lam SAU, dang danh gia muc do anh huong truoc (xem muc 3 DO trong
# bao cao kem theo thay doi nay).
#
# Gom 8 ky tu loai tram THAT (xem doi chieu du lieu dau file: M/W/B/E/X/R/F/S/P)
# thanh 4 nhom LON de hien thi don gian hon, theo dung yeu cau user:
NHOM_MACRO = "MACRO"
NHOM_IBS = "IBS"
NHOM_SMALL_CELL = "SMALL_CELL"
NHOM_KHAC = "KHAC"

_NHOM_THEO_CHU_CAI = {
    "M": NHOM_MACRO, "W": NHOM_MACRO, "B": NHOM_MACRO, "E": NHOM_MACRO, "X": NHOM_MACRO, "R": NHOM_MACRO,
    "F": NHOM_IBS,
    "S": NHOM_SMALL_CELL, "P": NHOM_SMALL_CELL,
}


def nhom_loai_tram(chu_cai: str | None) -> str:
    """Gom 1 ky tu loai tram (M/W/B/E/X/R/F/S/P...) ve 1 trong 4 nhom hien thi
    (MACRO/IBS/SMALL_CELL/KHAC).

    None hoac KHONG nam trong 8 gia tri da xac nhan -> KHAC (CO Y, KHONG tu
    doan nhom cho chu cai la - giong tinh than LOAI_TRAM_SMALL_CELL o tren:
    chi "chot" nhom cho gia tri DA CO BANG CHUNG du lieu that)."""
    return _NHOM_THEO_CHU_CAI.get(chu_cai, NHOM_KHAC)


# Tach chu cai loai TU TEN TRAM (KHAC ten cell - ten tram KHONG CO "so cell/
# sector" o cuoi, vd "4G-CGY029M-HNI" sv ten cell "4G-CGY029M11-HNI"). Tien to
# [A-Za-z0-9]+[-_] GIU NGUYEN quy uoc voi _SITE_RE (domain/services/ho_delaunay.py)
# de khop ca cac dang da gap trong du lieu that (UL-/UL_/LN-/SN-...), KHONG
# CHI rieng "4G-" nhu _LOAI_TRAM_RE (ten CELL) o tren. DUNG CHUNG _MA_KHU_VUC
# (SUA 15/10/2026) thay vi "[A-Z]{2,4}[0-9]{2,4}" rieng - mau CU doi khu vuc
# la CHU THUAN nen cac tram dang "Q01"/"Q08" (ma quan HCM, chu+so) KHONG khop
# duoc, roi vao KHAC oan (vd 4G-Q01219S-HCM, UL_Q01149M_HCM).
#
# GHI CHU (KHONG sua lan nay, ngoai pham vi yeu cau): _SITE_RE o ho_delaunay.py
# dung "[A-Z]{2,4}[0-9]{2,4}" CHO MUC DICH KHAC (bat TRON "khu vuc + so tram"
# lam 1 nhom de GOP CUM CUNG SITE, khong chi lay chu cai loai) nen CO THE
# CUNG gap bug tuong tu voi tram Q0x (anh huong phan loai TOA_DO_DUNG_CHUNG/
# CRAN) - can khao sat rieng neu user yeu cau, KHONG tu y mo rong pham vi sua
# lan nay (chi loai_tram.py).
_LOAI_TU_TEN_TRAM_RE = re.compile(rf"^[A-Za-z0-9]+[-_]{_MA_KHU_VUC}[0-9]+([A-Z])[-_][A-Z]{{3}}$")


def loai_tram_tu_ten_tram(ten_tram: str | None) -> str:
    """Tra NHOM loai tram (MACRO/IBS/SMALL_CELL/KHAC) tu TEN TRAM (bang tram,
    KHONG phai ten cell). SUA 12/10/2026 (quyet dinh "L1/L2 CHI TINH VOI TRAM
    MACRO"): KHAC "chi de hien thi" nhu dac ta goc o tren (da CU, GIU NGUYEN
    van ban lich su) - ham nay NAY CON duoc dung de LOC tap diem Delaunay
    (loai IBS/SMALL_CELL), gan layer "IBS"/"SMALL_CELL" cho tram dich, va xac
    dinh "X la IBS" (xem domain/services/ho_delaunay.py, ho_cell_selector.py).
    Ten khong khop mau hoac rong -> KHAC (khong raise - giong triet ly
    loai_tram_tu_ten_cell(), 1 tram ten la khong duoc lam hong ca danh sach
    dang hien thi/tinh toan)."""
    if not ten_tram:
        return NHOM_KHAC
    m = _LOAI_TU_TEN_TRAM_RE.match(ten_tram)
    return nhom_loai_tram(m.group(1) if m else None)
