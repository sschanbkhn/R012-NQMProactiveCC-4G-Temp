"""
DIEU TRA (CHI DOC) - tai sao 24,7% tram mau (74/300) bi gan TOA_DO_NGHI_SAI
trong scripts/kiem_tra_thuat_toan_ho.py. KHONG sua domain/services/ho_delaunay.py
hay ho_cell_selector.py - CHI dung lai 2 module do (phan_lop_delaunay voi
ALPHA/ban_kinh khac nhau de so sanh) VA 1 ham MO RONG RIENG cho L3 (CHI o
script nay, de dieu tra - KHONG PHAI thay doi luat chinh thuc).

Tu: yeu cau truc tiep user - "Ket luan: co do TOA DO SAI that hay do MO HINH
L1/L2 qua hep. De xuat cach sua... KHONG tu sua luat co."
"""

import asyncio
import random

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from domain.services.ho_cell_selector import chon_cell_cr
from domain.services.ho_delaunay import (
    ALPHA_MAC_DINH,
    BAN_KINH_KM_MAC_DINH,
    EARTH_R_KM,
    NGUONG_CUNG_SITE_KM_MAC_DINH,
    TramDiem,
    _haversine_km,
    _toa_do_hop_le,
    phan_lop_delaunay,
)
from scripts.kiem_tra_thuat_toan_ho import (
    _ho_rows_cho_tram,
    _thong_tin_tram_dich,
    _tram_diem_list,
)
from scripts.phan_tich_nguong_ho import (
    _nhom_theo_tram,
    _tim_file_csv,
    doc_toan_bo_csv,
    nap_cell_infor_dn_map,
    nap_toan_bo_tram,
)

RANDOM_SEED = 42
SO_MAU = 300


async def _nap_ma_csht() -> dict[int, str | None]:
    # TACH RIENG (khong sua nap_toan_bo_tram() dung chung o phan_tich_nguong_ho.py
    # - tranh dong cham code dang dung o script khac) - CHI can ma_csht cho
    # muc d (doi chieu 111 cap trung toa do khac ma_csht da phat hien truoc).
    from sqlalchemy import select

    from infrastructure.db import AsyncSessionLocal
    from models.tram import Tram as TramModel

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(TramModel.tram_id, TramModel.ma_csht))).all()
    ket_qua: dict[int, str | None] = {}
    for tram_id, ma_csht in rows:
        try:
            ket_qua[int(tram_id)] = ma_csht
        except ValueError:
            continue
    return ket_qua


def _phan_lop_co_l3(x: TramDiem, ung_vien: list, alpha: float, ban_kinh_km: float):
    """BAN SAO RIENG cho dieu tra (KHONG dua vao domain/) - mo rong them 1
    hop (L3) tu CHINH co che cua phan_lop_delaunay(). Tra (so_l1, so_l2, so_l3)."""
    if not _toa_do_hop_le(x):
        return 0, 0, 0
    ung_vien_hop_le = [d for d in ung_vien if _toa_do_hop_le(d) and d.tram_id != x.tram_id]
    cung_site = []
    con_lai = []
    for d in ung_vien_hop_le:
        km = _haversine_km(x.lat, x.lon, d.lat, d.lon)
        if km < NGUONG_CUNG_SITE_KM_MAC_DINH:
            cung_site.append(d)
        elif km <= ban_kinh_km:
            con_lai.append(d)
    if not con_lai:
        return len(cung_site), 0, 0

    nhom_theo_toa_do = {}
    for d in con_lai:
        key = (round(d.lat, 6), round(d.lon, 6))
        nhom_theo_toa_do.setdefault(key, []).append(d)
    dai_dien = [nhom[0] for nhom in nhom_theo_toa_do.values()]
    if len(dai_dien) + 1 < 4:
        return len(cung_site), 0, 0

    from math import cos, radians

    lat0, lon0 = radians(x.lat), radians(x.lon)
    pts = [(0.0, 0.0)]
    for d in dai_dien:
        x_km = (radians(d.lon) - lon0) * EARTH_R_KM * cos(lat0)
        y_km = (radians(d.lat) - lat0) * EARTH_R_KM
        pts.append((x_km, y_km))
    pts_arr = np.array(pts)
    try:
        tri = Delaunay(pts_arr)
    except Exception:
        return len(cung_site), 0, 0

    canh = set()
    for simplex in tri.simplices:
        for i in range(3):
            a, b = int(simplex[i]), int(simplex[(i + 1) % 3])
            canh.add((min(a, b), max(a, b)))
    tree = cKDTree(pts_arr)
    d_nn, _ = tree.query(pts_arr, k=2)
    trung_vi_nn = float(np.median(d_nn[:, 1]))
    nguong = alpha * trung_vi_nn

    do_thi = {i: set() for i in range(len(pts_arr))}
    for a, b in canh:
        if float(np.linalg.norm(pts_arr[a] - pts_arr[b])) <= nguong:
            do_thi[a].add(b)
            do_thi[b].add(a)

    IDX_X = 0
    l1 = do_thi[IDX_X]
    l2 = set()
    for a in l1:
        l2 |= do_thi[a]
    l2 -= l1
    l2.discard(IDX_X)
    l3 = set()
    for a in l2:
        l3 |= do_thi[a]
    l3 -= l1
    l3 -= l2
    l3.discard(IDX_X)

    return len(cung_site) + len(l1), len(l2), len(l3)


async def main():
    path = _tim_file_csv()
    ds = doc_toan_bo_csv(path)
    tram_theo_enb = await nap_toan_bo_tram()
    dn_map = await nap_cell_infor_dn_map()
    ma_csht_theo_enb = await _nap_ma_csht()
    nhom = _nhom_theo_tram(ds["AGG"])
    tram_diem_list = _tram_diem_list(tram_theo_enb)
    thong_tin_dich = _thong_tin_tram_dich(tram_theo_enb)

    ung_vien = [
        enb for enb in nhom
        if enb in tram_theo_enb and tram_theo_enb[enb]["ma_tinh"] == "HNI" and tram_theo_enb[enb]["lat"] is not None
    ]
    rng = random.Random(RANDOM_SEED)
    mau = rng.sample(ung_vien, min(SO_MAU, len(ung_vien)))

    # --- Doi chieu 111 cap trung toa do KHAC ma_csht (da phat hien o Muc 0
    # cua yeu cau truoc) - nap lai NGAY TAI DAY (CHI DOC) ---
    theo_toa_do: dict[tuple, list] = {}
    for enb, info in tram_theo_enb.items():
        if info["lat"] is None:
            continue
        key = (round(info["lat"], 6), round(info["lon"], 6))
        theo_toa_do.setdefault(key, []).append((enb, ma_csht_theo_enb.get(enb)))
    tram_loi_trung_toa_do_khac_csht: set[int] = set()
    for lst in theo_toa_do.values():
        if len(lst) < 2:
            continue
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                if lst[i][1] != lst[j][1]:
                    tram_loi_trung_toa_do_khac_csht.add(lst[i][0])
                    tram_loi_trung_toa_do_khac_csht.add(lst[j][0])

    ket_qua_74: list[dict] = []
    for enb in mau:
        x_info = tram_theo_enb[enb]
        x_diem = TramDiem(str(enb), x_info["tram_name"], x_info["lat"], x_info["lon"])
        ung_vien_diem = [d for d in tram_diem_list if d.tram_id != str(enb)]
        l1_l2 = phan_lop_delaunay(x_diem, ung_vien_diem)
        rows = _ho_rows_cho_tram(nhom, enb)
        if not rows:
            continue
        kq = chon_cell_cr(str(enb), rows, l1_l2, thong_tin_dich, dn_map, x_lat=x_info["lat"], x_lon=x_info["lon"])
        if not kq.nghi_toa_do_x:
            continue

        l1_list = [t for t in l1_l2 if t.layer == "L1"]
        l2_list = [t for t in l1_l2 if t.layer == "L2"]
        trung_vi_l1 = sorted(t.km for t in l1_list)[len(l1_list) // 2] if l1_list else None

        top5 = sorted(kq.a, key=lambda c: -c.ho_attempt)[:5]
        ket_qua_74.append({
            "enb": enb, "ten": x_info["tram_name"], "lat": x_info["lat"], "lon": x_info["lon"],
            "so_l1": len(l1_list), "so_l2": len(l2_list), "trung_vi_l1": trung_vi_l1,
            "top5": top5, "loi_trung_toa_do": enb in tram_loi_trung_toa_do_khac_csht,
        })

    print(f"Tong so tram X bi gan TOA_DO_NGHI_SAI: {len(ket_qua_74)}/{len(mau)}")

    # === a. Phan bo khu vuc theo mat do (trung vi L1) ===
    print("\n=== a. Phan bo theo mat do (khoang cach L1 trung vi) ===")
    nhom_mat_do = {"noi_thanh_day_dac (<0.5km)": 0, "ven_do (0.5-2km)": 0, "thua (2-5km)": 0, "rat_thua (>5km)": 0, "khong_co_L1": 0}
    for r in ket_qua_74:
        tv = r["trung_vi_l1"]
        if tv is None:
            nhom_mat_do["khong_co_L1"] += 1
        elif tv < 0.5:
            nhom_mat_do["noi_thanh_day_dac (<0.5km)"] += 1
        elif tv < 2:
            nhom_mat_do["ven_do (0.5-2km)"] += 1
        elif tv < 5:
            nhom_mat_do["thua (2-5km)"] += 1
        else:
            nhom_mat_do["rat_thua (>5km)"] += 1
    for k, v in nhom_mat_do.items():
        print(f"  {k:<28} {v:>3} tram ({100.0*v/len(ket_qua_74):.1f}%)")

    so_l1_arr = np.array([r["so_l1"] for r in ket_qua_74])
    so_l2_arr = np.array([r["so_l2"] for r in ket_qua_74])
    print(f"\n  So tram L1: trung_vi={np.median(so_l1_arr):.0f} min={so_l1_arr.min()} max={so_l1_arr.max()}")
    print(f"  So tram L2: trung_vi={np.median(so_l2_arr):.0f} min={so_l2_arr.min()} max={so_l2_arr.max()}")
    print(f"  So tram KHONG co L1 nao: {sum(1 for r in ket_qua_74 if r['so_l1']==0)}/{len(ket_qua_74)}")

    # === b. 10 vi du ===
    print("\n=== b. 10 vi du (toa do X, top 5 tram dich theo HO kem km+layer, ban kinh L1 trung vi) ===")
    for r in ket_qua_74[:10]:
        tv_str = f"{r['trung_vi_l1']:.2f}km" if r["trung_vi_l1"] is not None else "n/a (0 L1)"
        print(f"\n  X={r['ten']} (enb={r['enb']}) lat={r['lat']} lon={r['lon']} | L1={r['so_l1']} L2={r['so_l2']} | trung_vi_L1={tv_str}")
        for c in r["top5"]:
            km_str = f"{c.km:.2f}km" if c.km is not None else "n/a"
            print(f"      -> {c.tram_dich_ten or c.target_enb:<22} layer={c.layer:<2} km={km_str:<9} attempt={c.ho_attempt:<6} %={100*c.pct_trong_sector:.1f}")

    # === c. Thu L1+L2+L3, ALPHA 4, 5 ===
    print("\n=== c. Thu lai voi L1+L2+L3 va ALPHA 4/5 (CHI DIEU TRA - khong doi luat chinh thuc) ===")
    for alpha_thu, dung_l3 in [(3, True), (4, False), (5, False)]:
        so_con_bi_co = 0
        for enb in mau:
            x_info = tram_theo_enb[enb]
            x_diem = TramDiem(str(enb), x_info["tram_name"], x_info["lat"], x_info["lon"])
            ung_vien_diem = [d for d in tram_diem_list if d.tram_id != str(enb)]
            rows = _ho_rows_cho_tram(nhom, enb)
            if not rows:
                continue
            if dung_l3:
                # Dung ham MO RONG L3 CHI o day de biet them L3 co "vot" duoc
                # cell Z coi la gan hon khong - nhung chon_cell_cr() CHINH
                # THUC chi nhan L1/L2 (gia tri tra ve tu phan_lop_delaunay),
                # nen o day CHI dem so cell duoc "cuu" NEU coi L3 cung la
                # "khong phai Z", KHONG thuc su doi hanh vi chon_cell_cr().
                l1_l2 = phan_lop_delaunay(x_diem, ung_vien_diem, alpha=alpha_thu)
                so_l1, so_l2, so_l3 = _phan_lop_co_l3(x_diem, ung_vien_diem, alpha_thu, BAN_KINH_KM_MAC_DINH)
            else:
                l1_l2 = phan_lop_delaunay(x_diem, ung_vien_diem, alpha=alpha_thu)
            kq = chon_cell_cr(str(enb), rows, l1_l2, thong_tin_dich, dn_map, x_lat=x_info["lat"], x_lon=x_info["lon"])
            if kq.nghi_toa_do_x:
                so_con_bi_co += 1
        nhan = f"ALPHA={alpha_thu}" + (" (+L3 rieng de tham khao, KHONG doi chon_cell_cr)" if dung_l3 else "")
        print(f"  {nhan}: {so_con_bi_co}/{len(mau)} tram bi co ({100.0*so_con_bi_co/len(mau):.1f}%)")

    # === d. Trung toa do khac ma_csht ===
    print("\n=== d. Doi chieu voi 111 cap trung toa do KHAC ma_csht (loi du lieu that) ===")
    so_trung = sum(1 for r in ket_qua_74 if r["loi_trung_toa_do"])
    print(f"  So tram X (trong 74 tram bi co) CUNG LUC trung toa do voi tram KHAC ma_csht: {so_trung}/{len(ket_qua_74)}")


if __name__ == "__main__":
    asyncio.run(main())
