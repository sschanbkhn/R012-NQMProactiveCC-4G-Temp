"""
DO (CHI DOC) khoang cach tram -> tram GAN NHAT (ca nuoc + rieng HNI), phan
theo cung/khac ma_csht - lam co so CHOT luat GOP CUM SITE (quyet dinh
08/10/2026, yeu cau truc tiep user, sau review thiet ke).

Dung KD-tree tren toa do 3D (chieu len mat cau don vi x ban kinh Trai Dat) de
tim lang gieng gan nhat CHINH XAC (khong gioi han ban kinh truoc), tranh sai
so cua phep chieu phang khi khoang cach rat nho (met).
"""

import asyncio

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy import select

from infrastructure.db import AsyncSessionLocal
from models.tram import Tram as TramModel

EARTH_R_M = 6371008.8  # met

BUCKETS_M = [0, 10, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400, float("inf")]


def _xyz(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    x = EARTH_R_M * np.cos(lat) * np.cos(lon)
    y = EARTH_R_M * np.cos(lat) * np.sin(lon)
    z = EARTH_R_M * np.sin(lat)
    return np.column_stack([x, y, z])


def _phan_tich(ten_vung: str, tram_ids, lats, lons, ma_cshts):
    tong = len(tram_ids)
    co_toa_do = [i for i in range(tong) if lats[i] is not None and lons[i] is not None and not (lats[i] == 0 and lons[i] == 0)]
    print(f"\n=== {ten_vung}: {tong} tram, {len(co_toa_do)} co toa do hop le ===")
    so_khong_ma_csht = sum(1 for i in co_toa_do if not ma_cshts[i])
    print(f"  So tram KHONG co ma_csht: {so_khong_ma_csht}/{len(co_toa_do)} ({100.0*so_khong_ma_csht/len(co_toa_do):.2f}%)")

    lat_arr = np.array([lats[i] for i in co_toa_do])
    lon_arr = np.array([lons[i] for i in co_toa_do])
    xyz = _xyz(lat_arr, lon_arr)
    tree = cKDTree(xyz)
    d_chord, idx = tree.query(xyz, k=2)  # cot 0 la chinh no (d=0), cot 1 la lang gieng gan nhat
    # doi day cung (chord) sang khoang cach THAT tren mat cau (m) - sai so
    # khong dang ke o quy mo <1km.
    d_m = 2 * EARTH_R_M * np.arcsin(np.clip(d_chord[:, 1] / (2 * EARTH_R_M), 0, 1))

    cung_ma_csht = []
    khac_ma_csht = []
    for k, i in enumerate(co_toa_do):
        j = co_toa_do[idx[k, 1]]
        d = d_m[k]
        if ma_cshts[i] and ma_cshts[j] and ma_cshts[i] == ma_cshts[j]:
            cung_ma_csht.append((d, tram_ids[i], tram_ids[j]))
        else:
            khac_ma_csht.append((d, tram_ids[i], tram_ids[j]))

    print(f"\n  Phan bo khoang cach toi lang gieng GAN NHAT theo khoang (m):")
    print(f"  {'khoang (m)':<14} {'tong':>8} {'% cung ma_csht':>16} {'% khac ma_csht':>16}")
    for b in range(len(BUCKETS_M) - 1):
        lo, hi = BUCKETS_M[b], BUCKETS_M[b + 1]
        nhan = f"{lo:.0f}-{hi:.0f}" if hi != float("inf") else f">{lo:.0f}"
        trong_khoang_cung = sum(1 for d, _, _ in cung_ma_csht if lo <= d < hi)
        trong_khoang_khac = sum(1 for d, _, _ in khac_ma_csht if lo <= d < hi)
        tong_khoang = trong_khoang_cung + trong_khoang_khac
        if tong_khoang == 0:
            continue
        print(f"  {nhan:<14} {tong_khoang:>8} {100.0*trong_khoang_cung/tong_khoang:>15.1f}% {100.0*trong_khoang_khac/tong_khoang:>15.1f}%")

    d_khac = np.array([d for d, _, _ in khac_ma_csht])
    d_cung = np.array([d for d, _, _ in cung_ma_csht])
    print(f"\n  Cap KHAC ma_csht (n={len(d_khac)}): P1={np.percentile(d_khac,1):.1f}m P5={np.percentile(d_khac,5):.1f}m")
    print(f"  Cap CUNG ma_csht (n={len(d_cung)}): P95={np.percentile(d_cung,95):.1f}m P99={np.percentile(d_cung,99):.1f}m max={d_cung.max():.1f}m")

    vi_du = sorted([t for t in cung_ma_csht if t[0] > 200], key=lambda t: -t[0])[:10]
    print(f"\n  10 vi du CUNG ma_csht nhung > 200m (co {sum(1 for t in cung_ma_csht if t[0]>200)} cap nhu vay):")
    for d, a, b in vi_du:
        print(f"    {a} <-> {b}: {d:.1f}m")

    return d_khac, d_cung


async def main():
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(TramModel.tram_id, TramModel.ma_tinh, TramModel.ma_csht, TramModel.latitude, TramModel.longitude))).all()

    tram_ids = [r[0] for r in rows]
    ma_tinhs = [r[1] for r in rows]
    ma_cshts = [r[2] for r in rows]
    lats = [float(r[3]) if r[3] is not None else None for r in rows]
    lons = [float(r[4]) if r[4] is not None else None for r in rows]

    _phan_tich("TOAN QUOC", tram_ids, lats, lons, ma_cshts)

    idx_hni = [i for i in range(len(tram_ids)) if ma_tinhs[i] == "HNI"]
    _phan_tich("HNI", [tram_ids[i] for i in idx_hni], [lats[i] for i in idx_hni], [lons[i] for i in idx_hni], [ma_cshts[i] for i in idx_hni])


if __name__ == "__main__":
    asyncio.run(main())
