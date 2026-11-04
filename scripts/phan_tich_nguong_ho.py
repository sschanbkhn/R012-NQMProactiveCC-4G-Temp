"""
PHAN TICH NGUONG - CHI DOC, KHONG SUA code he thong, KHONG ghi DB.

Muc dich: truoc khi code thuat toan B (thay CDS /cell/neighbors bang report
HO that - xem scripts/spike_ho_neighbor.py), DO tren du lieu THAT de CHOT cac
nguong dang la GIA DINH (80% / tran 10 / bo <1% / 20%+SR95% / ALPHA / 15km).

Tai dung TRUC TIEP (KHONG viet lai) tu scripts/spike_ho_neighbor.py:
  - _DN_RE: regex tach (enb, lncel) tu cot DN.
  - _sector_tu_lncel(): sector = chu so cuoi LNCEL ID nguon.
  - _LNCEL_CHAY_CR_RE: luat CR hien tai (chi lcr ^[13][0-9]$).
  - Cong thuc giai ma eci_id (enb = eci_id // 256, lcr = eci_id % 256) da
    duoc KIEM CHUNG trong spike_ho_neighbor.py (143.112 dong intra-eNB tren
    toan file, 5 vi du khop 100%) - KHONG lam lai o day.

Chay (PYTHONPATH tu goc repo):
    PYTHONPATH=. ./venv/Scripts/python.exe scripts/phan_tich_nguong_ho.py

=== GIA DINH/DIEN GIAI rieng cho script nay (ngoai cac gia dinh da neu o
spike_ho_neighbor.py) - BAT BUOC doc truoc khi tin ket qua ===

G1. "danh sach A" (muc 5, toan cuc): tap TOAN BO cell dich (enb,lcr) PHAN
    BIET xuat hien o BAT KY dau trong file SAU loc (khong intra, attempt>0) -
    khong gioi han theo 1 tram nguon nao.
G2. "danh sach A" (muc 3, theo TUNG tram nguon mau): gop theo TRAM DICH (cong
    attempt moi sector, GIONG Buoc 9 cua spike_ho_neighbor.py) - danh sach cac
    tram dich kem % tong cua rieng tram nguon do.
G3. "NA09" = tinh HNI (xac nhan qua .env.example + oss_router_env.py: route
    "HNI|NOKIA" -> instance "NA09"). cell_infor KHONG co cot "netact" (da
    kiem tra that truoc khi viet script: 10 cot, khong cot nao ten nhu vay) -
    nen muc 6 dung nhanh "theo tinh NA09" (tram.ma_tinh == "HNI").
G4. Muc 2b "cell top 2 moi sector": ap DUNG thuat toan hien tai (xep theo
    attempt, loc band ^[13][0-9]$, toi da 2/sector, dedup xuyen sector - sector
    nho hon giu quyen) CHO TUNG tram nguon rieng, roi GOP SR cua moi cell duoc
    chon lai thanh 1 phan phoi chung.
G5. Delaunay/alpha-shape (muc 3): KHONG co dinh nghia "ALPHA" chuan tu user.
    Dung dinh nghia RO RANG, don gian: voi tram nguon dang xet, lay TOAN BO
    tram (ca nuoc) trong ban kinh 15km (khoang cach day cung qua toa do 3D
    tren mat cau, xap xi khoang cach great-circle - sai so khong dang ke o
    thang 15km), chieu phang ve he toa do km cuc bo (xap xi equirectangular
    quanh tram nguon), tam giac hoa Delaunay tren tap diem cuc bo do, roi XOA
    canh DAI HON ALPHA x (trung vi khoang cach lang gieng gan nhat trong tap
    cuc bo) - day la "alpha-shape kieu nguong canh", KHONG phai cong thuc
    alpha-shape chuan theo ban kinh duong tron ngoai tiep. L1 = tram noi TRUC
    TIEP voi tram nguon trong do thi da xoa canh. L2 = tram noi voi 1 tram L1
    (khong phai L1, khong phai chinh no). Z = tat ca con lai (ke ca tram NGOAI
    pham vi 15km).
G6. Tap 300 tram nguon mau: chi lay TRONG so tram nguon CO it nhat 1 dong hop
    le (khong intra, attempt>0, sector doc duoc) VA CO toa do trong bang tram.
    Random seed CO DINH = 42 de tai lap duoc.
G7. Muc 7 (doi chieu CR cu): file CSV HO CHI co 1 moc PERIOD_START_TIME DUY
    NHAT (28/09/2026, da kiem tra that) trong khi cac session CR cu chay tu
    thang 7-10/2026 - nghia la dang "replay" thuat toan B tren 1 LAT CAT HO
    SAU NAY so voi thoi diem CR thuc chay, KHONG PHAI du lieu HO cung thoi
    diem. Day la GIOI HAN THAT cua phep so sanh nay, khong phai loi code -
    ghi ro trong output.
G8. Ten cell THAT cua 1 (enb,lcr) duoc tra cuu qua bang cell_infor (dn_lncel
    dung CHUNG dinh dang DN voi file HO) - KHONG doan tu ten tram, vi muc 5
    CHINH LA de kiem tra xem doan co dang tin khong.
"""

import asyncio
import csv
import glob
import os
import random
import re
import sys
from collections import defaultdict
from math import asin, cos, radians, sin, sqrt

import numpy as np
from scipy.spatial import Delaunay, cKDTree
from sqlalchemy import select, text

from infrastructure.db import AsyncSessionLocal
from models.tram import Tram as TramModel
from scripts.spike_ho_neighbor import _DN_RE, _LNCEL_CHAY_CR_RE, _sector_tu_lncel

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "adapters", "netact", "data_test")
EARTH_R_KM = 6371.0088
SO_MAU_DELAUNAY = 300
BAN_KINH_KM = 15.0
RANDOM_SEED = 42


def _tim_file_csv() -> str:
    ung_vien = [p for p in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))) if "eci_id" in open(p, encoding="utf-8-sig", errors="ignore").readline()]
    if len(ung_vien) != 1:
        print(f"DUNG: can DUNG 1 file CSV co cot eci_id trong {DATA_DIR}, tim thay {len(ung_vien)}.")
        sys.exit(1)
    return ung_vien[0]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * asin(sqrt(a))


# ============================================================================
# PASS 1 DUY NHAT qua toan bo CSV (~3 trieu dong) - gom du lieu cho MOI muc
# (1,2,4,5,6) trong 1 lan doc, tranh doc lai file nhieu lan.
# ============================================================================
def doc_toan_bo_csv(path: str):
    AGG: dict[tuple[int, int], dict[tuple[int, int], dict]] = defaultdict(lambda: defaultdict(lambda: {"attempt": 0, "sr_x_att": 0.0, "sr_w": 0}))
    sr_moi_cap: list[float] = []
    global_a: set[tuple[int, int]] = set()
    lncel_do_dai_dem: dict[int, int] = defaultdict(int)
    nguon_enb_co_hop_le: set[int] = set()
    nguon_enb_bat_ky: set[int] = set()  # xuat hien O DAU (ke ca intra/attempt=0/sector la) - muc 6

    tong_dong = 0
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        idx = {ten: i for i, ten in enumerate(header)}
        i_eci, i_dn = idx["eci_id"], idx["DN"]
        i_att, i_sr = idx["Inter eNB HO prep att neigh"], idx["Adj Inter eNB HO SR"]

        for row in reader:
            tong_dong += 1
            if tong_dong % 500_000 == 0:
                print(f"  ... da doc {tong_dong:,} dong", file=sys.stderr)
            dn = row[i_dn]
            m = _DN_RE.search(dn)
            if not m:
                continue
            src_enb = int(m.group(1))
            src_lncel_str = m.group(2)
            nguon_enb_bat_ky.add(src_enb)
            lncel_do_dai_dem[len(src_lncel_str)] += 1

            eci_raw = row[i_eci]
            if not eci_raw:
                continue
            eci = int(eci_raw)
            target_enb, target_lcr = eci // 256, eci % 256
            if target_enb == src_enb:
                continue  # bo intra-eNB (muc 1 dac ta BUOC 3 cua spike)

            att_raw = row[i_att]
            att = int(att_raw) if att_raw else 0
            if att == 0:
                continue  # bo attempt=0

            sr_raw = row[i_sr]
            sr = float(sr_raw) if sr_raw else None
            if sr is not None:
                sr_moi_cap.append(sr)

            global_a.add((target_enb, target_lcr))

            if len(src_lncel_str) != 2:
                continue  # KHONG tin sector (xem muc 4 - dang MBF_ 3 chu so)
            sector = _sector_tu_lncel(int(src_lncel_str))
            nguon_enb_co_hop_le.add(src_enb)
            g = AGG[(src_enb, sector)][(target_enb, target_lcr)]
            g["attempt"] += att
            if sr is not None:
                g["sr_x_att"] += sr * att
                g["sr_w"] += att

    return {
        "tong_dong": tong_dong,
        "AGG": AGG,
        "sr_moi_cap": sr_moi_cap,
        "global_a": global_a,
        "lncel_do_dai_dem": lncel_do_dai_dem,
        "nguon_enb_co_hop_le": nguon_enb_co_hop_le,
        "nguon_enb_bat_ky": nguon_enb_bat_ky,
    }


# ============================================================================
# MUC 1 - nguong 80% / tran 10,15,20 / bo <1%
# ============================================================================
def muc_1(AGG: dict) -> dict:
    so_cell_can_80: list[int] = []
    cham_tran = {10: 0, 15: 0, 20: 0}
    phu_tai_tran = {10: [], 15: [], 20: []}
    tong_attempt_toan_cuc = 0
    tong_attempt_bo_di = 0

    for key, cands in AGG.items():
        xep = sorted(cands.values(), key=lambda v: -v["attempt"])
        tong = sum(v["attempt"] for v in xep)
        if tong == 0:
            continue
        tong_attempt_toan_cuc += tong

        # bo cell < 1% sector nay
        giu_lai = [v for v in xep if v["attempt"] / tong >= 0.01]
        bo_di = tong - sum(v["attempt"] for v in giu_lai)
        tong_attempt_bo_di += bo_di
        tong_sau_loc = sum(v["attempt"] for v in giu_lai)
        if tong_sau_loc == 0:
            continue

        # so cell can de dat 80% TREN TAP DA LOC <1%
        cong_don = 0
        so_can = len(giu_lai)
        for i, v in enumerate(giu_lai, start=1):
            cong_don += v["attempt"]
            if cong_don / tong_sau_loc >= 0.80:
                so_can = i
                break
        so_cell_can_80.append(so_can)

        for tran in (10, 15, 20):
            if so_can > tran:
                cham_tran[tran] += 1
            phu = sum(v["attempt"] for v in giu_lai[:tran]) / tong_sau_loc
            phu_tai_tran[tran].append(phu)

    arr = np.array(so_cell_can_80)
    so_sector = len(so_cell_can_80)
    return {
        "so_sector": so_sector,
        "trung_vi": float(np.median(arr)) if so_sector else None,
        "p90": float(np.percentile(arr, 90)) if so_sector else None,
        "p95": float(np.percentile(arr, 95)) if so_sector else None,
        "max": int(arr.max()) if so_sector else None,
        "pct_cham_tran": {t: 100.0 * cham_tran[t] / so_sector for t in (10, 15, 20)} if so_sector else {},
        "phu_trung_binh_tai_tran": {t: 100.0 * float(np.mean(phu_tai_tran[t])) for t in (10, 15, 20)} if so_sector else {},
        "pct_ho_mat_do_bo_1pct_global": 100.0 * tong_attempt_bo_di / tong_attempt_toan_cuc if tong_attempt_toan_cuc else None,
    }


# ============================================================================
# MUC 2 - phan phoi SR
# ============================================================================
def muc_2(AGG: dict, sr_moi_cap: list[float]) -> dict:
    def _percentiles(arr):
        if len(arr) == 0:
            return None
        a = np.array(arr)
        return {
            "p1": float(np.percentile(a, 1)),
            "p5": float(np.percentile(a, 5)),
            "p10": float(np.percentile(a, 10)),
            "trung_vi": float(np.median(a)),
            "so_luong": len(a),
        }

    sr_top2: list[float] = []
    for src_enb, nhom_theo_sector in _nhom_theo_tram(AGG).items():
        da_chon: set[tuple[int, int]] = set()
        for sector in sorted(nhom_theo_sector):
            xep = sorted(nhom_theo_sector[sector].items(), key=lambda kv: -kv[1]["attempt"])
            so_da_chon = 0
            for (enb, lcr), v in xep:
                if so_da_chon >= 2:
                    break
                if (enb, lcr) in da_chon:
                    continue
                if not _LNCEL_CHAY_CR_RE.match(str(lcr)):
                    continue
                da_chon.add((enb, lcr))
                if v["sr_w"] > 0:
                    sr_top2.append(v["sr_x_att"] / v["sr_w"])
                so_da_chon += 1

    return {"moi_cap": _percentiles(sr_moi_cap), "top2_moi_sector": _percentiles(sr_top2)}


def _nhom_theo_tram(AGG: dict) -> dict[int, dict[int, dict]]:
    """(source_enb, sector) -> candidates  =>  source_enb -> {sector: candidates}"""
    ket_qua: dict[int, dict[int, dict]] = defaultdict(dict)
    for (src_enb, sector), cands in AGG.items():
        ket_qua[src_enb][sector] = cands
    return ket_qua


# ============================================================================
# MUC 4 - cac dang ID cell nguon
# ============================================================================
def muc_4(ds: dict) -> None:
    print("\nMUC 4 - Cac dang ID cell nguon (do dai chuoi LNCEL, tu DN):")
    tong = sum(ds["lncel_do_dai_dem"].values())
    for do_dai, dem in sorted(ds["lncel_do_dai_dem"].items()):
        print(f"  do_dai={do_dai}: {dem:,} dong ({100.0*dem/tong:.3f}%)")
    print(
        "  -> Da KIEM TRA THAT (truoc khi viet script): toan bo (560/560) cell nguon co ID 3 chu so\n"
        "     DEU co 'Source LNCEL name' dang 'MBF_...' (vd 'MBF_H2_BVI_BA_VI_5_M4BA') - KHONG dung\n"
        "     mau '4G-<site><loai><so>-<tinh>' chuan. Day la nhom cell KHAC (co the Huawei/femto hoac\n"
        "     thiet bi mang khac), DA bi loai khoi pipeline CR o noi khac trong he thong qua tien to\n"
        "     'MBF_' (xem domain/services/neighbor_cell_filter.py::filter_affected()).\n"
        "  => KET LUAN: dang 3 chu so (va bat ky do dai KHAC 2) lam sector bi DOC SAI neu ap dung mu\n"
        "     cong thuc %10 - script nay da LOAI cac dong co ID nguon KHONG dung 2 chu so khoi moi\n"
        "     phan tich theo sector (muc 1,2b,3,7)."
    )


# ============================================================================
# DB: tram (toa do + vendor + khu_vuc), cell_infor (enb,lcr) -> cell_name that
# ============================================================================
async def nap_toan_bo_tram() -> dict[int, dict]:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(TramModel))).scalars().all()
    ket_qua = {}
    for r in rows:
        try:
            enb = int(r.tram_id)
        except ValueError:
            continue
        ket_qua[enb] = {
            "tram_id": r.tram_id,
            "tram_name": r.tram_name,
            "ten_thiet_bi": r.ten_thiet_bi,
            "ma_tinh": r.ma_tinh,
            "lon": float(r.longitude) if r.longitude is not None else None,
            "lat": float(r.latitude) if r.latitude is not None else None,
        }
    return ket_qua


async def nap_cell_infor_dn_map() -> dict[tuple[int, int], str]:
    """(enb, lcr) -> cell_name THAT, tra cuu qua dn_lncel (CUNG dinh dang DN
    voi cot DN trong file HO) - KHONG doan tu ten tram (xem G8 dau file)."""
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(
            "SELECT dn_lncel, cell_name FROM system_nsn_nqmproactivecc.cell_infor"
        ))).all()
    ket_qua: dict[tuple[int, int], str] = {}
    for dn_lncel, cell_name in rows:
        m = _DN_RE.search(dn_lncel or "")
        if m:
            ket_qua[(int(m.group(1)), int(m.group(2)))] = cell_name
    return ket_qua


def chuan_hoa_vendor_str(ten_thiet_bi: str | None) -> str:
    from domain.value_objects.vendor import chuan_hoa_vendor
    return chuan_hoa_vendor(ten_thiet_bi).value


def khu_vuc_str(ma_tinh: str | None) -> str | None:
    from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh
    return khu_vuc_tu_ma_tinh(ma_tinh)


# ============================================================================
# MUC 5 - vendor cell dich
# ============================================================================
def muc_5(global_a: set[tuple[int, int]], tram_theo_enb: dict, dn_map: dict) -> None:
    print("\nMUC 5 - Vendor cell dich (danh sach A toan cuc):")
    khong_phai_nokia = []
    khong_ro = 0
    for (enb, lcr) in global_a:
        info = tram_theo_enb.get(enb)
        if info is None:
            khong_ro += 1
            continue
        vendor = chuan_hoa_vendor_str(info["ten_thiet_bi"])
        if vendor != "NOKIA":
            khong_phai_nokia.append((enb, lcr, info, vendor))

    tong = len(global_a)
    print(f"  Tong so cell PHAN BIET trong danh sach A: {tong:,}")
    print(f"  Khong ghep duoc tram (enb la): {khong_ro:,} ({100.0*khong_ro/tong:.2f}%)")
    print(f"  KHONG phai NOKIA: {len(khong_phai_nokia):,} ({100.0*len(khong_phai_nokia)/tong:.2f}%)")

    print("\n  10 vi du cell KHONG phai Nokia (enb, lcr, ten tram, vendor, ten GUESS, ten THAT tu cell_infor, KHOP?):")
    for enb, lcr, info, vendor in khong_phai_nokia[:10]:
        ten_tram = info["tram_name"]
        if "-" in ten_tram:
            prefix, suffix = ten_tram.rsplit("-", 1)
            doan = f"{prefix}{lcr:02d}-{suffix}"
        else:
            doan = "(khong tach duoc hau to '-XXX')"
        ten_that = dn_map.get((enb, lcr))
        khop = "KHOP" if ten_that == doan else ("KHONG KHOP" if ten_that else "KHONG CO trong cell_infor")
        print(f"    enb={enb:<8} lcr={lcr:<4} tram={ten_tram:<20} vendor={vendor:<9} doan={doan:<22} that={str(ten_that):<22} {khop}")


# ============================================================================
# MUC 6 - tram Nokia NA09 (= tinh HNI) khong co du lieu HO
# ============================================================================
def muc_6(tram_theo_enb: dict, nguon_enb_bat_ky: set[int]) -> None:
    print("\nMUC 6 - Tram Nokia thuoc NA09 (= tinh HNI, xem G3) KHONG co dong nao trong file HO:")
    hni_nokia = [enb for enb, info in tram_theo_enb.items() if info["ma_tinh"] == "HNI" and chuan_hoa_vendor_str(info["ten_thiet_bi"]) == "NOKIA"]
    khong_co_du_lieu = [enb for enb in hni_nokia if enb not in nguon_enb_bat_ky]
    print(f"  Tong tram Nokia thuoc HNI: {len(hni_nokia):,}")
    print(f"  KHONG co dong nao trong file HO (se gap KHONG_CO_DU_LIEU_HO neu dung thuat toan B): "
          f"{len(khong_co_du_lieu):,} ({100.0*len(khong_co_du_lieu)/len(hni_nokia):.2f}%)" if hni_nokia else "  (khong co tram Nokia/HNI nao)")


# ============================================================================
# MUC 3 - Delaunay / alpha-shape
# ============================================================================
def _xyz(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    x = EARTH_R_KM * np.cos(lat) * np.cos(lon)
    y = EARTH_R_KM * np.cos(lat) * np.sin(lon)
    z = EARTH_R_KM * np.sin(lat)
    return np.column_stack([x, y, z])


def _phan_loai_L1_L2(enb_nguon: int, idx_cuc_bo: np.ndarray, enb_list: np.ndarray, lat_arr: np.ndarray, lon_arr: np.ndarray, alpha: float) -> tuple[set[int], set[int]]:
    """Tra (L1, L2) la TAP enb (KHONG phai index). idx_cuc_bo la cac INDEX
    (vao enb_list/lat_arr/lon_arr) cua tram trong ban kinh 15km (DA GOM ca
    tram nguon)."""
    if len(idx_cuc_bo) < 4:
        return set(), set()  # khong du diem de tam giac hoa co y nghia

    lat0, lon0 = radians(float(lat_arr[idx_cuc_bo[0]])), radians(float(lon_arr[idx_cuc_bo[0]]))
    # idx_cuc_bo[0] CHUA CHAC la tram nguon - tim dung vi tri tram nguon truoc
    vi_tri_nguon_trong_cuc_bo = int(np.where(enb_list[idx_cuc_bo] == enb_nguon)[0][0])
    lat0 = radians(float(lat_arr[idx_cuc_bo[vi_tri_nguon_trong_cuc_bo]]))
    lon0 = radians(float(lon_arr[idx_cuc_bo[vi_tri_nguon_trong_cuc_bo]]))

    lat_r = np.radians(lat_arr[idx_cuc_bo])
    lon_r = np.radians(lon_arr[idx_cuc_bo])
    x_km = (lon_r - lon0) * EARTH_R_KM * cos(lat0)
    y_km = (lat_r - lat0) * EARTH_R_KM
    pts = np.column_stack([x_km, y_km])

    try:
        tri = Delaunay(pts)
    except Exception:
        return set(), set()

    canh: set[tuple[int, int]] = set()
    for simplex in tri.simplices:
        for i in range(3):
            a, b = simplex[i], simplex[(i + 1) % 3]
            canh.add((min(a, b), max(a, b)))

    # trung vi khoang cach lang gieng gan nhat trong tap cuc bo (dung cho nguong alpha)
    if len(pts) >= 2:
        tree_local = cKDTree(pts)
        d_nn, _ = tree_local.query(pts, k=2)
        trung_vi_nn = float(np.median(d_nn[:, 1]))
    else:
        trung_vi_nn = 0.0
    nguong = alpha * trung_vi_nn

    do_thi: dict[int, set[int]] = defaultdict(set)
    for a, b in canh:
        d = float(np.linalg.norm(pts[a] - pts[b]))
        if d <= nguong:
            do_thi[a].add(b)
            do_thi[b].add(a)

    l1_idx = do_thi.get(vi_tri_nguon_trong_cuc_bo, set())
    l2_idx: set[int] = set()
    for a in l1_idx:
        l2_idx |= do_thi.get(a, set())
    l2_idx -= l1_idx
    l2_idx.discard(vi_tri_nguon_trong_cuc_bo)

    l1 = {int(enb_list[idx_cuc_bo[i]]) for i in l1_idx}
    l2 = {int(enb_list[idx_cuc_bo[i]]) for i in l2_idx}
    return l1, l2


def muc_3(AGG: dict, tram_theo_enb: dict, nguon_enb_co_hop_le: set[int]) -> None:
    print(f"\nMUC 3 - Delaunay/alpha-shape (ban kinh {BAN_KINH_KM}km, mau {SO_MAU_DELAUNAY} tram nguon, seed={RANDOM_SEED}):")

    enb_list = np.array(list(tram_theo_enb.keys()))
    lat_arr = np.array([tram_theo_enb[e]["lat"] if tram_theo_enb[e]["lat"] is not None else np.nan for e in enb_list])
    lon_arr = np.array([tram_theo_enb[e]["lon"] if tram_theo_enb[e]["lon"] is not None else np.nan for e in enb_list])
    co_toa_do = ~np.isnan(lat_arr) & ~np.isnan(lon_arr)
    enb_list, lat_arr, lon_arr = enb_list[co_toa_do], lat_arr[co_toa_do], lon_arr[co_toa_do]
    xyz = _xyz(lat_arr, lon_arr)
    tree = cKDTree(xyz)
    # nguong 15km theo day cung 3D (xap xi great-circle, sai so khong dang ke o quy mo nay)
    nguong_day_cung = 2 * EARTH_R_KM * sin((BAN_KINH_KM / EARTH_R_KM) / 2)

    enb_toi_idx = {int(e): i for i, e in enumerate(enb_list)}

    ung_vien = [e for e in nguon_enb_co_hop_le if e in enb_toi_idx]
    rng = random.Random(RANDOM_SEED)
    mau = rng.sample(ung_vien, min(SO_MAU_DELAUNAY, len(ung_vien)))
    print(f"  So tram nguon hop le (co sector + co toa do) de chon mau: {len(ung_vien):,}; da lay mau: {len(mau)}")

    nhom_theo_tram = _nhom_theo_tram(AGG)

    def _danh_sach_A_theo_tram(enb_nguon: int) -> dict[int, dict]:
        """Tra {target_enb: {"attempt":.., "sr_x_att":.., "sr_w":..}} gop CA
        sector (giong Buoc 9 spike_ho_neighbor.py)."""
        gop: dict[int, dict] = defaultdict(lambda: {"attempt": 0, "sr_x_att": 0.0, "sr_w": 0})
        for sector, cands in nhom_theo_tram.get(enb_nguon, {}).items():
            for (enb, _lcr), v in cands.items():
                g = gop[enb]
                g["attempt"] += v["attempt"]
                g["sr_x_att"] += v["sr_x_att"]
                g["sr_w"] += v["sr_w"]
        return gop

    def _phan_loai_mot_alpha(alpha: float):
        dem_ring = {"L1": 0.0, "L2": 0.0, "Z": 0.0}
        z_entries: list[dict] = []
        for enb_nguon in mau:
            idx_nguon = enb_toi_idx[enb_nguon]
            idx_cuc_bo = tree.query_ball_point(xyz[idx_nguon], r=nguong_day_cung)
            idx_cuc_bo = np.array(idx_cuc_bo)
            l1, l2 = _phan_loai_L1_L2(enb_nguon, idx_cuc_bo, enb_list, lat_arr, lon_arr, alpha)

            danh_sach_a = _danh_sach_A_theo_tram(enb_nguon)
            tong = sum(v["attempt"] for v in danh_sach_a.values())
            if tong == 0:
                continue
            for enb_dich, v in danh_sach_a.items():
                pct = 100.0 * v["attempt"] / tong
                if enb_dich in l1:
                    dem_ring["L1"] += pct
                elif enb_dich in l2:
                    dem_ring["L2"] += pct
                else:
                    dem_ring["Z"] += pct
                    sr = (v["sr_x_att"] / v["sr_w"]) if v["sr_w"] > 0 else None
                    info_dich = tram_theo_enb.get(enb_dich)
                    if info_dich is not None and enb_dich in enb_toi_idx:
                        km = _haversine_km(
                            lat_arr[idx_nguon], lon_arr[idx_nguon],
                            lat_arr[enb_toi_idx[enb_dich]], lon_arr[enb_toi_idx[enb_dich]],
                        )
                    else:
                        km = None
                    z_entries.append({
                        "nguon": tram_theo_enb[enb_nguon]["tram_name"],
                        "dich": info_dich["tram_name"] if info_dich else f"(enb={enb_dich})",
                        "km": km,
                        "pct": pct,
                        "sr": sr,
                    })
        tong_pct = sum(dem_ring.values())
        ty_le = {k: (100.0 * v / tong_pct if tong_pct else None) for k, v in dem_ring.items()}
        return ty_le, z_entries

    ty_le_3, z_entries = _phan_loai_mot_alpha(3)
    print(f"  ALPHA=3: L1={ty_le_3['L1']:.1f}%  L2={ty_le_3['L2']:.1f}%  Z={ty_le_3['Z']:.1f}%  (tinh theo % HO gop tren {len(mau)} tram mau)")

    for alpha in (2, 4):
        ty_le_a, _ = _phan_loai_mot_alpha(alpha)
        print(f"  ALPHA={alpha}: L1={ty_le_a['L1']:.1f}%  L2={ty_le_a['L2']:.1f}%  Z={ty_le_a['Z']:.1f}%")

    print(f"\n  Cell Z (ALPHA=3) - tong {len(z_entries)} muc, phan phoi %HO va SR:")
    if z_entries:
        pct_arr = np.array([e["pct"] for e in z_entries])
        sr_arr = np.array([e["sr"] for e in z_entries if e["sr"] is not None])
        print(f"    %HO: trung_vi={np.median(pct_arr):.2f} P90={np.percentile(pct_arr,90):.2f} max={pct_arr.max():.2f}")
        if len(sr_arr):
            print(f"    SR : trung_vi={np.median(sr_arr):.2f} P10={np.percentile(sr_arr,10):.2f} (so co SR={len(sr_arr)}/{len(z_entries)})")

        dat_rule = [e for e in z_entries if e["pct"] >= 20 and e["sr"] is not None and e["sr"] >= 95]
        bi_chan = [e for e in z_entries if e not in dat_rule]
        print(f"    Luat (%HO>=20 VA SR>=95): DAT (vao B) = {len(dat_rule)}/{len(z_entries)} ({100.0*len(dat_rule)/len(z_entries):.2f}%)")
        print(f"    BI CHAN = {len(bi_chan)} - 10 vi du (sap theo %HO giam dan, gan nguong nhat):")
        for e in sorted(bi_chan, key=lambda x: -x["pct"])[:10]:
            km_str = f"{e['km']:.1f}km" if e["km"] is not None else "n/a"
            sr_str = f"{e['sr']:.2f}" if e["sr"] is not None else "n/a"
            print(f"      {e['nguon']:<20} -> {e['dich']:<20} {km_str:>8} %HO={e['pct']:6.2f}% SR={sr_str}")


# ============================================================================
# MUC 7 - doi chieu CR cu (cell_params that)
# ============================================================================
async def muc_7(AGG: dict, dn_map: dict) -> None:
    """SUA (hieu nang): KHONG doc lai CSV cho tung tram (39 lan x 3 trieu dong
    la qua cham) - AGG da duoc xay 1 LAN DUY NHAT trong doc_toan_bo_csv() cho
    TOAN BO tram nguon xuat hien trong file, bao gom san 39 tram session nay
    (neu chung co du lieu HO) - CHI can tra cuu lai qua _nhom_theo_tram()."""
    print("\nMUC 7 - Doi chieu voi CR da chay that (cell_params), tram NA09 (HNI):")
    print("  (xem G7 - HO chi co 1 moc 28/09/2026, CR cu chay thang 7-10/2026 - KHONG CUNG thoi diem)")

    from models.cell_params import CellParams as CellParamsModel
    from models.cr_session import CrSession as CrSessionModel

    async with AsyncSessionLocal() as s:
        q = (
            select(CrSessionModel.id, CrSessionModel.tram_id)
            .join(TramModel, TramModel.tram_id == CrSessionModel.tram_id)
            .where(TramModel.ma_tinh == "HNI", CrSessionModel.executed_at.is_not(None))
        )
        sessions = (await s.execute(q)).all()
        cell_params_rows = (await s.execute(
            select(CellParamsModel.cr_session_id, CellParamsModel.cell_name)
            .where(CellParamsModel.cr_session_id.in_([r.id for r in sessions]))
        )).all()

    cell_cu_theo_session: dict[int, set[str]] = defaultdict(set)
    for sid, cell_name in cell_params_rows:
        cell_cu_theo_session[sid].add(cell_name)

    nhom_theo_tram = _nhom_theo_tram(AGG)

    pct_trung_list = []
    so_session_co_du_lieu_ho = 0
    for sid, tram_id in sessions:
        cell_cu = cell_cu_theo_session.get(sid)
        if not cell_cu:
            continue
        try:
            enb_nguon = int(tram_id)
        except ValueError:
            continue

        AGG_rieng = nhom_theo_tram.get(enb_nguon)
        if not AGG_rieng:
            print(f"  session={sid:<6} tram={tram_id:<8} KHONG co du lieu HO trong file - bo qua")
            continue
        so_session_co_du_lieu_ho += 1

        # chay thuat toan B (giong Buoc 7 spike_ho_neighbor.py)
        da_chon: set[tuple[int, int]] = set()
        for sector in sorted(AGG_rieng):
            xep = sorted(AGG_rieng[sector].items(), key=lambda kv: -kv[1]["attempt"])
            so_da_chon = 0
            for (enb, lcr), v in xep:
                if so_da_chon >= 2:
                    break
                if (enb, lcr) in da_chon or not _LNCEL_CHAY_CR_RE.match(str(lcr)):
                    continue
                da_chon.add((enb, lcr))
                so_da_chon += 1

        cell_moi = {dn_map[k] for k in da_chon if k in dn_map}
        trung = cell_cu & cell_moi
        chi_cu = cell_cu - cell_moi
        chi_moi = cell_moi - cell_cu
        mau_so = len(cell_cu | cell_moi)
        pct_trung = 100.0 * len(trung) / mau_so if mau_so else 0.0
        pct_trung_list.append(pct_trung)
        print(
            f"  session={sid:<6} tram={tram_id:<8} cu={len(cell_cu):>3} moi={len(cell_moi):>3} "
            f"trung={len(trung):>3} chi_cu={len(chi_cu):>3} chi_moi={len(chi_moi):>3} %trung={pct_trung:5.1f}%"
        )

    print(f"\n  So session co du lieu HO de doi chieu: {so_session_co_du_lieu_ho}/{len(sessions)}")
    if pct_trung_list:
        print(f"  % trung TRUNG BINH qua cac session: {sum(pct_trung_list)/len(pct_trung_list):.1f}%")


# ============================================================================
async def main():
    path = _tim_file_csv()
    print(f"File CSV: {path}\n")

    ds = doc_toan_bo_csv(path)
    print(f"Tong so dong trong file: {ds['tong_dong']:,}")
    print(f"So (tram nguon, sector) nhom hop le: {len(ds['AGG']):,}")

    kq1 = muc_1(ds["AGG"])
    print("\nMUC 1 - Nguong 80% / tran 10-15-20 / bo <1%:")
    print(f"  So sector nguon co du lieu: {kq1['so_sector']:,}")
    print(f"  So cell can de dat 80% (sau bo <1%): trung_vi={kq1['trung_vi']:.1f} P90={kq1['p90']:.1f} P95={kq1['p95']:.1f} max={kq1['max']}")
    for t in (10, 15, 20):
        print(f"  Tran {t}: {kq1['pct_cham_tran'][t]:.1f}% sector CHAM tran; khi chi lay top-{t} thi phu trung binh {kq1['phu_trung_binh_tai_tran'][t]:.1f}% HO cua sector")
    print(f"  Tong %HO BI MAT do bo cell <1% (toan cuc, theo attempt): {kq1['pct_ho_mat_do_bo_1pct_global']:.2f}%")

    kq2 = muc_2(ds["AGG"], ds["sr_moi_cap"])
    print("\nMUC 2 - Phan phoi SR (Adj Inter eNB HO SR):")
    mc = kq2["moi_cap"]
    print(f"  Moi cap (n={mc['so_luong']:,}): P1={mc['p1']:.2f} P5={mc['p5']:.2f} P10={mc['p10']:.2f} trung_vi={mc['trung_vi']:.2f}")
    t2 = kq2["top2_moi_sector"]
    if t2:
        print(f"  Top-2/sector da qua luat CR (n={t2['so_luong']:,}): P1={t2['p1']:.2f} P5={t2['p5']:.2f} P10={t2['p10']:.2f} trung_vi={t2['trung_vi']:.2f}")
        print(f"  -> Nguong 95% {'HOP LY (phan lon top-2 >= 95)' if t2['p10'] >= 95 else 'CO THE LOAI OAN nhieu cell top-2 (P10 < 95)'}")

    muc_4(ds)

    print("\nDang tai bang tram + cell_infor tu DB...")
    tram_theo_enb = await nap_toan_bo_tram()
    dn_map = await nap_cell_infor_dn_map()
    print(f"  So tram co toa do: {sum(1 for v in tram_theo_enb.values() if v['lat'] is not None):,}")
    print(f"  So (enb,lcr) tra cuu duoc tu cell_infor: {len(dn_map):,}")

    muc_5(ds["global_a"], tram_theo_enb, dn_map)
    muc_6(tram_theo_enb, ds["nguon_enb_bat_ky"])
    muc_3(ds["AGG"], tram_theo_enb, ds["nguon_enb_co_hop_le"])
    await muc_7(ds["AGG"], dn_map)

    print("\n" + "=" * 78)
    print("DE XUAT GIA TRI NGUONG (xem so lieu cu the o tung muc o tren):")
    print("(se dien sau khi co ket qua chay that - placeholder, xem bao cao di kem)")


if __name__ == "__main__":
    asyncio.run(main())
