"""
adapters/http/sync_tram_from_enodeb.py

Fetch toan bo eNodeB list (phan trang, pageSize toi da 1000) va upsert vao
bang tram. Dua tren test_enodeb_list.py da test that thanh cong.

Mapping field JSON -> cot DB (xac nhan tu DB_SCHEMA.md + response that):
  enodeb_id     -> tram_id
  ten_he_thong  -> tram_name
  ma_tinh       -> ma_tinh
  ten_thiet_bi  -> ten_thiet_bi
  longitude     -> longitude (0 hoac None -> NULL)
  latitude      -> latitude (0 hoac None -> NULL)
  ma_csht       -> ma_csht
  ten_quan_ly   -> ten_quan_ly (SUA 04/10/2026 - OQ-11 DA RESOLVE: API that
                  tra field nay, vd "SMC_VINPEARL-CUA HOI1-CLO_NAN". Rong/
                  khoang trang -> None, giong cach xu ly ma_tinh/ma_csht)

Chay:
  python sync_tram_from_enodeb.py --tram-id 110548   # test nhanh 1 tram
  python sync_tram_from_enodeb.py                    # sync toan bo (~58k dong)
  python sync_tram_from_enodeb.py --dry-run           # chi in, khong ghi DB
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

HOST = "10.156.10.119"
PORT = 8080
URL = f"http://{HOST}:{PORT}/application/g/enodeb_list"


def _get_token() -> str:
    # V11 - truoc day JWT nam CUNG TRONG SOURCE (hardcode), da bi commit vao
    # git history - moi lan clone repo la lo secret them 1 noi. Doc tu .env,
    # DUNG chung bien ENODEB_BEARER_TOKEN voi adapters/http/enodeb_http_adapter.py
    # (quy uoc da co san, KHONG dat ten moi ENODEB_JWT de tranh 2 bien cung
    # tro 1 token).
    #
    # Doc trong ham (khong phai module-level) va KHONG fallback ve token cu:
    # goi load_dotenv() luc IMPORT module se bat script chay duoc du .env
    # thieu bien (import xong roi moi bao loi, hoac te hon la dung nham token
    # cu neu co fallback) - chi bao loi khi THAT SU can goi API, va loi phai
    # noi ro TEN BIEN thieu, khong duoc de import app (neu sau nay co noi nao
    # import module nay) crash vi thieu credential cua 1 script CLI doc lap.
    load_dotenv()
    token = os.getenv("ENODEB_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            "Thieu bien moi truong ENODEB_BEARER_TOKEN trong .env - xem "
            ".env.example muc ENODEB LIST API. KHONG co gia tri mac dinh "
            "(token cu da bi xoa khoi source vi la secret)."
        )
    return token


def fetch_page(page_index: int, page_size: int) -> dict | None:
    # SUA 04/10/2026: requests -> httpx (requests KHONG nam trong requirements/
    # venv cua repo - chay tren .196 se ModuleNotFoundError). Dung ham module-
    # level httpx.post() (GIONG cu phap requests.post(), khong can doi logic
    # goi) - KHONG dung httpx.AsyncClient nhu EnodebHttpAdapter vi fetch_page()/
    # fetch_all()/main() o day deu la ham DONG BO (sync), viet lai thanh async
    # se keo theo sua CA vong lap phan trang trong fetch_all(), ngoai pham vi
    # yeu cau "chi doi requests -> httpx".
    headers = {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}
    body = {"pageIndex": page_index, "pageSize": page_size}
    resp = httpx.post(URL, json=body, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all(tram_id_filter: str | None = None) -> list[dict]:
    all_rows: list[dict] = []
    page_index = 1
    page_size = 1000
    while True:
        data = fetch_page(page_index, page_size)
        if not data or not data.get("success"):
            print(f"[ERROR] API tra loi o trang {page_index}: {data}", file=sys.stderr)
            break
        rows = data.get("data", [])
        if tram_id_filter:
            rows = [r for r in rows if str(r.get("enodeb_id")) == str(tram_id_filter)]
        all_rows.extend(rows)

        total_page = data.get("totalPage", 1)
        print(f"[INFO] Da fetch trang {page_index}/{total_page} ({len(rows)} dong)")

        if tram_id_filter and rows:
            break  # tim thay roi, dung som khi filter 1 tram
        if page_index >= total_page:
            break
        page_index += 1

    return all_rows


def to_row(r: dict) -> dict:
    lon = r.get("longitude")
    lat = r.get("latitude")
    return {
        "tram_id": str(r.get("enodeb_id")),
        "tram_name": r.get("ten_he_thong"),
        "ma_tinh": r.get("ma_tinh") or None,
        "ten_thiet_bi": r.get("ten_thiet_bi"),
        "longitude": lon if lon else None,
        "latitude": lat if lat else None,
        "ma_csht": r.get("ma_csht") or None,
        # SUA 04/10/2026 (OQ-11 da resolve - API that tra field nay, vd
        # "SMC_VINPEARL-CUA HOI1-CLO_NAN"). .strip() TRUOC khi check rong -
        # khac ma_tinh/ma_csht (chi "or None", khong strip): du lieu quan ly
        # hanh chinh de dinh dang loi khoang trang dau/cuoi hon ma tinh/ma
        # CSHT (ma code chuan), "   " se qua duoc "or None" (truthy) neu
        # khong strip truoc, luu nham chuoi trang vao DB thay vi NULL that su.
        "ten_quan_ly": (r.get("ten_quan_ly") or "").strip() or None,
    }


async def upsert_all(rows: list[dict], dry_run: bool):
    if dry_run:
        for r in rows:
            print(f"[UPSERT] {r}")
        print(f"\nTong: {len(rows)} tram se duoc upsert (dry-run, CHUA ghi DB that)")
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
        # C1.4-fix9 (21072026) - last_synced_at/updated_at gio la TIMESTAMPTZ
        # (models/tram.py) - THAY now() cua Postgres (DB server TimeZone GUC=
        # Asia/Ho_Chi_Minh, tung xac nhan la nguon bug lech gio) bang gia tri
        # Python tinh SAN datetime.now(timezone.utc), truyen qua bind param
        # ($8) giong pattern EnodebRepo.upsert_many() (production path that,
        # adapters/postgres/enodeb_repo.py) - script nay la utility doc lap
        # (chay tay qua CLI), phai dong bo cach lam de khong tao lai bug cu.
        now_utc = datetime.now(timezone.utc)
        # created_at THEM vao column list (truoc day dua vao server_default=
        # now() cua DB, gio migration C1.4-fix9 da DROP DEFAULT o cot nay -
        # INSERT thieu se vi pham NOT NULL). CHI dat luc INSERT (KHONG dua vao
        # ON CONFLICT SET) - giu dung ngu nghia "set 1 lan luc tao", khop cach
        # SQLAlchemy default= (khac onupdate=) hoat dong o models/tram.py.
        # SUA 04/10/2026 (OQ-11 da resolve) - them ten_quan_ly vao CA cot
        # INSERT LAN ON CONFLICT SET (khac trang_thai/created_at - 2 cot do
        # GIU NGUYEN KHONG dua vao SET, xem comment ngay tren ve ly do).
        upsert_sql = """
            INSERT INTO system_nsn_nqmproactivecc.tram
                (tram_id, tram_name, ma_tinh, ten_thiet_bi, longitude, latitude,
                 ma_csht, ten_quan_ly, trang_thai, last_synced_at, updated_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active', $9, $9, $9)
            ON CONFLICT (tram_id) DO UPDATE SET
                tram_name = EXCLUDED.tram_name,
                ma_tinh = EXCLUDED.ma_tinh,
                ten_thiet_bi = EXCLUDED.ten_thiet_bi,
                longitude = EXCLUDED.longitude,
                latitude = EXCLUDED.latitude,
                ma_csht = EXCLUDED.ma_csht,
                ten_quan_ly = EXCLUDED.ten_quan_ly,
                last_synced_at = EXCLUDED.last_synced_at,
                updated_at = EXCLUDED.updated_at
        """
        args = [
            (
                r["tram_id"],
                r["tram_name"],
                r["ma_tinh"],
                r["ten_thiet_bi"],
                r["longitude"],
                r["latitude"],
                r["ma_csht"],
                r["ten_quan_ly"],
                now_utc,
            )
            for r in rows
        ]
        async with conn.transaction():
            await conn.executemany(upsert_sql, args)
        print(f"Da ghi DB that: {len(rows)} tram")
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tram-id", default=None, help="Chi sync 1 tram (test nhanh)")
    parser.add_argument("--dry-run", action="store_true", help="Chi in, khong ghi DB")
    args = parser.parse_args()

    raw_rows = fetch_all(tram_id_filter=args.tram_id)
    if not raw_rows:
        print("Khong fetch duoc dong nao.", file=sys.stderr)
        sys.exit(1)

    rows = [to_row(r) for r in raw_rows]
    missing_ma_tinh = [r["tram_id"] for r in rows if not r["ma_tinh"]]
    if missing_ma_tinh:
        print(
            f"[WARN] {len(missing_ma_tinh)} tram thieu ma_tinh: {missing_ma_tinh[:20]}"
            f"{' ...' if len(missing_ma_tinh) > 20 else ''}",
            file=sys.stderr,
        )

    asyncio.run(upsert_all(rows, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
