"""
adapters/netact/import_cell_infor.py

Doc file CSV export tu Admin CLI (8 cot, tab-separated, 2 dong header + dong 
trong) va upsert vao bang cell_infor.

Khac voi import_cell_params_csv.py (ban cu): KHONG join theo key giua nhieu 
dong nua - moi dong trong file da tu du 8 cot cho 1 cell, ghi thang 1-1 vao DB, 
key chinh la dn_lncel (cot 2).

Vi tri cot co dinh (theo thu tu, KHONG dua vao ten header vi trung $dn):
  0: $operation
  1: $dn        -> dn_lncel   (KEY chinh, dung de tra cuu)
  2: name
  3: cellName   -> cell_name
  4: $dn        -> dn_fdd     (dung build XML sau nay)
  5: dlRsBoost  -> rsboost_current (dang "0dB", can strip "dB")
  6: $dn        -> dn_sib     (dung build XML sau nay)
  7: qrxlevmin  -> qrxlevmin_current (so nguyen)
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).parent / "data_test"


def detect_delimiter(path: Path) -> str:
    """Tu nhan dien dau phan cach - KHONG gia dinh co dinh tab hay phay.

    Admin CLI (NetAct) co the export ra TAB hoac COMMA tuy cau hinh phien
    export, ma duoi file luon la ".csv" trong ca hai truong hop - nhin ten file
    khong biet duoc. File mau dang co trong repo
    (data_test/data_crr012_hni_11072026_11122.csv) thuc te la COMMA-separated
    (docstring cu ghi nham la TAB - da sua 12/08).

    Dem ky tu trong 4KB dau roi chon ben nhieu hon: 2 dong header co san
    (NOKLTE:LNCEL,... / $operation,$dn,...) da du dac dau phan cach that de
    phan biet, ke ca khi gia tri trong du lieu co lan dau kia.
    """
    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(4096)
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def read_csv(path: Path) -> list[dict]:
    delimiter = detect_delimiter(path)
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, raw in enumerate(reader, start=1):
            if len(raw) < 8:
                continue  # dong ngan/hong/trong -> bo qua im lang
            row = [c.strip() for c in raw[:8]]
            _, dn_lncel, name, cell_name, dn_fdd, rsboost_raw, dn_sib, qrx_raw = row

            # nhan dien dong header/blank: cot dn_lncel phai bat dau bang PLMN-PLMN
            if not dn_lncel.startswith("PLMN-PLMN"):
                continue

            try:
                rsboost_current = float(rsboost_raw.replace("dB", "").strip()) if rsboost_raw else None
            except ValueError:
                print(f"[WARN] dong {i}: dlRsBoost khong parse duoc: '{rsboost_raw}'", file=sys.stderr)
                rsboost_current = None

            try:
                qrxlevmin_current = int(qrx_raw.strip()) if qrx_raw else None
            except ValueError:
                print(f"[WARN] dong {i}: qrxlevmin khong parse duoc: '{qrx_raw}'", file=sys.stderr)
                qrxlevmin_current = None

            rows.append({
                "dn_lncel": dn_lncel,
                "name": name,
                "cell_name": cell_name,
                "dn_fdd": dn_fdd or None,
                "rsboost_current": rsboost_current,
                "dn_sib": dn_sib or None,
                "qrxlevmin_current": qrxlevmin_current,
            })
    return rows


async def upsert_all(rows: list[dict], dry_run: bool):
    if dry_run:
        for r in rows:
            print(f"[UPSERT] {r}")
        print(f"\nTong: {len(rows)} dong se duoc upsert (dry-run, CHUA ghi DB that)")
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
        upsert_sql = """
            INSERT INTO system_nsn_nqmproactivecc.cell_infor
                (dn_lncel, name, cell_name, dn_fdd, rsboost_current,
                 dn_sib, qrxlevmin_current, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (dn_lncel) DO UPDATE SET
                name = EXCLUDED.name,
                cell_name = EXCLUDED.cell_name,
                dn_fdd = EXCLUDED.dn_fdd,
                rsboost_current = EXCLUDED.rsboost_current,
                dn_sib = EXCLUDED.dn_sib,
                qrxlevmin_current = EXCLUDED.qrxlevmin_current,
                updated_at = now()
        """
        args = [
            (r["dn_lncel"], r["name"], r["cell_name"], r["dn_fdd"],
             r["rsboost_current"], r["dn_sib"], r["qrxlevmin_current"])
            for r in rows
        ]

        async with conn.transaction():
            await conn.executemany(upsert_sql, args)

        print(f"Da ghi DB that: {len(rows)} dong")
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