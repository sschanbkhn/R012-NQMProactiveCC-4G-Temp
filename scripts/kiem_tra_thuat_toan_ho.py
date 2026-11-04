"""
KIEM TRA thuat toan chon cell CR tu HO (domain/services/ho_cell_selector.py +
ho_delaunay.py) tren DU LIEU THAT - CHI DOC, KHONG ghi DB, KHONG goi CDS.
Tu: quyet dinh 06-08/10/2026 (BO CDS, yeu cau truc tiep user).

TAI SU DUNG (import truc tiep, cung thu muc scripts/) co che doc file +
giai ma ECI + nap tram/cell_infor tu 2 script truoc (KHONG viet lai):
  - scripts.spike_ho_neighbor: tim file CSV, regex DN, sector tu LNCEL.
  - scripts.phan_tich_nguong_ho: doc toan bo CSV 1 lan (AGG theo tram+sector),
    nap bang tram, nap cell_infor.

1. Tram 117903 (du lieu that): in L1, L2, A tung sector (kem % cong don), B,
   cell BAT_THUONG.
2. Mau 300 tram nguon NA09 (= tinh HNI, xem G3 trong phan_tich_nguong_ho.py):
   so cell bi chan boi vung Z TRUOC/SAU 2 luat an toan (cung site - da nam
   san trong phan_lop_delaunay(), toa do X nghi sai); so tram X/tram dich bi
   gan TOA_DO_NGHI_SAI, 10 vi du kem toa do.
"""

import asyncio
import random

from domain.services.ho_cell_selector import ThongTinTramDich, chon_cell_cr
from domain.services.ho_delaunay import TOA_DO_DUNG_CHUNG, TramDiem, phan_loai_toa_do, phan_lop_delaunay
from domain.services.loai_tram import NHOM_IBS, NHOM_MACRO, loai_tram_tu_ten_tram
from domain.services.neighbor_cell_filter import band_tu_lncel
from scripts.phan_tich_nguong_ho import (
    _nhom_theo_tram,
    _tim_file_csv,
    doc_toan_bo_csv,
    nap_cell_infor_dn_map,
    nap_toan_bo_tram,
)

RANDOM_SEED = 42
SO_MAU = 300
X_TEST_ID = 117903


def _ho_rows_cho_tram(nhom_theo_tram: dict, enb: int) -> list[dict]:
    # source_lncel_name: AGG (tu doc_toan_bo_csv()) da GOP theo sector, mat
    # ten CELL NGUON rieng - nhung MBF_ da bi loai TU LUC doc file (chi nhan
    # ID nguon 2 chu so, xem phan_tich_nguong_ho.py), nen dien 1 ten GIA (KHONG
    # phai "MBF_...") la an toan - chon_cell_cr() chi dung field nay de phong
    # ve MBF_, khong dung cho muc dich nao khac o day.
    rows = []
    for sector, cands in nhom_theo_tram.get(enb, {}).items():
        for (t_enb, t_lcr), v in cands.items():
            sr = (v["sr_x_att"] / v["sr_w"]) if v["sr_w"] > 0 else None
            rows.append({
                "source_sector": sector, "target_enb": t_enb, "target_lcr": t_lcr,
                "ho_attempt": v["attempt"], "ho_sr": sr,
                "source_lncel_name": "4G-DA-GOP-SECTOR",
            })
    return rows


def _tram_diem_list(tram_theo_enb: dict) -> list[TramDiem]:
    return [
        TramDiem(tram_id=str(enb), tram_name=info["tram_name"], lat=info["lat"], lon=info["lon"])
        for enb, info in tram_theo_enb.items() if info["lat"] is not None and info["lon"] is not None
    ]


def _thong_tin_tram_dich(tram_theo_enb: dict, phan_loai: dict[str, str]) -> dict[int, ThongTinTramDich]:
    return {
        enb: ThongTinTramDich(
            tram_id=info["tram_id"], tram_name=info["tram_name"],
            ten_thiet_bi=info["ten_thiet_bi"], lat=info["lat"], lon=info["lon"],
            toa_do_dung_chung=phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG,
        )
        for enb, info in tram_theo_enb.items()
    }


def _in_tram(x_enb: int, nhan: str, nhom: dict, tram_theo_enb: dict, tram_diem_list: list, thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str]) -> None:
    print("=" * 78)
    print(f"MUC 1 - Tram {x_enb} ({nhan}, du lieu that)")
    x_info = tram_theo_enb.get(x_enb)
    if x_info is None or x_info["lat"] is None:
        print(f"  DUNG: tram {x_enb} khong co trong bang tram hoac khong co toa do.")
        return

    x_diem = TramDiem(tram_id=str(x_enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
    x_la_dung_chung = phan_loai.get(str(x_enb)) == TOA_DO_DUNG_CHUNG
    print(f"  Toa do X: lat={x_info['lat']} lon={x_info['lon']} ({x_info['tram_name']})")
    print(f"  X la TOA_DO_DUNG_CHUNG: {x_la_dung_chung}")

    ung_vien = [d for d in tram_diem_list if d.tram_id != str(x_enb)]
    l1_l2 = phan_lop_delaunay(x_diem, ung_vien, phan_loai)
    l1 = sorted([t for t in l1_l2 if t.layer == "L1"], key=lambda t: t.km)
    l2 = sorted([t for t in l1_l2 if t.layer == "L2"], key=lambda t: t.km)
    print(f"\n  L1 ({len(l1)} tram):")
    for t in l1:
        print(f"    {t.tram_id:<8} {t.tram_name:<20} {t.km:6.2f}km")
    print(f"\n  L2 ({len(l2)} tram):")
    for t in l2:
        print(f"    {t.tram_id:<8} {t.tram_name:<20} {t.km:6.2f}km")

    ho_rows = _ho_rows_cho_tram(nhom, x_enb)
    if not ho_rows:
        print(f"\n  DUNG: tram {x_enb} khong co du lieu HO.")
        return
    from domain.services.ho_cell_selector import KhongCoDuLieuHoError
    try:
        kq = chon_cell_cr(
            str(x_enb), ho_rows, l1_l2, thong_tin_dich, dn_map,
            x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=x_la_dung_chung,
        )
    except KhongCoDuLieuHoError as exc:
        print(f"\n  DUNG: {exc}")
        return
    if kq.sectors_it_du_lieu:
        print(f"\n  CANH BAO: sector {sorted(kq.sectors_it_du_lieu)} IT_DU_LIEU (duoi N_MIN_HO_SECTOR)")

    print(f"\n  Danh sach A ({len(kq.a)} cell), theo sector, kem % va % cong don:")
    theo_sector: dict[int, list] = {}
    for c in kq.a:
        theo_sector.setdefault(c.sector, []).append(c)
    for sector in sorted(theo_sector):
        xep = sorted(theo_sector[sector], key=lambda c: -c.ho_attempt)
        print(f"    Sector {sector}:")
        cong_don = 0.0
        tong = sum(c.ho_attempt for c in xep)
        for c in xep:
            cong_don += c.ho_attempt
            ten = c.cell_name or f"(CAN_GHEP_TEN, vendor={c.vendor})"
            print(
                f"      enb={c.target_enb:<8} lcr={c.target_lcr:<4} {ten:<24} layer={c.layer:<2} "
                f"attempt={c.ho_attempt:<6} %={100*c.pct_trong_sector:5.1f} %cong_don={100*cong_don/tong:5.1f}"
            )

    print(f"\n  Danh sach B ({len(kq.b)} cell):")
    for c in sorted(kq.b, key=lambda c: (c.sector, c.rank_b)):
        print(f"    sector={c.sector} rank={c.rank_b:<10} enb={c.target_enb:<8} lcr={c.target_lcr:<4} {c.cell_name} layer={c.layer}")

    print(f"\n  Cell BAT_THUONG ({len(kq.bat_thuong)}):")
    for c in kq.bat_thuong:
        print(f"    enb={c.target_enb:<8} lcr={c.target_lcr:<4} %={100*c.pct_trong_sector:.1f} SR={c.ho_sr}")

    print(f"\n  Quan he DAY DU ({len(kq.quan_he_day_du)} dong, GOM CA sector 'phu' bi dedup):")
    for q in sorted(kq.quan_he_day_du, key=lambda q: (q.sector, -q.ho_attempt)):
        print(f"    sector={q.sector} enb={q.target_enb:<8} lcr={q.target_lcr:<4} layer={q.layer:<2} attempt={q.ho_attempt:<6} %={100*q.pct_trong_sector:5.1f} SR={q.ho_sr}")

    print(f"\n  X co HO_DI_XA: {kq.ho_di_xa_x}")
    so_nghi_dich = sum(1 for c in kq.a if c.ho_di_xa_dich)
    print(f"  So cell dich co HO_DI_XA: {so_nghi_dich}")


def _mau_300_tram_na09(nhom: dict, tram_theo_enb: dict, tram_diem_list: list, thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str]) -> None:
    print("\n" + "=" * 78)
    print(f"MUC 2 - Mau {SO_MAU} tram nguon NA09 (= tinh HNI), seed={RANDOM_SEED}")

    ung_vien = [
        enb for enb in nhom
        if enb in tram_theo_enb and tram_theo_enb[enb]["ma_tinh"] == "HNI" and tram_theo_enb[enb]["lat"] is not None
    ]
    rng = random.Random(RANDOM_SEED)
    mau = rng.sample(ung_vien, min(SO_MAU, len(ung_vien)))
    print(f"  So tram ung vien (co HO + co toa do, tinh HNI): {len(ung_vien):,}; da lay mau {len(mau)}")

    so_bat_thuong_thuc_te = 0
    so_z_tong = 0
    so_naive_bi_chan = 0  # neu KHONG co luat an toan (cung site da nam trong Delaunay; chi tat luat toa do X)
    so_x_nghi_toa_do = 0
    so_x_toa_do_dung_chung = 0
    nghi_toa_do_dich: dict[str, dict] = {}
    # IBS/SMALL_CELL THEM 12/10/2026 (quyet dinh "L1/L2 chi tinh voi tram
    # MACRO") - du lieu that CO cell dich loai nay, phai co san trong dict
    # keo tranh KeyError (phat hien qua do lai lan nay tren du lieu NA09 that).
    so_cell_a_theo_layer = {"L1": 0, "L2": 0, "Z": 0, "KHONG_XAC_DINH": 0, "IBS": 0, "SMALL_CELL": 0}

    from domain.services.ho_cell_selector import KhongCoDuLieuHoError

    # SUA 08/10/2026 lan 3 (yeu cau truc tiep user): cac thong ke duoi day
    # (L1/L2, % cell A theo layer, % HO_DI_XA) CHI tinh tren X la TIN_CAY -
    # X TOA_DO_DUNG_CHUNG luon co l1_l2=[] (0 L1/0 L2) va MOI cell roi vao
    # Z/KHONG_XAC_DINH mot cach "gia tao" (khong phan anh mat do hinh hoc
    # thuc), dua vao chung se lam LECH cac so trung binh/median - tach RIENG
    # de so sanh dung voi so lieu "truoc khi loai tram DUNG_CHUNG khoi Delaunay"
    # (8,0%, do tren CA 300 tram, luc do chua co khai niem TOA_DO_DUNG_CHUNG).
    so_khong_du_lieu = 0
    l1_count_list: list[int] = []
    l2_count_list: list[int] = []
    for enb in mau:
        x_info = tram_theo_enb[enb]
        x_la_dung_chung = phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG
        if x_la_dung_chung:
            so_x_toa_do_dung_chung += 1
            continue  # KHONG dua vao thong ke L1/L2/%cell A/HO_DI_XA duoi day

        x_diem = TramDiem(tram_id=str(enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
        ung_vien_diem = [d for d in tram_diem_list if d.tram_id != str(enb)]
        l1_l2 = phan_lop_delaunay(x_diem, ung_vien_diem, phan_loai)
        l1_count_list.append(sum(1 for t in l1_l2 if t.layer == "L1"))
        l2_count_list.append(sum(1 for t in l1_l2 if t.layer == "L2"))
        ho_rows = _ho_rows_cho_tram(nhom, enb)
        if not ho_rows:
            continue
        try:
            kq = chon_cell_cr(
                str(enb), ho_rows, l1_l2, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=False,
            )
        except KhongCoDuLieuHoError:
            so_khong_du_lieu += 1
            continue

        if kq.ho_di_xa_x:
            so_x_nghi_toa_do += 1

        so_bat_thuong_thuc_te += len(kq.bat_thuong)
        for c in kq.a:
            so_cell_a_theo_layer[c.layer] += 1
            if c.layer != "Z":
                continue
            so_z_tong += 1
            # "naive" = AP DUNG luat vung Z (20%+95%) KHONG CAN BIET X co nghi
            # toa do hay khong (bo qua luat an toan rieng cho X).
            dat_naive = c.pct_trong_sector >= 0.20 and c.ho_sr is not None and c.ho_sr >= 95.0
            if not dat_naive:
                so_naive_bi_chan += 1
            if c.ho_di_xa_dich:
                key = c.tram_dich_id or str(c.target_enb)
                if key not in nghi_toa_do_dich:
                    nghi_toa_do_dich[key] = {
                        "nguon": x_info["tram_name"], "dich": c.tram_dich_ten, "km": c.km,
                        "pct": c.pct_trong_sector, "sr": c.ho_sr,
                    }

    import numpy as np

    l1_arr = np.array(l1_count_list)
    l2_arr = np.array(l2_count_list)
    tong_cell_a = sum(so_cell_a_theo_layer.values())
    so_tin_cay = len(mau) - so_x_toa_do_dung_chung
    print(f"\n  So tram X la TOA_DO_DUNG_CHUNG (CRAN, LOAI khoi thong ke duoi day): {so_x_toa_do_dung_chung}/{len(mau)} ({100.0*so_x_toa_do_dung_chung/len(mau):.1f}%)")
    print(f"  Con lai {so_tin_cay} tram X TIN_CAY - thong ke tu day CHI tinh tren nhom nay:")
    print(f"  So tram KHONG co du lieu HO (KhongCoDuLieuHoError, bao gom ca N_MIN): {so_khong_du_lieu}/{so_tin_cay}")
    print(f"  So tram L1: trung_vi={np.median(l1_arr):.0f} P10={np.percentile(l1_arr,10):.0f}")
    print(f"  So tram L2: trung_vi={np.median(l2_arr):.0f} P10={np.percentile(l2_arr,10):.0f}")
    print(f"  (SO VOI BAN CU - truoc gop cum/sua moc loc canh: L1 trung_vi=2, L2 trung_vi=0)")
    print(f"\n  % cell trong A theo layer (tong {tong_cell_a} cell, CHI tren X TIN_CAY):")
    for layer, dem in so_cell_a_theo_layer.items():
        print(f"    {layer}: {dem:,} ({100.0*dem/tong_cell_a:.1f}%)" if tong_cell_a else f"    {layer}: 0")

    print(f"\n  Tong so cell Z (tren {so_tin_cay} tram X TIN_CAY): {so_z_tong:,}")
    print(f"  BAT_THUONG THUC TE (co ap dung luat an toan X-nghi-toa-do): {so_bat_thuong_thuc_te:,}")
    print(f"  Se bi chan NEU AP DUNG luat vung Z MU (khong co luat an toan toa do X): {so_naive_bi_chan:,}")
    print(f"  => Luat an toan 'X co HO_DI_XA' da CUU {so_naive_bi_chan - so_bat_thuong_thuc_te:,} cell khoi bi chan oan")
    print(f"\n  So tram X (TIN_CAY) duoc gan HO_DI_XA: {so_x_nghi_toa_do}/{so_tin_cay} ({100.0*so_x_nghi_toa_do/so_tin_cay:.1f}%)" if so_tin_cay else "")
    print(f"  (SO VOI BAN CU - truoc khi loai tram DUNG_CHUNG khoi Delaunay: 8,0%)")
    print(f"  So tram DICH duoc gan HO_DI_XA (phan biet): {len(nghi_toa_do_dich)}")
    print("  10 vi du tram dich co HO_DI_XA (nguon, dich, km, %HO, SR):")
    for info in list(nghi_toa_do_dich.values())[:10]:
        print(f"    {info['nguon']:<20} -> {info['dich']:<20} {info['km']:6.2f}km %={100*info['pct']:5.1f} SR={info['sr']}")


def _so_sanh_a_b_truoc_sau_luat_10pct(
    x_enb: int, nhan: str, nhom: dict, tram_theo_enb: dict, tram_diem_list: list,
    thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str],
) -> None:
    """THEM 10/10/2026 - so sanh TOAN BO pipeline (Delaunay + chon_cell_cr(),
    giong _in_tram()) TRUOC/SAU luat 'LAY THEM CELL LON >=10%' cho 1 tram cu
    the - "truoc" tai tao bang monkeypatch NGUONG_CELL_LON=1.01 (xem dac ta
    day du o _do_hieu_ung_luat_10pct_toan_bo_na09())."""
    import domain.services.ho_cell_selector as hcs
    from domain.services.ho_cell_selector import KhongCoDuLieuHoError

    print("\n" + "=" * 78)
    print(f"MUC 1 - So sanh A/B TRUOC/SAU luat 10% - tram {x_enb} ({nhan})")
    x_info = tram_theo_enb.get(x_enb)
    if x_info is None or x_info["lat"] is None:
        print(f"  DUNG: tram {x_enb} khong co trong bang tram hoac khong co toa do.")
        return

    x_diem = TramDiem(tram_id=str(x_enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
    x_la_dung_chung = phan_loai.get(str(x_enb)) == TOA_DO_DUNG_CHUNG
    ung_vien = [d for d in tram_diem_list if d.tram_id != str(x_enb)]
    l1_l2 = phan_lop_delaunay(x_diem, ung_vien, phan_loai)
    ho_rows = _ho_rows_cho_tram(nhom, x_enb)
    if not ho_rows:
        print(f"  DUNG: tram {x_enb} khong co du lieu HO.")
        return

    def _chay() -> tuple[int, int] | None:
        try:
            kq = chon_cell_cr(
                str(x_enb), ho_rows, l1_l2, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=x_la_dung_chung,
            )
        except KhongCoDuLieuHoError:
            return None
        return len(kq.a), len(kq.b)

    sau = _chay()
    nguong_cu = hcs.NGUONG_CELL_LON
    hcs.NGUONG_CELL_LON = 1.01
    try:
        truoc = _chay()
    finally:
        hcs.NGUONG_CELL_LON = nguong_cu

    print(f"  TRUOC (luat cu, khong lay them cell 10%): A={truoc[0] if truoc else 'N/A'} B={truoc[1] if truoc else 'N/A'}")
    print(f"  SAU   (luat moi, co lay them cell >=10%): A={sau[0] if sau else 'N/A'} B={sau[1] if sau else 'N/A'}")


def _do_hieu_ung_luat_10pct_toan_bo_na09(nhom: dict, thong_tin_dich: dict, dn_map: dict) -> None:
    """THEM 10/10/2026 (yeu cau truc tiep user) - do % sector CO THEM cell nho
    luat "LAY THEM CELL LON >=10%" (xem domain/services/ho_cell_selector.py)
    tren TOAN BO NA09 (KHONG lay mau 300 nhu MUC 2 - do nay CHI can dem so cell
    chon/sector, KHONG can L1/L2/Delaunay nen chay duoc tren het, nhanh).

    So sanh BANG CACH tat luat (NGUONG_CELL_LON=1.01, nguong > 100% -> khong
    cell nao vuot qua duoc buoc cong-don -> tai tao DUNG hanh vi CU) roi chay
    lai chon_cell_cr() - monkeypatch module-level constant, KHONG sua ham.
    l1_l2=[]/x_la_toa_do_dung_chung=False: AN TOAN cho do nay vi quan_he_day_du
    (nguon dem o day) duoc xay TRUC TIEP tu ung_vien_theo_sector, KHONG phu
    thuoc l1_l2/dung_chung (2 tham so do CHI anh huong layer/gating Z, khong
    anh huong CO duoc chon vao sector hay khong)."""
    import domain.services.ho_cell_selector as hcs
    from domain.services.ho_cell_selector import KhongCoDuLieuHoError

    print("\n" + "=" * 78)
    print("MUC 3 - Hieu ung luat 'LAY THEM CELL LON >=10%' tren TOAN BO NA09")

    tong_sector = 0
    so_sector_them = 0
    tong_cell_them = 0

    for enb in nhom:
        ho_rows = _ho_rows_cho_tram(nhom, enb)
        if not ho_rows:
            continue
        try:
            kq_moi = chon_cell_cr(str(enb), ho_rows, [], thong_tin_dich, dn_map)
        except KhongCoDuLieuHoError:
            continue

        nguong_cu = hcs.NGUONG_CELL_LON
        hcs.NGUONG_CELL_LON = 1.01
        try:
            kq_cu = chon_cell_cr(str(enb), ho_rows, [], thong_tin_dich, dn_map)
        except KhongCoDuLieuHoError:
            continue
        finally:
            hcs.NGUONG_CELL_LON = nguong_cu

        dem_moi: dict[int, int] = {}
        dem_cu: dict[int, int] = {}
        for q in kq_moi.quan_he_day_du:
            dem_moi[q.sector] = dem_moi.get(q.sector, 0) + 1
        for q in kq_cu.quan_he_day_du:
            dem_cu[q.sector] = dem_cu.get(q.sector, 0) + 1

        for sector, so_moi in dem_moi.items():
            so_cu = dem_cu.get(sector, 0)
            tong_sector += 1
            if so_moi > so_cu:
                so_sector_them += 1
                tong_cell_them += so_moi - so_cu

    print(f"  Tong so sector da xet (co du lieu HO): {tong_sector:,}")
    if tong_sector:
        print(f"  So sector co THEM cell nho luat 10%: {so_sector_them:,} ({100.0*so_sector_them/tong_sector:.1f}%)")
    if so_sector_them:
        print(f"  So cell them trung binh (tren CAC sector CO them): {tong_cell_them/so_sector_them:.2f}")
        print(f"  Tong so cell them (toan NA09): {tong_cell_them:,}")


def _dem_loai_tram(tram_theo_enb: dict, chi_ma_tinh: str | None = None) -> dict[str, int]:
    """Dem so tram theo nhom loai_tram (MACRO/IBS/SMALL_CELL/KHAC) tren TOAN
    BO tram_theo_enb (nap_toan_bo_tram() da nap het CA NUOC, khong rieng NA09)
    - loc theo ma_tinh neu chi_ma_tinh != None. CHI DOC, muc 3d cua bao cao
    PHAN LOAI TRAM + DO ANH HUONG (11-12/10/2026, yeu cau truc tiep user)."""
    dem: dict[str, int] = {}
    for info in tram_theo_enb.values():
        if chi_ma_tinh is not None and info["ma_tinh"] != chi_ma_tinh:
            continue
        nhom = loai_tram_tu_ten_tram(info["tram_name"])
        dem[nhom] = dem.get(nhom, 0) + 1
    return dem


def _phan_loai_tram_toan_quoc_va_hni(tram_theo_enb: dict) -> None:
    print("\n" + "=" * 78)
    print("MUC 3d - So tram theo loai_tram (toan quoc va rieng HNI)")

    dem_toan_quoc = _dem_loai_tram(tram_theo_enb)
    dem_hni = _dem_loai_tram(tram_theo_enb, chi_ma_tinh="HNI")
    print(f"  Toan quoc ({sum(dem_toan_quoc.values()):,} tram): {dem_toan_quoc}")
    print(f"  HNI ({sum(dem_hni.values()):,} tram): {dem_hni}")

    vi_du_khac = [
        info["tram_name"] for info in tram_theo_enb.values()
        if loai_tram_tu_ten_tram(info["tram_name"]) == "KHAC"
    ][:10]
    print(f"  10 vi du KHAC: {vi_du_khac}")


def _phan_loai_tram_va_do_anh_huong_mau_300(
    nhom: dict, tram_theo_enb: dict, tram_diem_list: list, thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str],
) -> None:
    """PHAN LOAI TRAM + DO ANH HUONG (11-12/10/2026, yeu cau truc tiep user) -
    muc 3a/3b/3c cua bao cao. Quyet dinh 11-12/10/2026: GIU NGUYEN cach tinh
    L1/L2 that (dung CHO SAN XUAT) - "cach 2" (chi macro) o day CHI de DO MUC
    DO ANH HUONG neu sau nay quyet dinh ap dung, KHONG thay doi code san xuat.

    Dung LAI mau 300 tram/seed 42 giong MUC 2 (_mau_300_tram_na09) de cac con
    so so sanh duoc voi nhau."""
    print("\n" + "=" * 78)
    print(f"MUC 3a/3b/3c - Phan loai tram + do anh huong, mau {SO_MAU} tram NA09, seed={RANDOM_SEED}")

    from domain.services.ho_cell_selector import KhongCoDuLieuHoError

    ung_vien = [
        enb for enb in nhom
        if enb in tram_theo_enb and tram_theo_enb[enb]["ma_tinh"] == "HNI" and tram_theo_enb[enb]["lat"] is not None
    ]
    rng = random.Random(RANDOM_SEED)
    mau = rng.sample(ung_vien, min(SO_MAU, len(ung_vien)))

    # --- 3a: thanh phan L1/L2 theo loai (CACH 1 - thuat toan HIEN TAI, dung
    # TOAN BO tram lam ung vien, KHONG loc loai) ---
    dem_l1: dict[str, int] = {}
    dem_l2: dict[str, int] = {}

    # --- 3b/3c: so sanh CACH 1 (hien tai) vs CACH 2 (CHI macro lam ung vien
    # Delaunay/L1/L2) ---
    so_tram_xet = 0
    so_tram_b_khac = 0
    tong_cell_them = 0  # co o CACH 2 nhung KHONG co o CACH 1
    tong_cell_mat = 0   # co o CACH 1 nhung KHONG co o CACH 2
    vi_du_khac_b: list[dict] = []
    so_a_cach1 = so_z_cach1 = 0
    so_a_cach2 = so_z_cach2 = 0

    for enb in mau:
        x_info = tram_theo_enb[enb]
        if phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG:
            continue  # X CRAN: l1_l2 luon [] o CA 2 cach, khong co gi de so sanh (giong MUC 2)
        ho_rows = _ho_rows_cho_tram(nhom, enb)
        if not ho_rows:
            continue

        x_diem = TramDiem(tram_id=str(enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
        ung_vien_diem_goc = [d for d in tram_diem_list if d.tram_id != str(enb)]
        l1_l2_cach1 = phan_lop_delaunay(x_diem, ung_vien_diem_goc, phan_loai)
        for t in l1_l2_cach1:
            nhom_t = loai_tram_tu_ten_tram(t.tram_name)
            if t.layer == "L1":
                dem_l1[nhom_t] = dem_l1.get(nhom_t, 0) + 1
            else:
                dem_l2[nhom_t] = dem_l2.get(nhom_t, 0) + 1

        # CACH 2: loc ung vien CHI con tram MACRO truoc khi dua vao Delaunay -
        # X van la chinh no (KHONG doi, chi gioi han TAP UNG VIEN lam L1/L2).
        ung_vien_diem_macro = [d for d in ung_vien_diem_goc if loai_tram_tu_ten_tram(d.tram_name) == NHOM_MACRO]
        l1_l2_cach2 = phan_lop_delaunay(x_diem, ung_vien_diem_macro, phan_loai)

        try:
            kq1 = chon_cell_cr(
                str(enb), ho_rows, l1_l2_cach1, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=False,
            )
            kq2 = chon_cell_cr(
                str(enb), ho_rows, l1_l2_cach2, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=False,
            )
        except KhongCoDuLieuHoError:
            continue
        so_tram_xet += 1

        so_a_cach1 += len(kq1.a); so_z_cach1 += sum(1 for c in kq1.a if c.layer == "Z")
        so_a_cach2 += len(kq2.a); so_z_cach2 += sum(1 for c in kq2.a if c.layer == "Z")

        b1 = {(c.target_enb, c.target_lcr) for c in kq1.b}
        b2 = {(c.target_enb, c.target_lcr) for c in kq2.b}
        if b1 != b2:
            so_tram_b_khac += 1
            them = b2 - b1
            mat = b1 - b2
            tong_cell_them += len(them)
            tong_cell_mat += len(mat)
            if len(vi_du_khac_b) < 5:
                ten_theo_khoa = {(c.target_enb, c.target_lcr): c.cell_name for c in kq1.b}
                ten_theo_khoa.update({(c.target_enb, c.target_lcr): c.cell_name for c in kq2.b})
                vi_du_khac_b.append({
                    "tram": x_info["tram_name"],
                    "them": [ten_theo_khoa.get(k) or k for k in them],
                    "mat": [ten_theo_khoa.get(k) or k for k in mat],
                })

    print(f"\n3a. Thanh phan L1 theo loai (tong {sum(dem_l1.values()):,}): {dem_l1}")
    print(f"    Thanh phan L2 theo loai (tong {sum(dem_l2.values()):,}): {dem_l2}")

    print(f"\n3b. So tram da xet (ca 2 cach deu co du lieu): {so_tram_xet}")
    print(f"    So tram co danh sach B KHAC nhau giua 2 cach: {so_tram_b_khac} ({100.0*so_tram_b_khac/so_tram_xet:.1f}%)" if so_tram_xet else "")
    print(f"    Tong cell B THEM (co o cach-2-chi-macro, mat o cach 1): {tong_cell_them}")
    print(f"    Tong cell B MAT (co o cach 1, mat o cach-2-chi-macro): {tong_cell_mat}")
    print("    5 vi du tram co B khac nhau (them/mat):")
    for vd in vi_du_khac_b:
        print(f"      {vd['tram']}: THEM={vd['them']} MAT={vd['mat']}")

    print(f"\n3c. % cell A roi vao Z - CACH 1 (hien tai): {so_z_cach1}/{so_a_cach1} ({100.0*so_z_cach1/so_a_cach1:.1f}%)" if so_a_cach1 else "")
    print(f"    % cell A roi vao Z - CACH 2 (chi macro):  {so_z_cach2}/{so_a_cach2} ({100.0*so_z_cach2/so_a_cach2:.1f}%)" if so_a_cach2 else "")


def _b_hop_le_khong_tinh_layer(c) -> bool:
    """DIEU KIEN hop_le_b CU (TRUOC 12/10/2026, KHONG co "layer not in (IBS,
    SMALL_CELL)") - dung de dem CHINH XAC so cell BI LOAI KHOI B boi RIENG
    dieu kien layer IBS/SMALL_CELL moi them (1 cell thoa dieu kien nay VA co
    layer=="IBS" chinh la 1 cell bi loai KHOI B boi luat moi - truoc day no
    se duoc xep hang binh thuong). KHONG dung lam nguon that - BAN SAO doc de
    do anh huong, xem _do_lai_ibs_macro_mau_300()."""
    return c.vendor == "NOKIA" and not c.can_ghep_ten and band_tu_lncel(f"LNCEL-{c.target_lcr}") is not None


def _do_lai_ibs_macro_mau_300(
    nhom: dict, tram_theo_enb: dict, tram_diem_list: list, thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str],
) -> None:
    """DO LAI (12/10/2026, yeu cau truc tiep user) - hieu ung 2 quyet dinh
    CUNG luc: (2) IBS khong chay CR (loai khoi B), (3) L1/L2 chi tinh voi
    tram MACRO+KHAC. Dung LAI mau 300/seed 42 (giong MUC 2/MUC 3a-c) de so
    sanh duoc.

    PHUONG PHAP do "so tram B thay doi so voi ban dang deploy" (tach rieng 2
    hieu ung, KHONG the gop lam 1 phep so sanh duy nhat vi hop_le_b moi (loai
    IBS) la DIEU KIEN CUNG trong chon_cell_cr(), khong con tham so de "tat" ve
    hanh vi cu nhu NGUONG_CELL_LON/monkeypatch o MUC 3 khac):
      - Hieu ung (3) CO LAP RIENG: so sanh B (dung LUAT MOI, ke ca loai IBS)
        giua l1_l2 MOI (phan_lop_delaunay that, da co san macro+khac) va l1_l2
        CU (monkeypatch tam thoi loai_tram_tu_ten_tram trong module
        ho_delaunay de LUON tra NHOM_MACRO - vo hieu hoa bo loc macro+khac VA
        guard X-la-IBS, tai hien DUNG hanh vi pipeline TRUOC quyet dinh nay).
      - Hieu ung (2) CO LAP RIENG: dem TRUC TIEP so cell layer=="IBS" DU DIEU
        KIEN khac cua hop_le_b (_b_hop_le_khong_tinh_layer) tren ket qua A
        MOI - chinh la so cell IBS bi loai KHOI B boi luat moi, KHONG phu
        thuoc l1_l2 cu/moi."""
    print("\n" + "=" * 78)
    print(f"DO LAI - IBS khong chay CR + L1/L2 chi MACRO/KHAC, mau {SO_MAU} tram NA09, seed={RANDOM_SEED}")

    import domain.services.ho_delaunay as hd
    from domain.services.ho_cell_selector import KhongCoDuLieuHoError

    ung_vien = [
        enb for enb in nhom
        if enb in tram_theo_enb and tram_theo_enb[enb]["ma_tinh"] == "HNI" and tram_theo_enb[enb]["lat"] is not None
    ]
    rng = random.Random(RANDOM_SEED)
    mau = rng.sample(ung_vien, min(SO_MAU, len(ung_vien)))

    so_cell_a_theo_layer = {"L1": 0, "L2": 0, "Z": 0, "KHONG_XAC_DINH": 0, "IBS": 0, "SMALL_CELL": 0}
    so_x_dung_chung = so_x_ibs = so_x_tin_cay = so_khong_du_lieu = so_x_ho_di_xa = 0
    tong_cell_ibs_bi_loai_khoi_b = 0
    so_tram_xet_b = so_tram_b_khac_macro = 0

    for enb in mau:
        x_info = tram_theo_enb[enb]
        x_dung_chung = phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG
        x_ibs = loai_tram_tu_ten_tram(x_info["tram_name"]) == NHOM_IBS
        if x_dung_chung:
            so_x_dung_chung += 1
            continue  # giong MUC 2 - X CRAN khong co y nghia thong ke L1/L2/layer
        if x_ibs:
            so_x_ibs += 1
            continue  # tuong tu - X IBS cung l1_l2=[] "gia tao", tach rieng khoi thong ke layer

        so_x_tin_cay += 1
        ho_rows = _ho_rows_cho_tram(nhom, enb)
        if not ho_rows:
            continue

        x_diem = TramDiem(tram_id=str(enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
        ung_vien_diem = [d for d in tram_diem_list if d.tram_id != str(enb)]
        l1_l2_moi = phan_lop_delaunay(x_diem, ung_vien_diem, phan_loai)

        try:
            kq_moi = chon_cell_cr(
                str(enb), ho_rows, l1_l2_moi, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=False, x_la_ibs=False,
            )
        except KhongCoDuLieuHoError:
            so_khong_du_lieu += 1
            continue

        if kq_moi.ho_di_xa_x:
            so_x_ho_di_xa += 1
        for c in kq_moi.a:
            so_cell_a_theo_layer[c.layer] += 1
            if c.layer == "IBS" and _b_hop_le_khong_tinh_layer(c):
                tong_cell_ibs_bi_loai_khoi_b += 1

        # Hieu ung (3) CO LAP: l1_l2 CU qua monkeypatch (vo hieu bo loc macro+khac).
        nguyen_ham = hd.loai_tram_tu_ten_tram
        hd.loai_tram_tu_ten_tram = lambda ten: NHOM_MACRO  # noqa: E731 - script doc, khong phai production
        try:
            l1_l2_cu = phan_lop_delaunay(x_diem, ung_vien_diem, phan_loai)
        finally:
            hd.loai_tram_tu_ten_tram = nguyen_ham
        try:
            kq_cu = chon_cell_cr(
                str(enb), ho_rows, l1_l2_cu, thong_tin_dich, dn_map,
                x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=False, x_la_ibs=False,
            )
        except KhongCoDuLieuHoError:
            continue
        so_tram_xet_b += 1
        if {(c.target_enb, c.target_lcr) for c in kq_moi.b} != {(c.target_enb, c.target_lcr) for c in kq_cu.b}:
            so_tram_b_khac_macro += 1

    tong_cell_a = sum(so_cell_a_theo_layer.values())
    print(f"\n  So tram X la TOA_DO_DUNG_CHUNG (loai khoi thong ke layer/HO_DI_XA): {so_x_dung_chung}/{len(mau)}")
    print(f"  So tram X la IBS (loai khoi thong ke layer/HO_DI_XA, GIONG CRAN): {so_x_ibs}/{len(mau)}")
    print(f"  Con lai {so_x_tin_cay} tram X TIN_CAY (khong CRAN, khong IBS) - thong ke duoi day CHI tren nhom nay")
    print(f"  So tram KHONG co du lieu HO: {so_khong_du_lieu}/{so_x_tin_cay}")

    print(f"\n  % cell A theo layer (tong {tong_cell_a:,}):")
    for layer, dem in so_cell_a_theo_layer.items():
        print(f"    {layer}: {dem:,} ({100.0*dem/tong_cell_a:.1f}%)" if tong_cell_a else f"    {layer}: 0")

    so_x_du_du_lieu = so_x_tin_cay - so_khong_du_lieu
    print(f"\n  % tram X (TIN_CAY, du du lieu) duoc gan HO_DI_XA: {so_x_ho_di_xa}/{so_x_du_du_lieu} ({100.0*so_x_ho_di_xa/so_x_du_du_lieu:.1f}%)" if so_x_du_du_lieu else "")

    print(f"\n  So cell IBS bi loai khoi B (du dieu kien khac cua hop_le_b, CHI vuong layer IBS): {tong_cell_ibs_bi_loai_khoi_b:,}")

    print(f"\n  [Hieu ung L1/L2 chi MACRO+KHAC, co lap rieng khoi hieu ung IBS-khoi-B]")
    print(f"  So tram da xet (ca 2 kieu l1_l2 deu co du lieu): {so_tram_xet_b}")
    print(f"  So tram co B thay doi DO l1_l2 macro+khac (so voi ban dang deploy, l1_l2 KHONG loc loai): {so_tram_b_khac_macro} ({100.0*so_tram_b_khac_macro/so_tram_xet_b:.1f}%)" if so_tram_xet_b else "")


def _in_b_tram(x_enb: int, nhan: str, nhom: dict, tram_theo_enb: dict, tram_diem_list: list, thong_tin_dich: dict, dn_map: dict, phan_loai: dict[str, str]) -> None:
    print("\n" + "=" * 78)
    print(f"DO LAI - Danh sach B (luat moi) - tram {x_enb} ({nhan})")
    x_info = tram_theo_enb.get(x_enb)
    x_dung_chung = phan_loai.get(str(x_enb)) == TOA_DO_DUNG_CHUNG
    x_ibs = loai_tram_tu_ten_tram(x_info["tram_name"]) == NHOM_IBS
    x_diem = TramDiem(tram_id=str(x_enb), tram_name=x_info["tram_name"], lat=x_info["lat"], lon=x_info["lon"])
    ung_vien_diem = [d for d in tram_diem_list if d.tram_id != str(x_enb)]
    l1_l2 = [] if (x_dung_chung or x_ibs) else phan_lop_delaunay(x_diem, ung_vien_diem, phan_loai)
    ho_rows = _ho_rows_cho_tram(nhom, x_enb)
    from domain.services.ho_cell_selector import KhongCoDuLieuHoError
    try:
        kq = chon_cell_cr(
            str(x_enb), ho_rows, l1_l2, thong_tin_dich, dn_map,
            x_lat=x_info["lat"], x_lon=x_info["lon"], x_la_toa_do_dung_chung=x_dung_chung, x_la_ibs=x_ibs,
        )
    except KhongCoDuLieuHoError as exc:
        print(f"  DUNG: {exc}")
        return
    print(f"  B ({len(kq.b)} cell):")
    for c in sorted(kq.b, key=lambda c: (c.sector, c.rank_b)):
        print(f"    sector={c.sector} rank={c.rank_b:<10} {c.cell_name} layer={c.layer}")


async def main():
    path = _tim_file_csv()
    print(f"File CSV: {path}")
    ds = doc_toan_bo_csv(path)
    print(f"Tong so dong: {ds['tong_dong']:,}\n")

    print("Dang tai bang tram + cell_infor tu DB...")
    tram_theo_enb = await nap_toan_bo_tram()
    dn_map = await nap_cell_infor_dn_map()
    nhom = _nhom_theo_tram(ds["AGG"])
    tram_diem_list = _tram_diem_list(tram_theo_enb)
    # phan_loai_toa_do() goi 1 LAN cho TOAN BO tap tram (khong phu thuoc X
    # dang xet) - xem domain/services/ho_delaunay.py::phan_loai_toa_do().
    phan_loai = phan_loai_toa_do(tram_diem_list)
    thong_tin_dich = _thong_tin_tram_dich(tram_theo_enb, phan_loai)

    _in_tram(X_TEST_ID, "noi thanh - Cau Giay", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    # 2 tram THEM (yeu cau truc tiep user, muc 5c) - 1 noi thanh, 1 ngoai
    # thanh. 117713 (4G-CGY025B-HNI, Cau Giay) - da xac nhan CUNG site/
    # CUNG ma_csht voi 117703 o 1 yeu cau truoc (khu vuc noi thanh dong duc).
    # 113040 (4G-BVI044M-HNI, Ba Vi) - phat hien qua scripts/dieu_tra_toa_do_nghi_sai.py
    # truoc do: trung_vi_L1=2,57km (thua han so noi thanh <0,5km) - dai dien
    # vung ngoai thanh/nong thon.
    _in_tram(117713, "noi thanh - Cau Giay", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _in_tram(113040, "ngoai thanh - Ba Vi", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _mau_300_tram_na09(nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _do_hieu_ung_luat_10pct_toan_bo_na09(nhom, thong_tin_dich, dn_map)
    _so_sanh_a_b_truoc_sau_luat_10pct(117903, "noi thanh - Cau Giay", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _so_sanh_a_b_truoc_sau_luat_10pct(117713, "CRAN - TOA_DO_DUNG_CHUNG", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _phan_loai_tram_toan_quoc_va_hni(tram_theo_enb)
    _phan_loai_tram_va_do_anh_huong_mau_300(nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _do_lai_ibs_macro_mau_300(nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _in_b_tram(117903, "noi thanh - Cau Giay", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)
    _in_b_tram(117713, "CRAN - TOA_DO_DUNG_CHUNG", nhom, tram_theo_enb, tram_diem_list, thong_tin_dich, dn_map, phan_loai)


if __name__ == "__main__":
    asyncio.run(main())
