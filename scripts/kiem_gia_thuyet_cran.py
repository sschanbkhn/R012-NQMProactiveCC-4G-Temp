"""
KIEM GIA THUYET (CHI DOC, KHONG sua code/DB): toa do RIMS co phai la toa do
NOI DAT BASEBAND (CRAN - mot "hub" baseband phuc vu nhieu tram anten RF xa
nhau) hay la toa do THAT cua anten? Tu: yeu cau truc tiep user, dua tren
khao sat truoc (12.708 cap tram trung toa do CUNG ma_csht).

Tai su dung (import truc tiep, cung thu muc scripts/):
  - scripts.phan_tich_nguong_ho: doc file HO NA09, giai ma ECI.
"""

import asyncio
import re
from collections import defaultdict

from sqlalchemy import select

from infrastructure.db import AsyncSessionLocal
from models.tram import Tram as TramModel
from scripts.phan_tich_nguong_ho import _nhom_theo_tram, _tim_file_csv, doc_toan_bo_csv

# "4G-CGY029B-HNI" -> site "CGY029" (chu+so TRUOC 1 ky tu loai tram, dung quy
# uoc dat ten CO SAN cua VNPT - xem domain/services/loai_tram.py, KHAC mau do
# la cho TEN CELL (co them 2 chu so sector o CUOI); tram_name KHONG co 2 chu
# so do.
#
# KHAC voi loai_tram.py::_LOAI_TRAM_RE (chi khop tien to "4G-"): khao sat THAT
# cho thay con nhieu tien to khac (UL_, UL-, LN-, SN-...) VA dau phan cach
# khac (gach ngang "-" LAN gach duoi "_") - vd "UL_HBG012E_HPG",
# "UL-KAH059M-HTH", "LN-ADG028M-HPG". Regex RONG HON (khong ep tien to
# "4G", chap nhan ca 2 loai dau phan cach) de giam so cap "khong xac dinh
# duoc" - VAN giu nguyen tac "khong doan": ten khong khop du da rong van tra
# None, KHONG ep buoc.
_SITE_RE = re.compile(r"^[A-Za-z0-9]+[-_]([A-Z]{2,4}[0-9]{2,4})[A-Z][-_][A-Z]{3}$")


def _so_site(tram_name: str) -> str | None:
    m = _SITE_RE.match(tram_name)
    return m.group(1) if m else None


async def _nap_tram():
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(
            TramModel.tram_id, TramModel.tram_name, TramModel.ma_csht,
            TramModel.ten_quan_ly, TramModel.ma_tinh, TramModel.latitude, TramModel.longitude,
        ))).all()
    ket_qua = []
    for tram_id, tram_name, ma_csht, ten_quan_ly, ma_tinh, lat, lon in rows:
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)
        if lat == 0 and lon == 0:
            continue
        ket_qua.append({
            "tram_id": tram_id, "tram_name": tram_name, "ma_csht": ma_csht,
            "ten_quan_ly": ten_quan_ly, "ma_tinh": ma_tinh, "lat": lat, "lon": lon,
        })
    return ket_qua


def _nhom_theo_toa_do(tram_list: list[dict]) -> dict[tuple, list[dict]]:
    nhom: dict[tuple, list[dict]] = defaultdict(list)
    for t in tram_list:
        key = (round(t["lat"], 6), round(t["lon"], 6))
        nhom[key].append(t)
    return {k: v for k, v in nhom.items() if len(v) >= 2}


async def main():
    tram_list = await _nap_tram()
    print(f"Tong so tram co toa do hop le: {len(tram_list):,}")
    nhom_toa_do = _nhom_theo_toa_do(tram_list)

    # === MUC 1: tach cap CUNG ma_csht trong nhom trung toa do, phan loai
    # theo SO SITE (a = cung so site, b = khac so site) ===
    cung_so_site: list[tuple[dict, dict]] = []
    khac_so_site: list[tuple[dict, dict]] = []
    khong_xac_dinh: list[tuple[dict, dict]] = []
    tram_trong_nhom_b: set[str] = set()  # MUC 3 - tram_id PHAN BIET thuoc >=1 cap loai b

    for toa_do, thanh_vien in nhom_toa_do.items():
        n = len(thanh_vien)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = thanh_vien[i], thanh_vien[j]
                if not (a["ma_csht"] and b["ma_csht"] and a["ma_csht"] == b["ma_csht"]):
                    continue  # CHI xet cap CUNG ma_csht (dac ta muc 1)
                site_a, site_b = _so_site(a["tram_name"]), _so_site(b["tram_name"])
                if site_a is None or site_b is None:
                    khong_xac_dinh.append((a, b))
                elif site_a == site_b:
                    cung_so_site.append((a, b))
                else:
                    khac_so_site.append((a, b))
                    tram_trong_nhom_b.add(a["tram_id"])
                    tram_trong_nhom_b.add(b["tram_id"])

    print("\n" + "=" * 78)
    print("MUC 1 - Phan loai cap tram trung toa do, CUNG ma_csht, theo SO SITE:")
    print(f"  (a) CUNG so site (vd CGY029M/CGY029B): {len(cung_so_site):,} cap")
    print(f"  (b) KHAC so site (vd CGY029/CGY025)  : {len(khac_so_site):,} cap")
    print(f"  Khong xac dinh duoc so site (ten khac mau): {len(khong_xac_dinh):,} cap")
    print(f"  Tong cap cung ma_csht da xet: {len(cung_so_site) + len(khac_so_site) + len(khong_xac_dinh):,}")

    if khong_xac_dinh:
        print("\n  5 vi du 'khong xac dinh duoc so site' (ten tram khong dung mau):")
        for a, b in khong_xac_dinh[:5]:
            print(f"    {a['tram_name']} <-> {b['tram_name']}")

    print("\n  10 vi du loai (b) - KHAC so site, CUNG toa do, CUNG ma_csht:")
    for a, b in khac_so_site[:10]:
        print(f"    {a['tram_name']:<18} <-> {b['tram_name']:<18} ma_csht={a['ma_csht']} ten_quan_ly={a['ten_quan_ly']}")

    # === MUC 2: trong loai (b), bao nhieu co chu "CRAN" trong ten_quan_ly? ===
    print("\n" + "=" * 78)
    print("MUC 2 - Loai (b): chu 'CRAN' trong ten_quan_ly?")
    so_cap_co_cran = sum(
        1 for a, b in khac_so_site
        if (a["ten_quan_ly"] and "CRAN" in a["ten_quan_ly"].upper())
        or (b["ten_quan_ly"] and "CRAN" in b["ten_quan_ly"].upper())
    )
    print(f"  So cap (b) co chu CRAN trong ten_quan_ly (it nhat 1 ben): {so_cap_co_cran:,}/{len(khac_so_site):,} "
          f"({100.0*so_cap_co_cran/len(khac_so_site):.1f}%)" if khac_so_site else "  (khong co cap loai b)")

    # Top 10 ma_csht co NHIEU tram nhat dung chung 1 toa do (CHUNG, khong
    # gioi han rieng loai b - dac ta muc 2 doan 2 khong gioi han pham vi nay).
    theo_ma_csht_toa_do: dict[tuple[str, tuple], list[dict]] = defaultdict(list)
    for toa_do, thanh_vien in nhom_toa_do.items():
        theo_ma_csht_trong_nhom: dict[str, list[dict]] = defaultdict(list)
        for t in thanh_vien:
            if t["ma_csht"]:
                theo_ma_csht_trong_nhom[t["ma_csht"]].append(t)
        for ma_csht, ds in theo_ma_csht_trong_nhom.items():
            if len(ds) >= 2:
                theo_ma_csht_toa_do[(ma_csht, toa_do)] = ds

    top10 = sorted(theo_ma_csht_toa_do.items(), key=lambda kv: -len(kv[1]))[:10]
    print("\n  10 ma_csht co NHIEU tram nhat dung chung toa do:")
    for (ma_csht, toa_do), ds in top10:
        vi_du = ", ".join(t["tram_name"] for t in ds[:3])
        ten_quan_ly = ds[0]["ten_quan_ly"] or "(rong)"
        print(f"    ma_csht={ma_csht:<16} so_tram={len(ds):<4} ten_quan_ly={ten_quan_ly:<35} vi_du=[{vi_du}, ...]")

    # === MUC 3: toan bang tram - bao nhieu tram nam trong nhom "toa do dung
    # chung voi tram KHAC so site"? Bao nhieu % o HNI? ===
    print("\n" + "=" * 78)
    print("MUC 3 - Tram thuoc nhom toa do dung chung VOI TRAM KHAC SO SITE:")
    tong_tram = len(tram_list)
    so_tram_b = len(tram_trong_nhom_b)
    print(f"  Tong so tram (co toa do hop le): {tong_tram:,}")
    print(f"  So tram thuoc nhom (b): {so_tram_b:,} ({100.0*so_tram_b/tong_tram:.3f}% toan bang)")

    tram_hni_id = {t["tram_id"] for t in tram_list if t["ma_tinh"] == "HNI"}
    so_tram_b_hni = len(tram_trong_nhom_b & tram_hni_id)
    print(f"  Trong do o HNI: {so_tram_b_hni:,}/{len(tram_hni_id):,} tram HNI "
          f"({100.0*so_tram_b_hni/len(tram_hni_id):.3f}% tram HNI)")

    # === MUC 4: doi chieu HO - cac cap loai (b) O HNI (file NA09 chi co du
    # lieu HNI) co HO qua lai khong, phan bo % HO ===
    print("\n" + "=" * 78)
    print("MUC 4 - Doi chieu HO (NA09/HNI) cho cac cap loai (b):")
    path = _tim_file_csv()
    ds = doc_toan_bo_csv(path)
    nhom_ho = _nhom_theo_tram(ds["AGG"])  # enb -> {sector: {(t_enb,t_lcr): {...}}}

    def _tong_ho_di(enb: int) -> int:
        return sum(v["attempt"] for cands in nhom_ho.get(enb, {}).values() for v in cands.values())

    def _ho_giua(enb_a: int, enb_b: int) -> int:
        tong = 0
        for cands in nhom_ho.get(enb_a, {}).values():
            for (t_enb, _t_lcr), v in cands.items():
                if t_enb == enb_b:
                    tong += v["attempt"]
        return tong

    cap_b_hni = [(a, b) for a, b in khac_so_site if a["ma_tinh"] == "HNI" and b["ma_tinh"] == "HNI"]
    print(f"  So cap loai (b) O HNI (co du lieu HO de doi chieu): {len(cap_b_hni):,}/{len(khac_so_site):,}")

    ket_qua_doi_chieu = []
    for a, b in cap_b_hni:
        try:
            enb_a, enb_b = int(a["tram_id"]), int(b["tram_id"])
        except ValueError:
            continue
        ho_a_toi_b = _ho_giua(enb_a, enb_b)
        ho_b_toi_a = _ho_giua(enb_b, enb_a)
        tong_a = _tong_ho_di(enb_a)
        tong_b = _tong_ho_di(enb_b)
        pct_a = 100.0 * ho_a_toi_b / tong_a if tong_a else None
        pct_b = 100.0 * ho_b_toi_a / tong_b if tong_b else None
        ket_qua_doi_chieu.append({
            "a": a["tram_name"], "b": b["tram_name"],
            "ho_a_toi_b": ho_a_toi_b, "ho_b_toi_a": ho_b_toi_a,
            "pct_a": pct_a, "pct_b": pct_b,
        })

    so_co_ho = sum(1 for r in ket_qua_doi_chieu if r["ho_a_toi_b"] > 0 or r["ho_b_toi_a"] > 0)
    so_khong_ho = len(ket_qua_doi_chieu) - so_co_ho
    print(f"  So cap CO HO qua lai (bat ky chieu nao): {so_co_ho:,}/{len(ket_qua_doi_chieu):,}")
    print(f"  So cap KHONG CO HO nao qua lai: {so_khong_ho:,}/{len(ket_qua_doi_chieu):,}")

    import numpy as np
    pct_max = np.array([max(r["pct_a"] or 0, r["pct_b"] or 0) for r in ket_qua_doi_chieu])
    print(f"\n  Phan phoi %HO LON HON (max 2 chieu) tren TOAN BO {len(ket_qua_doi_chieu)} cap kiem duoc:")
    print(f"    trung_vi={np.median(pct_max):.2f}% P25={np.percentile(pct_max,25):.2f}% P75={np.percentile(pct_max,75):.2f}% P90={np.percentile(pct_max,90):.2f}%")
    print(f"    % cap co HO RAT THAP (<1%, gom ca 0%): {100.0*(pct_max<1).sum()/len(pct_max):.1f}%")
    print(f"    % cap co HO THAP (<5%): {100.0*(pct_max<5).sum()/len(pct_max):.1f}%")
    print(f"    % cap co HO DANG KE (>=20%, giong nguong vung Z): {100.0*(pct_max>=20).sum()/len(pct_max):.1f}%")

    print("\n  Chi tiet (toi da 20 cap dau, sap theo pct_a giam dan - uu tien cap CO HO de xem):")
    xep = sorted(ket_qua_doi_chieu, key=lambda r: -(r["pct_a"] or 0))
    for r in xep[:20]:
        pct_a_s = f"{r['pct_a']:.2f}%" if r["pct_a"] is not None else "n/a"
        pct_b_s = f"{r['pct_b']:.2f}%" if r["pct_b"] is not None else "n/a"
        print(f"    {r['a']:<18} <-> {r['b']:<18} HO(a->b)={r['ho_a_toi_b']:<6} ({pct_a_s:>7}) HO(b->a)={r['ho_b_toi_a']:<6} ({pct_b_s:>7})")


if __name__ == "__main__":
    asyncio.run(main())
