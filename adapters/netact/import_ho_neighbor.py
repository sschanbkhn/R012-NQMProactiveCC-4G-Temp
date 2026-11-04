"""
adapters/netact/import_ho_neighbor.py

Doc file report HO (handover) neighbor tu NetAct (CSV, dau phan cach ";",
~3 trieu dong/lan export) va nap vao bang ho_neighbor - thay the hoan toan
CDS /cell/neighbors (quyet dinh 06-08/10/2026, yeu cau truc tiep user). Xem
models/ho_neighbor.py va docs/BUSINESS_RULES.md ve ly do/nguong.

CACH DOC FILE + GIAI MA ECI: TAI SU DUNG (khong phai import, vi adapters/
khong nen phu thuoc scripts/ - lop cong cu doc lap) chinh XAC cach lam cua
scripts/spike_ho_neighbor.py (da kiem chung bang du lieu that: 143.112 dong
intra-eNB, 5 vi du khop 100% - xem Buoc 2 file do):
    enb   = eci_id // 256   (CHINH LA LNBTS - SUA 10/10/2026, xem _DN_RE duoi day)
    lcr   = eci_id % 256
    sector = (LNCEL ID nguon, tu cot DN) % 10

=== NAP DAY DU (SUA 08/10/2026 lan 4, yeu cau truc tiep user) ===
TRUOC: chi luu TOP 20 cell dich/cell nguon trong DB (de gon bang), file CSV
goc duoc CHEP luu rieng (HO_RAW_ARCHIVE_DIR) cho cac script dieu tra can doc
lai toan bo. NAY: BO han cat top-N - nap TOAN BO cap (source, dich) HOP LE
vao DB, KHONG can luu file CSV goc nua (DB da la nguon day du). Ly do: can
PHAN TICH/HIEU CHINH/UOC LUONG VI TRI CELL bang SQL truc tiep tren DB (vd
GROUP BY/thong ke phan phoi tren TOAN BO quan he, khong chi top 20) - cat
top-N tu truoc se mat du lieu can cho muc dich nay.

LOC (giu lai, KHONG doi so voi truoc - chi BO cat top-N):
    - dong intra-eNB (target_enb == source_enb)
    - dong attempt = 0
    - cell nguon co ID KHONG dung 2 chu so (nhom "MBF_...", %10 se ra sector
      SAI - xem scripts/phan_tich_nguong_ho.py muc 4, da xac nhan 560/560
      cell nguon ID 3 chu so deu la MBF_)
    - mnc_id khac "02" (VinaPhone) - PHONG VE them (khao sat
      scripts/spike_ho_neighbor.py Buoc 3 tren file NA09 that: 100% dong da
      la mnc_id="02", nen filter nay hien KHONG loai gi tren du lieu that,
      nhung GIU lam luoi an toan truoc file tuong lai/NetAct khac co the
      lan ca thue bao mang khac).

XOA + NAP LAI THEO NETACT: file export la snapshot DAY DU 1 lan chay cua 1
NetAct, KHONG phai incremental - XOA sach dong cu CUNG netact TRUOC khi nap,
tranh con sot du lieu lan truoc lan voi lan nay (vd 1 cell nguon lan truoc co
HO, lan nay khong con nua se "ket thuc vinh vien" neu khong xoa).

=== NAP BANG COPY (SUA 08/10/2026 lan 4) ===
Nap day du (khong con cat top-N) co the la HANG TRAM NGHIN - TRIEU dong/lan -
executemany() (INSERT tung dong qua giao thuc extended query) qua cham o quy
mo nay. Dung `asyncpg.Connection.copy_records_to_table()` (giao thuc COPY
nhi phan cua Postgres, nhanh hon INSERT hang loat rat nhieu). XOA + COPY nam
TRONG CUNG 1 transaction (`conn.transaction()`) - loi o BUOC NAO (ca COPY) se
ROLLBACK TOAN BO, du lieu cu cua netact van con nguyen (khong bao gio o trang
thai "da xoa nhung chua nap xong").

Chay:
    python adapters/netact/import_ho_neighbor.py --file <ten_hoac_duong_dan> --netact NA09 [--dry-run]
    python adapters/netact/import_ho_neighbor.py --chi-tinh-cran --netact NA10
        (SUA 15/10/2026, yeu cau truc tiep user: KHONG nap lai HO, chi TINH LAI
        bang cell_vi_tri_uoc_luong tu ho_neighbor dang co san trong DB cho
        netact nay - dung sau khi sua logic phan_loai_toa_do()/_SITE_RE, hoac
        khi lan nap truoc bi loi giua chung o buoc tinh CRAN - xem muc SUA
        LOI SYS.PATH duoi day.)
"""

import argparse
import csv
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

# SUA 15/10/2026 (yeu cau truc tiep user) - BUG tu commit 340206b (10/10/2026,
# them tinh_va_ghi_vi_tri_cran() voi import TUYET DOI "adapters.postgres...").
# Khi chay TRUC TIEP "python adapters/netact/import_ho_neighbor.py" (dung
# cach huong dan Chay: o tren), Python dat sys.path[0] = thu muc CUA FILE NAY
# (adapters/netact/), KHONG PHAI goc repo - import tuyet doi "adapters.*"/
# "domain.*"/"infrastructure.*" se ModuleNotFoundError NGAY KHI buoc tinh
# CRAN chay toi (xoa_va_nap() TRUOC do khong loi vi dung asyncpg/dotenv thuan,
# khong import goi noi bo nao - xem ham do). THEM goc repo vao sys.path o DAY
# (truoc moi import lazy ben duoi dua vao no) de script chay dung NHU TAI
# LIEU "Chay:" o tren mo ta, khong can "python -m".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DEFAULT_DATA_DIR = Path(__file__).parent / "data_test"

# mnc_id hop le duy nhat da xac nhan tren du lieu that (VinaPhone) - xem
# scripts/spike_ho_neighbor.py Buoc 3.
MNC_HOP_LE = "02"

# Cot BAT BUOC phai co trong file - kiem TRUOC khi doc du lieu, KHONG doan
# ten cot gan giong (dung tinh than "ten khac -> bao cao, khong tu doan" da
# ap dung xuyen suot cac spike truoc).
COT_BAT_BUOC = [
    "PERIOD_START_TIME",
    "Source LNBTS name",
    "Source LNCEL name",
    "eci_id",
    "mnc_id",
    "DN",
    "Inter eNB HO prep att neigh",
    "Adj Inter eNB HO SR",
]

# SUA 10/10/2026 (yeu cau truc tiep user, CHUNG MINH BANG TOAN HOC + DU LIEU
# THAT - xem domain/services/dist_name.py::LNBTS_LNCEL_RE): source_enb PHAI
# la LNBTS (KHONG phai MRBTS nhu ban truoc) - vi eNB ID giai ma tu ECI
# (target_enb = eci//256, dong Buoc 2 duoi day) CHINH LA LNBTS (eNB ID ECI
# toi da 20 bit = 1.048.575, MRBTS co the vuot qua gia tri nay nen KHONG THE
# la nguon cua ECI). TRUOC sua dung MRBTS lam source_enb: luat loc intra-eNB
# (`target_enb == source_enb` duoi day) SE KHONG BAO GIO dung cho 2,67% tram
# co MRBTS != LNBTS (so sanh "tao" voi "cam", 2 khong gian ID khac nhau) -
# dong intra-eNB cua cac tram do bi LOT LUOI, bi nap NHAM vao ho_neighbor
# nhu 1 "neighbor" INTER-eNB that (sai nghiem trong, lam phinh/sai danh sach
# B cho chinh TRAM DO khi no la nguon).
_DN_RE = re.compile(r"LNBTS-(\d+)/LNCEL-(\d+)")


def _parse_ngay(chuoi: str) -> date:
    # Dang that trong file: "09.28.2026" (MM.DD.YYYY) - da xac nhan qua
    # khao sat truoc (scripts/spike_ho_neighbor.py, scripts/phan_tich_nguong_ho.py).
    return datetime.strptime(chuoi, "%m.%d.%Y").date()


def doc_csv(path: Path) -> tuple[date, list[dict]]:
    """Tra (ngay_du_lieu, danh_sach_dong_da_loc_va_gop). Dong da giai ma san
    (target_enb/target_lcr/source_sector), gop theo (source_enb,
    source_sector, target_enb, target_lcr) - KHONG cat top-N (SUA 08/10/2026
    lan 4, xem docstring dau file).

    GOP THEO SECTOR (khong phai theo tung source_lncel_name rieng, SUA
    08/10/2026 lan 4 - phat hien qua chay THAT tren file NA09 day du): 2 cell
    nguon VAT LY khac nhau (vd 2 band) co the CUNG mot sector (%10 trung) va
    CUNG handover toi 1 cell dich - neu gop theo ten cell nguon rieng se tao
    2 dong (netact, source_enb, source_sector, target_enb, target_lcr) GIONG
    HET nhau (UniqueViolationError khi COPY, da gap that khi chay day du -
    KHONG xay ra voi ban top-20 cu vi it khi ca 2 cell cung lot top 20 toi
    CUNG 1 dich). Ca thuat toan chon cell (domain/services/ho_cell_selector.py)
    CUNG CHI gom theo source_sector (khong phan biet source_lncel_name khi
    tinh %/xep hang) nen gop som o day la DUNG BAN CHAT, khong mat thong tin
    co y nghia. source_lncel_name luu lai la TEN DAI DIEN (cell dong gop
    NHIEU ho_attempt nhat trong sector do) - chi dung de hien thi/phong ve
    MBF_ 2 lop (xem domain/services/ho_cell_selector.py), khong anh huong
    tinh toan."""
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        thieu = [c for c in COT_BAT_BUOC if c not in header]
        if thieu:
            print(f"DUNG: file thieu cot bat buoc: {thieu}", file=sys.stderr)
            print(f"  Cot THAT trong file: {header}", file=sys.stderr)
            sys.exit(1)

        idx = {ten: i for i, ten in enumerate(header)}
        i_period = idx["PERIOD_START_TIME"]
        i_src_lncel = idx["Source LNCEL name"]
        i_eci = idx["eci_id"]
        i_mnc = idx["mnc_id"]
        i_dn = idx["DN"]
        i_att = idx["Inter eNB HO prep att neigh"]
        i_sr = idx["Adj Inter eNB HO SR"]

        ngay_du_lieu: date | None = None
        # Gop theo (source_enb, source_sector, target_enb, target_lcr) - xem
        # docstring doc_csv() ve ly do gop THEO SECTOR (khong phai theo tung
        # source_lncel_name). "ten" trong tung nhom: {ten -> tong_attempt}
        # de chon TEN DAI DIEN (xem cuoi ham) sau khi doc het file.
        theo_nguon: dict[tuple[int, int], dict] = {}

        tong_dong, giu_lai = 0, 0
        for row in reader:
            tong_dong += 1
            if ngay_du_lieu is None and row[i_period]:
                ngay_du_lieu = _parse_ngay(row[i_period])

            if row[i_mnc] != MNC_HOP_LE:
                continue  # BO: mnc_id khac VinaPhone (xem MNC_HOP_LE dau file)

            dn = row[i_dn]
            m = _DN_RE.search(dn)
            if not m:
                continue
            src_enb = int(m.group(1))
            src_lncel_str = m.group(2)
            if len(src_lncel_str) != 2:
                continue  # BO: ID nguon khong dung 2 chu so (nhom MBF_)

            eci_raw = row[i_eci]
            if not eci_raw:
                continue
            eci = int(eci_raw)
            target_enb, target_lcr = eci // 256, eci % 256
            if target_enb == src_enb:
                continue  # BO intra-eNB

            att_raw = row[i_att]
            att = int(att_raw) if att_raw else 0
            if att == 0:
                continue  # BO attempt = 0

            sr_raw = row[i_sr]
            sr = float(sr_raw) if sr_raw else None
            sector = int(src_lncel_str) % 10
            src_lncel_name = row[i_src_lncel]

            khoa_nguon = (src_enb, sector)
            nhom = theo_nguon.setdefault(khoa_nguon, {"dich": {}, "ten_attempt": {}})
            nhom["ten_attempt"][src_lncel_name] = nhom["ten_attempt"].get(src_lncel_name, 0) + att
            khoa_dich = (target_enb, target_lcr)
            d = nhom["dich"].setdefault(khoa_dich, {"attempt": 0, "sr_x_att": 0.0, "sr_w": 0, "eci": eci})
            d["attempt"] += att
            if sr is not None:
                d["sr_x_att"] += sr * att
                d["sr_w"] += att
            giu_lai += 1

        print(f"Tong so dong doc duoc: {tong_dong:,}; dong qua loc (truoc khi gop trung cap nguon/dich): {giu_lai:,}")
        if ngay_du_lieu is None:
            print("DUNG: khong doc duoc PERIOD_START_TIME tu bat ky dong nao.", file=sys.stderr)
            sys.exit(1)

        ket_qua: list[dict] = []
        for (src_enb, sector), nhom in theo_nguon.items():
            # Ten DAI DIEN = cell nguon dong gop NHIEU ho_attempt nhat trong
            # sector nay (xem docstring doc_csv()) - DUNG khi sector nay co
            # >= 2 cell nguon vat ly khac nhau (da gop chung o day).
            ten_dai_dien = max(nhom["ten_attempt"].items(), key=lambda kv: kv[1])[0]
            for (target_enb, target_lcr), d in nhom["dich"].items():
                sr_tb = (d["sr_x_att"] / d["sr_w"]) if d["sr_w"] > 0 else None
                ket_qua.append({
                    "source_enb": src_enb,
                    "source_lncel_name": ten_dai_dien,
                    "source_sector": sector,
                    "target_eci": d["eci"],
                    "target_enb": target_enb,
                    "target_lcr": target_lcr,
                    "ho_attempt": d["attempt"],
                    "ho_sr": sr_tb,
                })
        return ngay_du_lieu, ket_qua


async def xoa_va_nap(netact: str, ngay_du_lieu: date, rows: list[dict], dry_run: bool) -> None:
    if dry_run:
        for r in rows[:20]:
            print(f"[NAP] netact={netact} {r}")
        print(f"\nTong: {len(rows)} dong se duoc nap cho netact={netact} ngay_du_lieu={ngay_du_lieu} "
              f"(dry-run, CHUA ghi DB that; {len(rows[:20])} dong dau da in o tren)")
        return

    import os

    import asyncpg
    from dotenv import load_dotenv

    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Khong tim thay DATABASE_URL trong .env", file=sys.stderr)
        sys.exit(1)
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    # created_at: 1 gia tri DUY NHAT cho CA LAN nap (giong y nghia `now()`
    # trong 1 cau SQL duy nhat o ban truoc) - KHONG dung server-side default
    # vi COPY khong goi expression DEFAULT cua cot (phai dien gia tri tu phia
    # client cho MOI dong).
    tao_luc = datetime.now(timezone.utc)
    records = [
        (netact, ngay_du_lieu, r["source_enb"], r["source_lncel_name"], r["source_sector"],
         r["target_eci"], r["target_enb"], r["target_lcr"], r["ho_attempt"], r["ho_sr"], tao_luc)
        for r in rows
    ]

    conn = await asyncpg.connect(dsn)
    try:
        t0 = time.monotonic()
        async with conn.transaction():
            # XOA SACH du lieu CU CUA NETACT DO truoc khi nap lai (xem docstring
            # dau file - file la snapshot DAY DU, khong phai incremental). XOA +
            # COPY trong CUNG 1 transaction - loi o buoc nao (ke ca COPY) se
            # ROLLBACK TOAN BO, du lieu cu van con nguyen.
            da_xoa = await conn.execute(
                "DELETE FROM system_nsn_nqmproactivecc.ho_neighbor WHERE netact = $1", netact
            )
            await conn.copy_records_to_table(
                "ho_neighbor",
                schema_name="system_nsn_nqmproactivecc",
                records=records,
                columns=[
                    "netact", "ngay_du_lieu", "source_enb", "source_lncel_name", "source_sector",
                    "target_eci", "target_enb", "target_lcr", "ho_attempt", "ho_sr", "created_at",
                ],
            )
        thoi_gian_s = time.monotonic() - t0
        print(
            f"Da xoa du lieu cu ({da_xoa}) va COPY {len(rows):,} dong cho netact={netact}, "
            f"ngay_du_lieu={ngay_du_lieu} trong {thoi_gian_s:.2f}s"
        )
    finally:
        await conn.close()


async def tinh_va_ghi_vi_tri_cran(netact: str, ngay_du_lieu: date, rows: list[dict]) -> None:
    """BUOC 4c (10/10/2026, yeu cau truc tiep user) - uoc luong vi tri CELL
    cua tram TOA_DO_DUNG_CHUNG (CRAN), tinh NGAY SAU KHI nap ho_neighbor
    (goi tu main(), SAU xoa_va_nap() thanh cong). CHI DE HIEN THI (xem WHY
    day du o domain/services/cran_vi_tri_estimator.py) - KHONG anh huong
    thuat toan chon cell.

    SUA 15/10/2026 (yeu cau truc tiep user): TRUOC day loi o day bi NUOT
    (chi in [CANH BAO] roi script van exit 0) - 1 lan nap NA10 da "loi giua
    chung" ma KHONG AI BIET (ho_neighbor nap dung, nhung cell_vi_tri_uoc_luong
    khong duoc cap nhat, exit code 0 nhu thanh cong). NAY: KHONG tu bat loi o
    day nua - de exception truyen THANG len main(), main() moi la noi QUYET
    DINH exit code (ho_neighbor van da nap xong/khong rollback, nhung script
    PHAI bao loi ro + exit != 0 de script/CI goi no biet buoc nay that bai)."""
    from adapters.postgres.cell_vi_tri_uoc_luong_repo import CellViTriUocLuongRepo
    from adapters.postgres.enodeb_repo import EnodebRepo
    from domain.services.cran_vi_tri_estimator import uoc_luong_vi_tri_cran
    from domain.services.ho_delaunay import TOA_DO_DUNG_CHUNG, TramDiem, phan_loai_toa_do
    from infrastructure.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tram_rows = await EnodebRepo(session).get_all_with_coords()
        tram_diem_list = [
            TramDiem(tram_id=r["tram_id"], tram_name=r["tram_name"], lat=r["latitude"], lon=r["longitude"])
            for r in tram_rows
        ]
        phan_loai = phan_loai_toa_do(tram_diem_list)
        tram_coords: dict[int, tuple[float, float]] = {}
        for r in tram_rows:
            try:
                tram_coords[int(r["tram_id"])] = (r["latitude"], r["longitude"])
            except (ValueError, TypeError):
                continue

        ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)
        await CellViTriUocLuongRepo(session).xoa_va_ghi(netact, ngay_du_lieu, ket_qua)

    so_cell_cran = sum(
        1 for (enb, _sector) in {(r["source_enb"], r["source_sector"]) for r in rows}
        if phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG
    )
    if so_cell_cran:
        print(
            f"Da tinh vi tri uoc luong CRAN: {len(ket_qua):,}/{so_cell_cran:,} cell CRAN "
            f"({100.0 * len(ket_qua) / so_cell_cran:.1f}% uoc luong duoc)"
        )
    else:
        print(f"Da tinh vi tri uoc luong CRAN: {len(ket_qua):,} (khong co cell CRAN nao trong lan nap nay)")


async def _doc_rows_tu_db(netact: str) -> tuple[date, list[dict]]:
    """THEM 15/10/2026 (yeu cau truc tiep user, che do --chi-tinh-cran) - doc
    LAI ho_neighbor dang co san trong DB cho 1 netact (KHONG doc file CSV) -
    dung khi can TINH LAI cell_vi_tri_uoc_luong sau khi sua logic
    phan_loai_toa_do()/_SITE_RE (domain/services/ho_delaunay.py) ma KHONG
    muon nap lai toan bo HO (du lieu ho_neighbor khong doi). Dung asyncpg
    thuan (giong xoa_va_nap()), KHONG qua SQLAlchemy session - script nay la
    cong cu doc lap, khong phu thuoc infrastructure/ cho buoc doc don gian."""
    import os

    import asyncpg
    from dotenv import load_dotenv

    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Khong tim thay DATABASE_URL trong .env", file=sys.stderr)
        sys.exit(1)
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        recs = await conn.fetch(
            "SELECT source_enb, source_sector, target_enb, ho_attempt, ngay_du_lieu "
            "FROM system_nsn_nqmproactivecc.ho_neighbor WHERE netact = $1",
            netact,
        )
    finally:
        await conn.close()

    if not recs:
        print(f"Khong co dong ho_neighbor nao cho netact={netact} trong DB - khong co gi de tinh.", file=sys.stderr)
        sys.exit(1)

    ngay_du_lieu = recs[0]["ngay_du_lieu"]
    rows = [
        {
            "source_enb": r["source_enb"],
            "source_sector": r["source_sector"],
            "target_enb": r["target_enb"],
            "ho_attempt": r["ho_attempt"],
        }
        for r in recs
    ]
    return ngay_du_lieu, rows


def main():
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Ten hoac duong dan file CSV report HO. Neu chi truyen ten file, se tim trong data_test/ (BAT BUOC tru khi dung --chi-tinh-cran)")
    parser.add_argument("--netact", required=True, help='Ten NetAct instance (vd "NA09") - dung de xoa+nap lai DUNG pham vi du lieu nay')
    parser.add_argument("--dry-run", action="store_true", help="Chi in ra, khong ghi DB (mac dinh la GHI DB THAT)")
    parser.add_argument(
        "--chi-tinh-cran", action="store_true",
        help="KHONG nap lai HO (khong can --file) - CHI tinh lai bang cell_vi_tri_uoc_luong tu ho_neighbor "
             "dang co san trong DB cho --netact (dung sau khi sua logic phan loai toa do/_SITE_RE)",
    )
    args = parser.parse_args()

    if args.chi_tinh_cran:
        if args.dry_run:
            print("--chi-tinh-cran khong ho tro --dry-run (khong ghi gi ngoai cell_vi_tri_uoc_luong, da la thao tac an toan/idempotent).", file=sys.stderr)
            sys.exit(1)
        ngay_du_lieu, rows = asyncio.run(_doc_rows_tu_db(args.netact))
        print(f"[--chi-tinh-cran] Doc {len(rows):,} dong ho_neighbor cho netact={args.netact}, ngay_du_lieu={ngay_du_lieu} TU DB (KHONG nap lai HO).")
        try:
            asyncio.run(tinh_va_ghi_vi_tri_cran(args.netact, ngay_du_lieu, rows))
        except Exception as e:
            print(f"LOI: tinh vi tri uoc luong CRAN THAT BAI cho netact={args.netact}: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if not args.file:
        print("Can --file (hoac dung --chi-tinh-cran de chi tinh lai CRAN tu du lieu da co).", file=sys.stderr)
        sys.exit(1)

    path = Path(args.file)
    if not path.exists():
        candidate = DEFAULT_DATA_DIR / args.file
        if candidate.exists():
            path = candidate
        else:
            print(f"Khong tim thay file: {args.file}", file=sys.stderr)
            print(f"  (da thu: {path.resolve()} va {candidate.resolve()})", file=sys.stderr)
            sys.exit(1)

    ngay_du_lieu, rows = doc_csv(path)
    print(f"Ngay du lieu (PERIOD_START_TIME): {ngay_du_lieu}")
    print(f"So nguon (source_enb, source_sector) phan biet: {len({(r['source_enb'], r['source_sector']) for r in rows}):,}")
    print(f"So dong se nap (sau loc + gop theo sector, DAY DU - khong cat top-N): {len(rows):,}")

    asyncio.run(xoa_va_nap(args.netact, ngay_du_lieu, rows, args.dry_run))

    # BUOC 4c (10/10/2026) - CHI tinh SAU KHI ho_neighbor nap THANH CONG
    # (khong phai dry-run) - uoc luong vi tri CRAN can doc LAI du lieu vua
    # nap (qua `rows` co san trong memory, KHONG can query lai DB). SUA
    # 15/10/2026: loi o day gio PHAI lam script exit != 0 (xem docstring
    # tinh_va_ghi_vi_tri_cran() - truoc day bi nuot im lang, 1 lan nap that
    # da "loi giua chung" ma khong ai biet).
    if not args.dry_run:
        try:
            asyncio.run(tinh_va_ghi_vi_tri_cran(args.netact, ngay_du_lieu, rows))
        except Exception as e:
            print(f"LOI: ho_neighbor DA nap OK cho netact={args.netact}, nhung tinh vi tri uoc luong CRAN THAT BAI: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
