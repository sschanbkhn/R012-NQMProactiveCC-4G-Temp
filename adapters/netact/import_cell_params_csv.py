"""
adapters/netact/import_cell_params_csv.py

Doc CSV export tu Admin CLI (8 cot, khong co header chuan - 3 cot $dn trung ten)
va upsert vao bang cell_params (schema system_nsn_nqmproactivecc).

Vi tri cot co dinh (theo thu tu, KHONG dua vao ten header vi trung $dn):
  0: $operation
  1: $dn        -> distName LNCEL       (de lay cell_id, tram_id)
  2: name
  3: cellName
  4: $dn        -> distName LNCEL_FDD   (khong can luu rieng)
  5: dlRsBoost  -> rsboost hien tai (dang "0dB", "3dB"... can strip "dB")
  6: $dn        -> distName SIB         (khong can luu rieng)
  7: qrxlevmin  -> qrxlevmin hien tai (so nguyen, co dau -)

Gia dinh distName LNCEL dang: PLMN-PLMN/MRBTS-{tram_id}/LNBTS-{tram_id}/LNCEL-{cell_local_id}
-> cell_id lay = MRBTS + "-" + LNCEL local id (VD: "110548-11").
   CHINH LAI neu quy uoc cell_id trong DB khac (vd chi dung cellName).
   XAC NHAN voi DB_SCHEMA.md truoc khi chay that (phan upsert_all() dang o dang
   TODO / dry-run, chua ghi DB that).

Vi tri chay mac dinh (theo project structure hien tai):
  D:\\Python_Project\\R012-NQMProactiveCustomerCare\\11072026_1406\\R012-NQMProactiveCC-4G\\
  adapters\\netact\\data_test\\
"""
import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# TODO: sua import nay cho dung cau truc project that (Hexagonal Architecture)
# from app.infrastructure.db import AsyncSessionLocal
# from app.adapters.repositories.cell_params_repo import CellParamsRepo

DN_RE = re.compile(r"MRBTS-(\d+).*?LNCEL-(\d+)")

# Mac dinh tim file CSV trong thu muc data_test cung cap voi script nay
DEFAULT_DATA_DIR = Path(__file__).parent / "data_test"


def extract_key(dn: str):
    """Rut (tram_id, lncel_local_id) tu MOT distName bat ky (LNCEL, LNCEL_FDD hoac SIB).
    QUAN TRONG: moi block ($dn cot 1, cot 4, cot 6) phai duoc parse RIENG bang ham nay,
    KHONG duoc gia dinh 3 block tren cung 1 dong thuoc cung 1 cell (da xac nhan sai qua
    dry-run that: vi du 4G-DDA155M12-HNI co $dn cua LNCEL_FDD tren cung dong tro sang
    cell khac voi $dn cua LNCEL/SIB)."""
    dn = dn.strip()
    if not dn.startswith("PLMN-PLMN"):
        return None
    m = DN_RE.search(dn)
    if not m:
        return None
    return (m.group(1), m.group(2))  # (tram_id, lncel_local_id)


def detect_delimiter(path: Path) -> str:
    """File thuc te export tu Admin CLI la TAB-separated (du duoi .csv).
    Tu nhan dien de van chay dung neu gap ban comma-separated."""
    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(4096)
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def read_csv(path: Path) -> list[dict]:
    """Doc toan bo file, tach 3 block LNCEL / LNCEL_FDD / SIB thanh 3 map RIENG
    theo key (tram_id, lncel_local_id) rut tu chinh $dn cua tung block, roi moi
    JOIN lai theo key o cuoi. Khong con ghep theo vi tri dong."""
    delimiter = detect_delimiter(path)

    lncel_info: dict = {}   # key -> {"cell_name": ...}
    rsboost_map: dict = {}  # key -> rsboost hien tai
    qrx_map: dict = {}      # key -> qrxlevmin hien tai

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, raw in enumerate(reader, start=1):
            if len(raw) < 8:
                continue  # dong ngan/hong/trong -> bo qua im lang
            row = [c.strip() for c in raw[:8]]
            _, dn_lncel, name, cell_name, dn_fdd, rsboost_raw, dn_sib, qrx_raw = row

            key_lncel = extract_key(dn_lncel)
            if key_lncel:
                lncel_info[key_lncel] = {"cell_name": cell_name}

            key_fdd = extract_key(dn_fdd)
            if key_fdd and rsboost_raw:
                try:
                    rsboost_map[key_fdd] = float(rsboost_raw.replace("dB", "").strip())
                except ValueError:
                    print(f"[WARN] dong {i}: dlRsBoost khong parse duoc: '{rsboost_raw}'", file=sys.stderr)

            key_sib = extract_key(dn_sib)
            if key_sib and qrx_raw:
                try:
                    qrx_map[key_sib] = int(qrx_raw.strip())
                except ValueError:
                    print(f"[WARN] dong {i}: qrxlevmin khong parse duoc: '{qrx_raw}'", file=sys.stderr)

    all_keys = set(lncel_info) | set(rsboost_map) | set(qrx_map)
    rows = []
    incomplete = 0
    for key in sorted(all_keys):
        tram_id, lncel_local_id = key
        cell_id = f"{tram_id}-{lncel_local_id}"
        info = lncel_info.get(key, {})
        rsboost = rsboost_map.get(key)
        qrxlevmin = qrx_map.get(key)
        cell_name = info.get("cell_name", "")
        if rsboost is None or qrxlevmin is None or not cell_name:
            incomplete += 1
            print(
                f"[WARN] cell {cell_id} thieu du lieu: "
                f"cell_name='{cell_name}', rsboost={rsboost}, qrxlevmin={qrxlevmin} -> khong upsert",
                file=sys.stderr,
            )
            continue
        rows.append({
            "cell_id": cell_id,
            "tram_id": tram_id,
            "cell_name": cell_name,
            "rsboost": rsboost,
            "qrxlevmin": qrxlevmin,
        })

    if incomplete:
        print(f"\n[INFO] {incomplete} cell bi loai vi thieu rsboost hoac qrxlevmin sau khi join theo key", file=sys.stderr)
    return rows


async def upsert_all(rows: list[dict], dry_run: bool):
    if dry_run:
        for r in rows:
            print(f"[UPSERT] {r}")
        print(f"\nTong: {len(rows)} cell se duoc upsert (dry-run, CHUA ghi DB that)")
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

    conn = await asyncpg.connect(dsn)
    try:
        # C1.4-fix9 (21072026) - last_synced_at/updated_at/created_at gio la
        # TIMESTAMPTZ (models/cell_params.py) va migration da DROP server-side
        # DEFAULT now() (DB server TimeZone GUC=Asia/Ho_Chi_Minh, nguon bug
        # lech gio). Raw SQL nay KHONG di qua SQLAlchemy nen KHONG duoc huong
        # default= Python cua model - phai tu tinh va truyen tuong minh, giong
        # pattern CellParamsRepo.upsert() (production path that,
        # adapters/postgres/cell_params_repo.py). created_at CHI dat luc
        # INSERT (khong dua vao ON CONFLICT SET) - set 1 lan luc tao.
        now_utc = datetime.now(timezone.utc)
        upsert_sql = """
            INSERT INTO system_nsn_nqmproactivecc.cell_params
                (tram_id, cell_name, cell_id, rsboost_current, qrxlevmin_current,
                 last_synced_at, updated_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $6, $6)
            ON CONFLICT (tram_id, cell_name) DO UPDATE SET
                cell_id = EXCLUDED.cell_id,
                rsboost_current = EXCLUDED.rsboost_current,
                qrxlevmin_current = EXCLUDED.qrxlevmin_current,
                last_synced_at = EXCLUDED.last_synced_at,
                updated_at = EXCLUDED.updated_at
        """
        args = [
            (r["tram_id"], r["cell_name"], r["cell_id"], r["rsboost"], r["qrxlevmin"], now_utc)
            for r in rows
        ]

        async with conn.transaction():
            await conn.executemany(upsert_sql, args)

        print(f"Da ghi DB that: {len(rows)} cell")
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        required=True,
        help="Ten hoac duong dan file CSV. Neu chi truyen ten file, se tim trong data_test/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi in ra, khong ghi DB (mac dinh la GHI DB THAT)",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        candidate = DEFAULT_DATA_DIR / args.file
        if candidate.exists():
            path = candidate
        else:
            print(f"Khong tim thay file: {args.file}", file=sys.stderr)
            print(f"  (da thu: {path.resolve()} va {candidate.resolve()})", file=sys.stderr)
            sys.exit(1)

    rows = read_csv(path)
    if not rows:
        print("Khong co dong hop le nao de import.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(upsert_all(rows, dry_run=args.dry_run))


if __name__ == "__main__":
    main()