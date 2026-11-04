"""
Vendor value object — enum 4 vendor + UNKNOWN, va chuan_hoa_vendor().
Tu: docs/audit/READINESS.md muc T1/T2 (do san sang multi-vendor); V2 buoc 2.

=== NGUON DU LIEU ===
tram.ten_thiet_bi (models/tram.py:23) — VARCHAR(200), nullable, KHONG rang buoc,
KHONG index. Du lieu do RIMS sync ve (adapters/http/sync_tram_from_enodeb.py).

Da do 58.230 dong ngay 13/09/2026: DUNG 4 gia tri
  NOKIA 22.794 | ERICSSON 19.573 | HUAWEI 11.247 | ZTE 4.616
0 NULL, 0 chuoi rong, 0 khoang trang thua, 0 chu thuong.

=== VI SAO CAN CHUAN HOA KHI DU LIEU DANG SACH ===
Vi cot la VARCHAR TU DO, khong co CHECK, khong co FK, khong co enum ben DB.
"Sach hom nay" la mot QUAN SAT, khong phai mot BAO DAM. Lan sync RIMS toi co
the mang ve "Nokia", " ZTE", "HUAWEI " hay mot vendor thu 5 — khong co gi trong
he thong chan duoc.

=== VI SAO UNKNOWN THAY VI None ===
UNKNOWN la LUOI AN TOAN, KHONG phai nhanh chet.

1. None co 2 nghia lan nhau: "tram nay khong co du lieu vendor" va "co du lieu
   nhung he thong khong hieu". Hai tinh huong doi hoi 2 hanh dong khac han:
   cai dau la thieu sync, cai sau la DU LIEU LA CAN DIEU TRA. Gop lam mot thi
   mat han tin hieu thu hai.
2. Gia tri la PHAI HIEN RA, khong duoc bien mat. Neu tra None roi FE an dong
   do di, mot vendor thu 5 xuat hien tren mang se khong ai biet cho den luc co
   nguoi thac mac "sao tong so tram khong khop". UNKNOWN bat no phai hien tren
   bang, ke ben 4 vendor kia.
3. Doi xung voi cach EvaluationService xu ly thieu du lieu: danh dau
   INSUFFICIENT_DATA chu khong im lang bo qua (xem
   domain/services/evaluation_service.py). Cung mot nguyen tac: KHONG DOAN,
   KHONG BO QUA — danh dau roi de nguoi quyet.

Query canh bao dinh ky (dat kem trong file migration cua buoc 5):
    SELECT DISTINCT ten_thiet_bi FROM tram
    WHERE ten_thiet_bi NOT IN ('NOKIA','ERICSSON','HUAWEI','ZTE');

=== KHONG import gi ngoai stdlib ===
domain/ CHI import Python stdlib + domain/ noi bo (ARCHITECTURE.md SS9).
"""

from enum import Enum


class Vendor(str, Enum):
    """4 vendor dang chay tren mang + UNKNOWN.

    Ke thua str (giong CrStatus o domain/entities/cr_session.py) de value khop
    thang chuoi khi serialize ra JSON va khi so sanh voi du lieu DB — khong phai
    goi .value o moi cho dung."""

    NOKIA = "NOKIA"
    ERICSSON = "ERICSSON"
    HUAWEI = "HUAWEI"
    ZTE = "ZTE"

    # KHONG phai mot vendor. La ket luan "co gia tri nhung khong khop tap da
    # biet, HOAC khong co gia tri" — xem docstring dau file.
    UNKNOWN = "UNKNOWN"


# Tap gia tri hop le, suy TU CHINH enum — khong go lai danh sach chuoi o day.
# Go lai la tao ban sao thu hai, them vendor moi vao enum ma quen sua cho nay
# thi chuan_hoa_vendor() se tra UNKNOWN cho mot vendor da duoc khai bao.
_HOP_LE = {v.value for v in Vendor if v is not Vendor.UNKNOWN}


def chuan_hoa_vendor(ten_thiet_bi: str | None) -> Vendor:
    """tram.ten_thiet_bi (chuoi tu do) -> Vendor. KHONG BAO GIO nem loi.

    Ham nay nam tren duong DOC cua GET /stations — 1 lan goi cho MOI dong tra
    ve. Nem loi o day se lam hong ca trang danh sach chi vi 1 tram co du lieu la.

    Quy tac:
      None / chuoi rong / chi co khoang trang  -> UNKNOWN
      trim + upper roi khop tap da biet        -> vendor tuong ung
      khong khop gia tri nao                   -> UNKNOWN (KHONG doan, KHONG bo qua)

    KHONG co ban do alias ("NSN" -> NOKIA, "HW" -> HUAWEI...): du lieu that chua
    tung xuat hien dang do (da do 58.230 dong). Them alias bay gio la doan truoc
    mot van de chua ton tai, va neu doan sai thi no gan nhan SAI cho tram that
    ma khong ai biet. Khi nao RIMS thuc su tra ve alias, query canh bao o
    docstring dau file se lam no hien ra, luc do moi them — kem du lieu that.
    """
    if ten_thiet_bi is None:
        return Vendor.UNKNOWN

    # .strip() xu ly luon ca chuoi chi gom khoang trang ("   " -> "").
    # .upper() sau .strip(): thu tu khong quan trong ve ket qua nhung giu nguyen
    # cach viet cua tang DB o buoc 4 (vendor_norm = vendor.strip().upper()).
    gia_tri = ten_thiet_bi.strip().upper()
    if not gia_tri:
        return Vendor.UNKNOWN

    if gia_tri in _HOP_LE:
        return Vendor(gia_tri)

    # Gia tri LA: co du lieu nhung khong khop tap da biet. Tra UNKNOWN de no
    # hien ra tren UI thay vi bi nuot — xem docstring dau file, muc 2.
    return Vendor.UNKNOWN
