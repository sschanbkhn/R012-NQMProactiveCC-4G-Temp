"""
uoc_luong_vi_tri_cran() - uoc luong vi tri (lat/lon) cua cell NGUON thuoc
tram TOA_DO_DUNG_CHUNG (CRAN), qua toa do cac tram DICH TIN_CAY ma cell do
co HO sang. BUOC 4c (10/10/2026, yeu cau truc tiep user).

HAM THUAN (khong I/O) - nhan ho_neighbor rows (DA nap, dang dict) + ket qua
phan_loai_toa_do() (domain/services/ho_delaunay.py) + toa do tram, tra ve
danh sach ban ghi SAN SANG GHI vao bang cell_vi_tri_uoc_luong (xem models/
cell_vi_tri_uoc_luong.py).

=== VI SAO CHI DUNG DE HIEN THI (KHONG duoc dua vao L1/L2/vung Z) ===
Neu dua vi tri uoc luong nay nguoc lai vao phan_lop_delaunay()/chon_cell_cr()
(domain/services/ho_delaunay.py, ho_cell_selector.py) se tao VONG LAP LOGIC:
HO (handover) sinh ra vi tri uoc luong, roi vi tri do lai duoc dung de danh
gia/kiem lai CHINH HO sinh ra no - mat tinh DOC LAP giua 2 nguon chung minh
(toa do thuc te RIMS doc lap voi HO; vi tri uoc luong KHONG doc lap, no LA
HO duoc tinh lai duoi dang khac). Vi tri uoc luong o day CHI la DU LIEU HIEN
THI (ban do xem truoc/API /stations/map), KHONG BAO GIO duoc truyen vao
TramDiem/ThongTinTramDich cua 2 module tren.

=== CONG THUC ===
Voi MOI (enb, sector) nguon la TOA_DO_DUNG_CHUNG:
  1. Gop HO theo TRAM DICH (cong don MOI target_lcr cung 1 target_enb).
  2. Loc trong cac tram dich do, CHI giu tram TIN_CAY (co toa do dang tin).
  3. ty_le_ho_tin_cay = (tong HO vao tram dich TIN_CAY) / (tong HO cua CA
     cell, ke ca tram dich khong TIN_CAY/khong co toa do).
  4. CHI GHI ban ghi khi ty_le_ho_tin_cay >= NGUONG_TY_LE_HO_TIN_CAY VA so
     tram dich TIN_CAY phan biet >= NGUONG_SO_TRAM_DICH_TOI_THIEU - nguoc
     lai KHONG ghi gi (= "khong xac dinh", KHONG ghi 0%/toa do rong).
  5. Vi tri = trung tam co TRONG SO (trong so = tong HO/tram dich TIN_CAY).
"""

from collections import defaultdict

from domain.services.ho_delaunay import TIN_CAY, TOA_DO_DUNG_CHUNG

# 2 hang so co ten (yeu cau truc tiep user) - nguong CHOT TAM, chua co khao
# sat rieng de tinh gia tri "toi uu" (khac N_MIN_HO_SECTOR da do thuc te) -
# 50% la da so, 3 tram la du de trung binh hoa bot nhieu tu 1-2 tram dich le.
NGUONG_TY_LE_HO_TIN_CAY = 0.5
NGUONG_SO_TRAM_DICH_TOI_THIEU = 3


def uoc_luong_vi_tri_cran(
    rows: list[dict],
    phan_loai: dict[str, str],
    tram_coords: dict[int, tuple[float, float]],
) -> list[dict]:
    """rows: ho_neighbor rows DA giai ma (can field source_enb, source_sector,
    target_enb, ho_attempt - dang dict tra tu adapters/netact/import_ho_neighbor.py::doc_csv()).
    phan_loai: tram_id(str) -> TIN_CAY|TOA_DO_DUNG_CHUNG (tren TOAN BO tram
    lien quan, xem domain/services/ho_delaunay.py::phan_loai_toa_do()).
    tram_coords: enb(int) -> (lat, lon) cho MOI tram co toa do.

    Tra [{"enb":int, "lcr":int (=source_sector), "lat":float, "lon":float,
    "ty_le_ho_tin_cay":float, "so_tram_dich":int}] - CHI cac (enb,sector) du
    dieu kien (xem dac ta CONG THUC dau file)."""
    theo_nguon: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        theo_nguon[(r["source_enb"], r["source_sector"])][r["target_enb"]] += r["ho_attempt"]

    ket_qua: list[dict] = []
    for (enb, sector), theo_dich in theo_nguon.items():
        if phan_loai.get(str(enb)) != TOA_DO_DUNG_CHUNG:
            continue  # chi uoc luong cho tram NGUON la CRAN - tram TIN_CAY da co toa do that

        tong_ho = sum(theo_dich.values())
        if tong_ho == 0:
            continue

        tin_cay = [
            (target_enb, attempt) for target_enb, attempt in theo_dich.items()
            if phan_loai.get(str(target_enb)) == TIN_CAY and target_enb in tram_coords
        ]
        tong_ho_tin_cay = sum(att for _, att in tin_cay)
        ty_le = tong_ho_tin_cay / tong_ho
        so_tram_dich = len(tin_cay)

        if ty_le < NGUONG_TY_LE_HO_TIN_CAY or so_tram_dich < NGUONG_SO_TRAM_DICH_TOI_THIEU:
            continue  # khong du dieu kien - "khong xac dinh", KHONG ghi gi

        lat = sum(tram_coords[te][0] * att for te, att in tin_cay) / tong_ho_tin_cay
        lon = sum(tram_coords[te][1] * att for te, att in tin_cay) / tong_ho_tin_cay
        ket_qua.append({
            "enb": enb, "lcr": sector, "lat": lat, "lon": lon,
            "ty_le_ho_tin_cay": ty_le, "so_tram_dich": so_tram_dich,
        })

    return ket_qua
