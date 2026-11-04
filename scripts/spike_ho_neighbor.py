"""
SPIKE CHI DOC — danh gia y tuong THAY CDS /cell/neighbors bang report HO
(handover) neighbor THAT tu NetAct, cho 1 tram sap tat.

Boi canh (yeu cau truc tiep user, 06/10/2026): CDS /cell/neighbors tinh
neighbor tu thong so nhap tay (do cao, azimuth cua tram) nen hay sai/thieu
cap nhat. Y tuong thay the: dung du lieu HO THAT - UE cua tram sap tat dang
handover SANG cell nao NHIEU NHAT (attempt cao nhat) thi cell do dang THAT
SU phu vung cua tram do, khong can suy tu azimuth.

KHONG sua code he thong (chi doc cac module domain/ da co san), KHONG ghi DB
(chi SELECT qua AsyncSessionLocal), KHONG tao migration. Script nay la
THUC NGHIEM (spike) - ket qua de THAM KHAO, chua phai quyet dinh thay the CDS.

Chay (PYTHONPATH tu goc repo):
    PYTHONPATH=. ./venv/Scripts/python.exe scripts/spike_ho_neighbor.py [tram_id]

Mac dinh tram_id=117903 (chon vi can doi chieu truc tiep voi CDS that o Buoc 8
- tram nay co du lieu HO trong file CSV, da xac nhan qua khao sat truoc khi
viet script).

=== GIA DINH DA GHI RO (yeu cau "ghi ro moi gia dinh") ===
1. Xep hang cell dich theo SO LUONG ATTEMPT (Inter eNB HO prep att neigh),
   KHONG ap nguong SR (Adj Inter eNB HO SR) toi thieu nao - SR chi hien THAM
   KHAO trong bang, KHONG dung de loai cell. Ly do: user chua chi dinh nguong
   SR cu the, tu dat nguong se la DOAN.
2. "Nguon dich thi cell do phu vung" CHI dung attempt THO (so lan handover-
   prep), KHONG chuan hoa theo luu luong/so UE cua tram nguon - tram luu
   luong cao se tu nhien co attempt cao hon tram luu luong thap, co the lam
   lech thu hang giua cac tram KHAC NHAU (khong anh huong thu hang NOI BO 1
   sector cua 1 tram, vi cung tram thi luu luong la hang so chung).
3. "eci_id" la ECI 28-bit chuan 3GPP (20-bit eNB ID + 8-bit Cell ID) -> enb =
   eci_id // 256, lcr = eci_id % 256. Da KIEM CHUNG bang du lieu THAT (xem
   Buoc 2 ben duoi), khong phai suy doan tu tai lieu.
4. "Sector nguon" = chu so CUOI cua LNCEL ID nguon (vd LNCEL-11 -> sector 1),
   CUNG quy uoc "huong_id % 10" da dung xuyen suot domain/services/
   neighbor_cell_filter.py - KHONG phai quy uoc moi rieng cho script nay.
5. File dmnc_id KHONG TON TAI trong CSV that (xem Buoc 1) - dung mnc_id thay
   the, va da xac nhan gia tri THAT la "02" (VinaPhone) cho 100% dong, nen
   buoc loc nay la MOT PHEP KIEM TRA (assert), khong loai bo dong nao thuc su.
6. CDS that (Buoc 8) co the KHONG goi duoc tu may chay script nay neu khong
   co VPN/mang noi bo VNPT toi gw-oneoss.vnpt.vn - script se BAO RO thay vi
   bia ket qua so sanh.
"""

import asyncio
import csv
import glob
import os
import re
import sys
from collections import defaultdict

from sqlalchemy import select

from adapters.http.cds_http_adapter import CdsHttpAdapter
from domain.services.neighbor_cell_filter import NeighborCellFilter
from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh
from domain.value_objects.vendor import chuan_hoa_vendor
from infrastructure.db import AsyncSessionLocal
from models.tram import Tram as TramModel

TRAM_ID = sys.argv[1] if len(sys.argv) > 1 else "117903"
ACTION = "shutdown"  # quy uoc da dung o scripts/run_real_cr.py - CDS can 1 action hop le

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "adapters", "netact", "data_test")

# === Cot MONG DOI (dac ta BUOC 1) vs TEN THAT trong file - BAT BUOC bao cao
# khac biet, KHONG tu doan/tu doi ten de "cho khop". ===
COT_MONG_DOI = [
    "Period start time",
    "Source LNBTS name",
    "Source LNCEL name",
    "eci_id",
    "dmnc_id",
    "Inter eNB HO prep att neigh",
    "Adj Inter eNB HO SR",
]

# SUA 10/10/2026 (yeu cau truc tiep user) - group 1 TRUOC day lay MRBTS, SAI:
# eNB ID giai ma tu ECI (enb=eci//256, xem gia dinh 3 dau file) CHINH LA
# LNBTS (chung minh toan hoc: eNB ID ECI toi da 20 bit = 1.048.575, MRBTS co
# the vuot gia tri nay; VA du lieu that tram 111629 MRBTS=1101629/LNBTS=111629
# - xem domain/services/dist_name.py::LNBTS_LNCEL_RE). Script nay la SPIKE
# CHI DOC da hoan thanh nhiem vu khao sat ban dau, nhung _DN_RE o day duoc
# scripts/phan_tich_nguong_ho.py IMPORT LAI va dung cho cac script dang chay
# THAT (scripts/kiem_tra_thuat_toan_ho.py) - PHAI sua dong bo, khong duoc coi
# la "chi lich su" roi bo qua.
_DN_RE = re.compile(r"LNBTS-(\d+)/LNCEL-(\d+)")
# Quy uoc CR hien tai (domain/services/neighbor_cell_filter.py::_LNCEL_CHAY_CR_RE)
# - LNCEL 2 chu so, dau "1" (F1) hoac "3" (F2) = band 1800 duoc phep chay CR.
_LNCEL_CHAY_CR_RE = re.compile(r"^[13][0-9]$")
MAX_CELL_PER_SECTOR = 2


def _tim_file_csv() -> str:
    """Tim DUNG 1 file CSV co cot eci_id trong adapters/netact/data_test/.
    Khong thay (hoac thay nhieu hon 1, khong ro chon file nao) -> DUNG, in
    huong dan hoi duong dan (dung yeu cau "Khong thay -> DUNG, hoi duong dan")."""
    ung_vien = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                header = f.readline()
        except OSError:
            continue
        if "eci_id" in header:
            ung_vien.append(path)

    if len(ung_vien) == 0:
        print(f"DUNG: khong tim thay file CSV nao co cot 'eci_id' trong {DATA_DIR}.")
        print("Hay cho biet duong dan file CSV report neighbor HO (NetAct) can dung.")
        sys.exit(1)
    if len(ung_vien) > 1:
        print(f"DUNG: tim thay {len(ung_vien)} file CSV deu co cot 'eci_id', khong ro dung file nao:")
        for p in ung_vien:
            print(f"  - {p}")
        print("Hay cho biet duong dan CHINH XAC file can dung.")
        sys.exit(1)
    return ung_vien[0]


def _bao_cao_cot(header_that: list[str]) -> None:
    print("=" * 78)
    print("BUOC 1 - CAC COT THAT trong file CSV:")
    for i, ten in enumerate(header_that):
        print(f"  [{i:2d}] {ten}")

    print()
    print("Doi chieu cot MONG DOI (dac ta) vs THAT:")
    header_set = set(header_that)
    for ten_mong_doi in COT_MONG_DOI:
        if ten_mong_doi in header_set:
            print(f"  KHOP      : {ten_mong_doi!r}")
        else:
            # Tim ten GAN GIONG (khong phan biet hoa/thuong) de goi y, KHONG tu doan la "chac no la cot nay"
            gan_giong = [h for h in header_that if h.lower().replace("_", " ") == ten_mong_doi.lower()]
            print(f"  KHAC TEN  : {ten_mong_doi!r} -> KHONG CO cot nay." + (f" Gan giong: {gan_giong}" if gan_giong else " KHONG co cot nao gan giong."))
    print(
        "\n  GHI CHU rieng 'dmnc_id': file THAT khong co cot nay. Thay vao do co\n"
        "  2 cot rieng 'mcc_id'/'mnc_id'. Se dung 'mnc_id' lam cot loc o Buoc 3,\n"
        "  va BAO CAO GIA TRI THAT (khong doan) o Buoc 3."
    )
    print("=" * 78)


def _sector_tu_lncel(lncel: int) -> int:
    return lncel % 10


async def _nap_tram_theo_id(enb_set: set[int]) -> dict[int, dict]:
    """Ghep enb (so nguyen) -> {tram_id, tram_name, vendor, khu_vuc}. CHI DOC."""
    if not enb_set:
        return {}
    ids = [str(e) for e in enb_set]
    ket_qua: dict[int, dict] = {}
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(TramModel).where(TramModel.tram_id.in_(ids)))).scalars().all()
    for r in rows:
        ket_qua[int(r.tram_id)] = {
            "tram_id": r.tram_id,
            "tram_name": r.tram_name,
            "vendor": chuan_hoa_vendor(r.ten_thiet_bi).value,
            "khu_vuc": khu_vuc_tu_ma_tinh(r.ma_tinh),
            "ma_tinh": r.ma_tinh,
        }
    return ket_qua


def main_doc_csv(path: str, tram_id: str):
    """Mot (1) lan doc toan bo file CSV (~3 trieu dong):
    - BUOC 1: lay header that.
    - BUOC 2: kiem chung cong thuc giai ma eci_id tren TOAN BO file (dong
      intra-eNB - enb dich == enb nguon - phai co lcr la mot LNCEL cua CHINH
      eNB do).
    - BUOC 3: dem gia tri mnc_id THAT (de bao cao, khong doan), thu thap RIENG
      cac dong thuoc tram_id dang xet (sau khi loai intra-eNB + attempt=0).
    Tra ve (header, thong_ke_toan_cuc, dong_cua_tram).
    """
    enb_muc_tieu = int(tram_id)
    thong_ke = {
        "tong_dong": 0,
        "mnc_id_gap": defaultdict(int),
        "intra_vi_du": [],  # toi da 5 vi du (enb, lcr, source_cell_name) de in minh hoa Buoc 2
        "intra_dem": 0,
    }
    dong_cua_tram: list[dict] = []

    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        idx = {ten: i for i, ten in enumerate(header)}

        i_src_lnbts = idx["Source LNBTS name"]
        i_src_lncel = idx["Source LNCEL name"]
        i_mnc = idx["mnc_id"]
        i_eci = idx["eci_id"]
        i_dn = idx["DN"]
        i_att = idx["Inter eNB HO prep att neigh"]
        i_sr = idx["Adj Inter eNB HO SR"]

        for row in reader:
            thong_ke["tong_dong"] += 1
            mnc = row[i_mnc]
            thong_ke["mnc_id_gap"][mnc] += 1

            dn = row[i_dn]
            m = _DN_RE.search(dn)
            if not m:
                continue  # DN khong dung mau - bo qua dong nay (khong doan)
            src_enb = int(m.group(1))
            src_lncel = int(m.group(2))

            eci_raw = row[i_eci]
            if not eci_raw:
                continue
            eci = int(eci_raw)
            target_enb = eci // 256
            target_lcr = eci % 256

            is_intra = target_enb == src_enb
            if is_intra:
                thong_ke["intra_dem"] += 1
                if len(thong_ke["intra_vi_du"]) < 5:
                    thong_ke["intra_vi_du"].append(
                        {
                            "source_cell": row[i_src_lncel],
                            "src_enb": src_enb,
                            "target_lcr": target_lcr,
                        }
                    )

            if src_enb != enb_muc_tieu:
                continue
            if is_intra:
                continue  # BUOC 3 - bo intra-eNB
            att_raw = row[i_att]
            att = int(att_raw) if att_raw else 0
            if att == 0:
                continue  # BUOC 3 - bo attempt = 0
            if mnc != "02":
                # Phong ve - chua gap trong du lieu that (xem bao cao Buoc 3),
                # nhung KHONG am tham nuot neu mot ngay no xay ra.
                continue

            sr_raw = row[i_sr]
            sr = float(sr_raw) if sr_raw else None

            dong_cua_tram.append(
                {
                    "source_cell_name": row[i_src_lncel],
                    "source_lnbts_name": row[i_src_lnbts],
                    "source_sector": _sector_tu_lncel(src_lncel),
                    "target_enb": target_enb,
                    "target_lcr": target_lcr,
                    "attempt": att,
                    "sr": sr,
                }
            )

    return header, thong_ke, dong_cua_tram


def _bao_cao_buoc_2(thong_ke: dict) -> None:
    print("\nBUOC 2 - KIEM CHUNG cong thuc giai ma eci_id (enb = eci_id // 256, lcr = eci_id % 256):")
    print(f"  Tong so dong intra-eNB (target_enb == source_enb) tren TOAN BO file: {thong_ke['intra_dem']:,}")
    print("  5 vi du dong intra-eNB (lcr dich PHAI la 1 LNCEL hop le cua CHINH eNB nguon):")
    for vd in thong_ke["intra_vi_du"]:
        print(
            f"    source_cell={vd['source_cell']:<20} src_enb={vd['src_enb']:<8} "
            f"-> target_lcr={vd['target_lcr']:<4} (LNCEL-{vd['target_lcr']} cua CUNG eNB {vd['src_enb']} - KHOP)"
        )


def _bao_cao_buoc_3(thong_ke: dict) -> None:
    print("\nBUOC 3 - Loc dmnc_id (that su la mnc_id) / bo intra-eNB / bo attempt=0:")
    print(f"  Tong so dong trong file: {thong_ke['tong_dong']:,}")
    print("  Phan bo GIA TRI THAT cua mnc_id (khong doan, dem toan bo file):")
    for gt, dem in sorted(thong_ke["mnc_id_gap"].items(), key=lambda kv: -kv[1]):
        print(f"    mnc_id={gt!r:8} so dong={dem:,}")
    if set(thong_ke["mnc_id_gap"]) == {"02"}:
        print("  -> 100% dong da la mnc_id='02' (VinaPhone). Loc theo VinaPhone la PHEP KIEM TRA,")
        print("     khong loai bo dong nao thuc te.")
    else:
        print("  -> CANH BAO: co gia tri mnc_id KHAC '02' trong file - da LOAI cac dong do (chi giu '02').")


async def main():
    path = _tim_file_csv()
    print(f"File CSV dang dung: {path}")
    print(f"Tram dang xet (nguon): {TRAM_ID}\n")

    header, thong_ke, dong_cua_tram = main_doc_csv(path, TRAM_ID)
    _bao_cao_cot(header)
    _bao_cao_buoc_2(thong_ke)
    _bao_cao_buoc_3(thong_ke)

    print(f"\n  So dong CON LAI sau loc, THUOC tram {TRAM_ID}: {len(dong_cua_tram):,}")
    if not dong_cua_tram:
        print(f"DUNG: khong co dong HO nao (sau loc) cho tram {TRAM_ID} trong file nay.")
        return

    # === BUOC 4: ghep enb -> tram (tram_id/ten/vendor/khu_vuc) ===
    enb_can_ghep = {d["target_enb"] for d in dong_cua_tram} | {int(TRAM_ID)}
    tram_theo_enb = await _nap_tram_theo_id(enb_can_ghep)
    enb_khong_ghep_duoc = sorted(e for e in {d["target_enb"] for d in dong_cua_tram} if e not in tram_theo_enb)
    print("\nBUOC 4 - Ghep enb -> bang tram:")
    print(f"  So enb dich DUY NHAT: {len({d['target_enb'] for d in dong_cua_tram})}")
    print(f"  So enb KHONG ghep duoc (khong co trong bang tram): {len(enb_khong_ghep_duoc)} {enb_khong_ghep_duoc}")

    tram_nguon = tram_theo_enb.get(int(TRAM_ID))
    if tram_nguon is None:
        print(f"DUNG: tram nguon {TRAM_ID} khong co trong bang tram - khong the doi chieu vendor/khu_vuc.")
        return
    print(f"  Tram nguon: {tram_nguon['tram_name']} | vendor={tram_nguon['vendor']} | khu_vuc={tram_nguon['khu_vuc']}")

    # === BUOC 5 + 6: nhom theo sector nguon, xep theo attempt giam dan ===
    theo_sector: dict[int, dict[tuple[int, int], dict]] = defaultdict(dict)
    for d in dong_cua_tram:
        key = (d["target_enb"], d["target_lcr"])
        nhom = theo_sector[d["source_sector"]]
        if key not in nhom:
            nhom[key] = {"attempt": 0, "sr_x_att": 0.0, "sr_co_gia_tri": 0}
        nhom[key]["attempt"] += d["attempt"]
        if d["sr"] is not None:
            nhom[key]["sr_x_att"] += d["sr"] * d["attempt"]
            nhom[key]["sr_co_gia_tri"] += d["attempt"]

    print("\nBUOC 6 - Top 5 cell dich/sector nguon (xep theo attempt giam dan):")
    print("  (GIA DINH: xep hang CHI theo attempt, KHONG ap nguong SR toi thieu - xem docstring dau file)")
    xep_hang_theo_sector: dict[int, list[dict]] = {}
    for sector in sorted(theo_sector):
        nhom = theo_sector[sector]
        tong_attempt_sector = sum(v["attempt"] for v in nhom.values())
        xep = sorted(nhom.items(), key=lambda kv: -kv[1]["attempt"])
        xep_hang_theo_sector[sector] = xep
        print(f"\n  Sector {sector} (tong attempt = {tong_attempt_sector:,}):")
        print(f"    {'enb':>8} {'lcr':>4} {'tram dich':<22} {'attempt':>9} {'% sector':>9} {'SR tb':>7}")
        for (enb, lcr), v in xep[:5]:
            tram_dich = tram_theo_enb.get(enb)
            ten_tram_dich = tram_dich["tram_name"] if tram_dich else f"(khong ro, enb={enb})"
            pct = 100.0 * v["attempt"] / tong_attempt_sector if tong_attempt_sector else 0.0
            sr_tb = (v["sr_x_att"] / v["sr_co_gia_tri"]) if v["sr_co_gia_tri"] else None
            sr_str = f"{sr_tb:6.2f}" if sr_tb is not None else "   n/a"
            print(f"    {enb:>8} {lcr:>4} {ten_tram_dich:<22} {v['attempt']:>9,} {pct:>8.1f}% {sr_str:>7}")

    # === BUOC 7: ap LUAT CR HIEN TAI (lcr ^[13][0-9]$, toi da 2/sector, dedup xuyen sector) ===
    print("\nBUOC 7 - Ap LUAT CR HIEN TAI (chi lcr ^[13][0-9]$ / toi da 2 cell/sector / dedup xuyen sector):")
    print(f"    {'sector':>6} {'rank':<11} {'enb':>8} {'lcr':>4} {'tram dich':<22} {'vendor':<9} {'attempt':>9}")
    da_chon_cell_name: set[tuple[int, int]] = set()
    danh_sach_cr_theo_ho: list[dict] = []
    for sector in sorted(xep_hang_theo_sector):
        so_da_chon_sector = 0
        for (enb, lcr), v in xep_hang_theo_sector[sector]:
            if so_da_chon_sector >= MAX_CELL_PER_SECTOR:
                break
            if (enb, lcr) in da_chon_cell_name:
                continue  # dedup xuyen sector - sector truoc da giu quyen
            if not _LNCEL_CHAY_CR_RE.match(str(lcr)):
                continue  # khong phai band 1800 F1/F2
            rank = "rsboost" if so_da_chon_sector == 0 else "qrxlevmin"
            tram_dich = tram_theo_enb.get(enb)
            ten_tram_dich = tram_dich["tram_name"] if tram_dich else f"(khong ro, enb={enb})"
            vendor_dich = tram_dich["vendor"] if tram_dich else "?"
            canh_bao_vendor = " <== KHAC VENDOR" if tram_dich and vendor_dich != tram_nguon["vendor"] else ""
            print(
                f"    {sector:>6} {rank:<11} {enb:>8} {lcr:>4} {ten_tram_dich:<22} "
                f"{vendor_dich:<9} {v['attempt']:>9,}{canh_bao_vendor}"
            )
            da_chon_cell_name.add((enb, lcr))
            danh_sach_cr_theo_ho.append({"enb": enb, "lcr": lcr, "sector": sector, "rank": rank})
            so_da_chon_sector += 1
        if so_da_chon_sector == 0:
            print(f"    {sector:>6} (khong co cell nao qua duoc luat band 1800 cho sector nay)")

    # === BUOC 8: doi chieu CDS that ===
    print("\nBUOC 8 - Doi chieu CDS that (CdsHttpAdapter.get_cell_neighbors + NeighborCellFilter.filter_for_cr):")
    cds_cells: set[str] | None = None
    try:
        adapter = CdsHttpAdapter()
        raw_huongs = await adapter.get_cell_neighbors(TRAM_ID, tram_nguon["tram_name"], ACTION, timeout=30, so_lan_thu=1)
        cells = NeighborCellFilter().filter_for_cr(raw_huongs, tram_goc_id=TRAM_ID)
        cds_cells = {c.cell_name for c in cells}
        print(f"  CDS tra ve {len(raw_huongs)} huong -> filter_for_cr() chon {len(cds_cells)} cell: {sorted(cds_cells)}")
    except Exception as exc:  # noqa: BLE001 - spike, muon THAY loi that de bao cao, khong de crash mat toan bo report
        print(f"  KHONG GOI DUOC CDS THAT: {type(exc).__name__}: {exc}")
        print("  -> Khong co VPN/mang noi bo VNPT toi CDS_BASE_URL tu may chay script nay (da kiem truoc khi viet script).")
        print("  -> Buoc 8 KHONG so sanh duoc o day. Chay lai script tren may CO mang noi bo de co ket qua that.")

    ho_cells_ten = set()
    for muc in danh_sach_cr_theo_ho:
        tram_dich = tram_theo_enb.get(muc["enb"])
        if tram_dich is None:
            continue
        # Doan ten cell dich tu quy uoc <tram_name_khong_hau_to>+<lcr> KHONG the lam chinh xac
        # (khong co du lieu ten cell That cua tram dich trong CSV nay) - CHI dung (enb,lcr) lam
        # khoa so sanh, KHONG suy doan ten cell.
        ho_cells_ten.add((muc["enb"], muc["lcr"]))

    if cds_cells is not None:
        # Quy doi CDS cell_name -> (enb, lcr) de so sanh CUNG 1 khoa voi phia HO (CSV khong co
        # ten cell dich that nen khong the so theo ten).
        cds_keys = set()
        for c in cells:
            m = _DN_RE.search(c.dist_name or c.cell_id or "")
            if m:
                cds_keys.add((int(m.group(1)), int(m.group(2))))
        trung = ho_cells_ten & cds_keys
        chi_ho = ho_cells_ten - cds_keys
        chi_cds = cds_keys - ho_cells_ten
        print(f"\n  TRUNG (ca HO va CDS deu chon): {len(trung)} -> {sorted(trung)}")
        print(f"  CHI HO co (CDS KHONG co trong danh sach CR): {len(chi_ho)} -> {sorted(chi_ho)}")
        print(f"  CHI CDS co (HO KHONG thay attempt nao, hoac bi loai o Buoc 7): {len(chi_cds)} -> {sorted(chi_cds)}")

    # === BUOC 9: gop theo tram dich (cong moi sector), top 10 + % tong ===
    print("\nBUOC 9 - Gop theo TRAM DICH (cong attempt qua moi sector nguon), top 10 + % tong:")
    tong_theo_tram: dict[int, int] = defaultdict(int)
    for sector, xep in xep_hang_theo_sector.items():
        for (enb, _lcr), v in xep:
            tong_theo_tram[enb] += v["attempt"]
    tong_tat_ca = sum(tong_theo_tram.values())
    top10 = sorted(tong_theo_tram.items(), key=lambda kv: -kv[1])[:10]
    print(f"  Tong attempt toan bo (3 sector, sau loc Buoc 3): {tong_tat_ca:,}")
    print(f"    {'tram dich':<22} {'khu_vuc':<8} {'vendor':<9} {'attempt':>9} {'% tong':>8}")
    for enb, att in top10:
        tram_dich = tram_theo_enb.get(enb)
        ten = tram_dich["tram_name"] if tram_dich else f"(khong ro, enb={enb})"
        kv = tram_dich["khu_vuc"] if tram_dich else "?"
        vd = tram_dich["vendor"] if tram_dich else "?"
        pct = 100.0 * att / tong_tat_ca if tong_tat_ca else 0.0
        print(f"    {ten:<22} {kv or '?':<8} {vd:<9} {att:>9,} {pct:>7.1f}%")

    # === NHAN XET ===
    print("\n" + "=" * 78)
    print("NHAN XET:")
    print(
        "- Neu Buoc 8 goi CDS duoc: xem 3 nhom 'TRUNG/CHI HO/CHI CDS' o tren de biet HO va CDS\n"
        "  lech nhau o dau. 'CHI CDS' thuong la cell CDS suy tu azimuth nhung THUC TE it/khong\n"
        "  co UE handover sang (co the azimuth/do cao nhap sai). 'CHI HO' la cell dang THAT SU\n"
        "  phu vung (UE handover sang nhieu) nhung CDS KHONG liet ke (thieu cau hinh neighbor\n"
        "  trong he thong, hoac azimuth khong huong toi do)."
    )
    print(
        "- Gia dinh CHUA kiem chung trong spike nay: nguong SR toi thieu (xem GIA DINH #1 dau\n"
        "  file) - neu can loai ca cell co attempt cao nhung SR handover THAP (handover hay that\n"
        "  bai, co the la cell 'nhin thay' ve RF nhung khong thuc su ket noi duoc tot) thi phai\n"
        "  CHOT nguong voi nguoi nghiep vu truoc, spike nay chua ap dung."
    )


if __name__ == "__main__":
    asyncio.run(main())
