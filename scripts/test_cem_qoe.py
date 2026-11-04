"""
SCRIPT TEST THUC NGHIEM - KHONG PHAI CODE PRODUCTION.

Muc dich: kiem chung API CEM (nguon QoE muc cell) co goi duoc khong, va
XAC DINH TRUONG NAO la QoE thang 1-5.

Tai sao can: OQ-01 - SocHttpAdapter hien dang la MOCK tra qoe=3.5 cung
(API_CONTRACTS.md Section 3: "Auth CHUA XAC NHAN"). BUSINESS_RULES/
xuat_phieu danh gia cell "KHONG DAT" khi chenh lech QoE truoc-sau > 0.2 ->
neu lay nham truong thang 0-100 (ux_final_idx_value) thi nguong 0.2 thanh
vo nghia. Vi vay script phai in RO khoang gia tri quan sat duoc.

KHONG sua adapters/http/soc_http_adapter.py. KHONG tich hop vao use case.

CAN TRUOC KHI CHAY: CEM_ACCOUNT + CEM_HASH_KEY trong .env (xem .env.example).
Script KHONG co gia tri mac dinh cho 2 bien nay - xem ly do o cho khai bao
ENV_ACCOUNT/ENV_HASH_KEY ben duoi.

Chay:
    python scripts/test_cem_qoe.py
    python scripts/test_cem_qoe.py --date 20260814 --cells 4G-A-HNI 4G-B-HNI
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import ssl
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# ── Hang so spec CEM ───────────────────────────────────────────────────────
# Chi HOST doc tu env (de doi sang moi truong test cua CEM ma khong sua code);
# duong dan API la mot phan cua SPEC, khong phai cau hinh van hanh.
DEFAULT_BASE_URL = "https://api-cem.vnptmedia.vn"
API_PATH = "/api5/daily/cell/kpi"

# Chuoi "@2022" la HANG SO CO DINH trong cong thuc hash cua CEM, chen giua
# hashKey va timestamp. Khong phai nam hien tai -> KHONG duoc thay bang
# datetime.now().year.
CEM_SALT = "@2022"

# KHONG co gia tri fallback cho account/hashKey - BAT BUOC doc tu .env.
#
# VI SAO (sua 16082026): moi credential khac cua du an deu nam trong .env -
# CDS_SECURE_KEY, ENODEB_BEARER_TOKEN, NETACT_SERVERS, cau hinh SaveCellClm/CTS.
# De rieng hashKey CEM trong ma nguon vua KHONG NHAT QUAN voi phan con lai, vua
# nguy hiem hon han: file nay NAM TRONG GIT va da duoc push len remote - hardcode
# o day la day thang credential len server git, noi khong ai kiem soat duoc ai
# doc. Thieu bien -> DUNG HAN (exit 1), KHONG doan, KHONG chay tiep voi key rong
# roi de nguoi dung tuong la loi API.
ENV_ACCOUNT = "CEM_ACCOUNT"
ENV_HASH_KEY = "CEM_HASH_KEY"
ENV_BASE_URL = "CEM_BASE_URL"

# Bang ma loi trong spec CEM - dung de doan nguyen nhan khi HTTP != 200.
ERROR_HINTS = {
    400: "Sai cu phap request (thieu field / sai kieu du lieu / JSON hong)",
    401: "Sai dinh danh hoac xac thuc that bai -> kiem tra account, hashKey, "
    "cong thuc secure_code (noi THANG, SHA-256), hoac timestamp lech > 30 phut",
    403: "Khong co quyen truy cap tai nguyen (account chua duoc cap quyen)",
    404: "Sai duong dan endpoint",
    503: "He thong qua tai / bao tri - thu lai sau",
}

# Cell mac dinh khi KHONG doc duoc DB. La cell THAT (co phieu CTS that 19207 /
# id=82 trong cr_phieu - DEV_LOG.md muc "Data that dung de test 12/08"), nhung
# van la go tay -> script canh bao ro khi phai dung nhanh nay.
FALLBACK_CELLS = ["4G-SSN087M43-HNI", "4G-SSN104M12-HNI"]

DEFAULT_SESSION_ID = 553


# ── .env ───────────────────────────────────────────────────────────────────
def load_env_file() -> None:
    """
    Nap .env o repo root vao os.environ.

    Why: script nam trong scripts/ nhung DATABASE_URL nam o .env repo root;
    dung parser toi gian de script chay duoc ca khi venv thieu python-dotenv.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# ── Auth ───────────────────────────────────────────────────────────────────
def build_secure_code(request_id: str, account: str, hash_key: str, timestamp: str) -> tuple[str, str]:
    """
    secure_code = SHA-256( request_id + account + hashKey + "@2022" + timestamp )

    KHAC HAN CDS/CTS (test_cds_neighbors.py): CDS dung SHA-512 + dau phan cach
    pipe "|" + gui qua HEADER. CEM noi THANG khong dau phan cach, SHA-256, va
    tat ca nam trong BODY.

    Tra ve (secure_code, chuoi_da_che_hashkey) de in doi chieu ma khong lo key.
    """
    raw = f"{request_id}{account}{hash_key}{CEM_SALT}{timestamp}"
    masked = f"{request_id}{account}<hashkey>{CEM_SALT}{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), masked


def is_ssl_failure(exc: BaseException) -> bool:
    """
    Nhan dien loi TLS.

    Why: httpx boc loi qua nhieu tang (httpcore -> httpx.ConnectError) nen
    isinstance(exc.__cause__, ssl.SSLError) khong du - phai di het chuoi
    __cause__/__context__.
    """
    seen = set()
    node: BaseException | None = exc
    while node is not None and id(node) not in seen:
        if isinstance(node, ssl.SSLError) or "SSL" in str(node):
            return True
        seen.add(id(node))
        node = node.__cause__ or node.__context__
    return False


def legacy_ssl_context(verify: bool) -> ssl.SSLContext:
    """
    SSLContext ha security level ve 1.

    Why: server CEM bat tay TLS bang DH key ngan (1024-bit) - OpenSSL 3.x mac
    dinh SECLEVEL=2 tu choi thang ("[SSL: DH_KEY_TOO_SMALL] dh key too small")
    nen KHONG the goi duoc bang httpx mac dinh. Ha SECLEVEL chi de bat tay
    duoc voi server noi bo cu; van GIU verify chung chi (verify=True).
    """
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def mask_secure_code(code: str) -> str:
    """Che phan giua secure_code khi in body (giu 8 dau + 8 cuoi de doi chieu)."""
    if len(code) <= 20:
        return code
    return f"{code[:8]}...{code[-8:]}"


# ── Doc cell that tu DB ────────────────────────────────────────────────────
async def fetch_cells_from_db(session_id: int, limit: int) -> list[str]:
    """
    Lay ten cell CHINH XAC tu cr_affected_cells (khong go tay - ten cell sai 1
    ky tu thi CEM tra rong va ta se ket luan nham la "API khong co du lieu").
    """
    import asyncpg  # import cuc bo: script van chay duoc khi chi test --cells

    url = os.environ.get("DATABASE_URL", "")
    # DATABASE_URL dang SQLAlchemy (postgresql+asyncpg://) - asyncpg.connect
    # khong hieu phan "+asyncpg".
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        raise RuntimeError("DATABASE_URL rong")

    conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=15)
    try:
        rows = await conn.fetch(
            "SELECT cell_name FROM cr_affected_cells "
            "WHERE cr_session_id = $1 ORDER BY cell_name LIMIT $2",
            session_id,
            limit,
        )
    finally:
        await conn.close()
    return [r["cell_name"] for r in rows]


def resolve_cells(args: argparse.Namespace) -> list[str]:
    if args.cells:
        return args.cells

    try:
        cells = asyncio.run(fetch_cells_from_db(args.session, args.limit))
        if cells:
            print(f"[cells] Doc tu DB cr_affected_cells session {args.session}: {cells}")
            return cells
        print(f"[cells] CANH BAO: session {args.session} khong co dong nao trong cr_affected_cells")
    except Exception as exc:  # noqa: BLE001 - script test, moi loi DB deu chi la fallback
        print(f"[cells] CANH BAO: khong doc duoc DB ({type(exc).__name__}: {exc})")

    print(f"[cells] Dung fallback go tay: {FALLBACK_CELLS}")
    return FALLBACK_CELLS


# ── Phan tich response ─────────────────────────────────────────────────────
# Cac truong can doi chieu, theo dung thu tu in bang.
FIELDS = [
    "ux_final",
    "ux_final_idx_value",
    "ux_1",
    "ux_2",
    "ux_3",
    "active_sub",
    "vol_downlink",
]


def find_cell_records(payload) -> list[dict]:
    """
    Tim list ban ghi muc cell trong response.

    Why: spec CEM chua noi ro ten khoa bao ngoai ("data"/"result"/"cells"...)
    -> do de quy tim list dau tien chua dict co truong nhan dang cell, thay vi
    hardcode payload["data"] roi vo tay khi ten khoa khac.
    """
    found: list[dict] = []

    def walk(node):
        if found:
            return
        if isinstance(node, list):
            dicts = [x for x in node if isinstance(x, dict)]
            if dicts and any(
                k in dicts[0] for k in ("cell_name", "cellname", "cell", "cell_id", "ux_final")
            ):
                found.extend(dicts)
                return
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(payload)
    return found


def get_cell_name(rec: dict) -> str:
    """
    Lay TEN cell.

    Why thu tu nay: CEM tra ca "cellName" (ten, vd 4G-SSN087M43-HNI) lan
    "cell_id" (ID so, vd 1166-29537579). Phai uu tien ten - lay nham cell_id
    thi doi chieu voi danh sach cell gui di se bao "thieu het" oan.
    """
    for key in ("cellName", "cell_name", "cellname", "cell", "cell_id"):
        if key in rec:
            return str(rec[key])
    return "<?>"


def fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def to_number(value):
    """Ep ve so de tinh min/max; CEM co the tra so duoi dang chuoi."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def analyse(payload, requested_cells: list[str]) -> None:
    records = find_cell_records(payload)

    print()
    print("=" * 100)
    print("PHAN TICH KET QUA")
    print("=" * 100)

    if not records:
        print("Khong tim thay ban ghi muc cell nao trong response.")
        print("Khoa cap 1 cua response:", list(payload) if isinstance(payload, dict) else type(payload).__name__)
        return

    print(f"So ban ghi cell tra ve: {len(records)}")
    print()

    # In het ten truong CEM tra ve: spec liet ke mot so truong (vd active_sub)
    # co the KHONG ton tai that -> phai thay danh sach that de khong viet
    # adapter doc truong ma API khong bao gio tra.
    all_keys = sorted({k for r in records for k in r})
    print(f"-- {len(all_keys)} TRUONG CO THAT TRONG RESPONSE --")
    print(", ".join(all_keys))
    absent = [f for f in FIELDS if f not in all_keys]
    if absent:
        print(f"KHONG CO trong response (du spec/yeu cau nhac toi): {absent}")
    print()

    header = ["cell_name"] + FIELDS
    rows = [[get_cell_name(r)] + [fmt(r.get(f)) for f in FIELDS] for r in records]
    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(header))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    # ── Khoang gia tri quan sat duoc ───────────────────────────────────────
    print()
    print("-- KHOANG GIA TRI QUAN SAT DUOC --")
    ranges: dict[str, tuple[float, float]] = {}
    for field in FIELDS:
        nums = [n for n in (to_number(r.get(field)) for r in records) if n is not None]
        if not nums:
            print(f"{field:22s}: (khong co gia tri so)")
            continue
        ranges[field] = (min(nums), max(nums))
        print(f"{field:22s}: min={min(nums):g}  max={max(nums):g}  (n={len(nums)})")

    # ── Ket luan thang do ──────────────────────────────────────────────────
    # Why: R012 so sanh QoE truoc/sau voi nguong chenh lech 0.2 (BUSINESS_RULES).
    # Nguong nay chi dung neu lay truong thang 1-5. Neu lay nham thang 0-100 thi
    # 0.2 diem tren 100 la nhieu do -> gan nhu MOI cell deu "DAT".
    print()
    print("-- KET LUAN VE THANG DO --")
    for field in ("ux_final", "ux_final_idx_value"):
        if field not in ranges:
            print(f"{field}: khong co du lieu so -> chua ket luan duoc")
            continue
        lo, hi = ranges[field]
        if 0 <= lo and hi <= 5:
            verdict = "NAM TRONG THANG 1-5 -> DUNG duoc lam QoE cho R012 (nguong 0.2 co nghia)"
        elif hi <= 100:
            verdict = "THANG 0-100 -> KHONG dung truc tiep lam QoE (nguong 0.2 se vo nghia)"
        else:
            verdict = "Vuot 100 -> khong phai thang QoE, can hoi lai CEM"
        print(f"{field}: [{lo:g} .. {hi:g}] -> {verdict}")
        if lo == hi:
            print(
                f"   LUU Y: ca {len(records)} cell deu cung gia tri {lo:g} -> mau qua it de "
                "chung minh bang so; xem doi chieu ux_N / ux_N_idx_value ben duoi."
            )

    # Doi chieu tung cap ux_N <-> ux_N_idx_value: neu ux_N la ban rut gon 1-5
    # cua chi so 0-100 thi cap nay phai cung chieu (idx cao -> ux cao).
    pairs = [
        (r.get(f"ux_{i}"), r.get(f"ux_{i}_idx_value"), i)
        for r in records
        for i in (1, 2, 3)
        if r.get(f"ux_{i}") is not None and r.get(f"ux_{i}_idx_value") is not None
    ]
    if pairs:
        print()
        print("-- DOI CHIEU ux_N (thang nho) <-> ux_N_idx_value (thang 0-100) --")
        for ux, idx, i in pairs:
            print(f"ux_{i}={fmt(ux):5s} <- ux_{i}_idx_value={fmt(idx)}")

    # ── Cell bi bo qua ─────────────────────────────────────────────────────
    print()
    print("-- DOI CHIEU CELL GUI DI / TRA VE --")
    returned = {get_cell_name(r) for r in records}
    missing = [c for c in requested_cells if c not in returned]
    extra = [c for c in returned if c not in requested_cells]
    print(f"Gui di  ({len(requested_cells)}): {requested_cells}")
    print(f"Tra ve  ({len(returned)}): {sorted(returned)}")
    if missing:
        print(f"THIEU   ({len(missing)}): {missing}")
        print("-> API BO QUA cell khong co du lieu (khong tra dong rong).")
        print("   Adapter that PHAI xu ly truong hop thieu cell, khong duoc zip theo thu tu.")
    else:
        print("Khong thieu cell nao - API tra du so cell da gui.")
    if extra:
        print(f"THUA (ten khong khop ten gui di): {extra}")


# ── Main ───────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    p = argparse.ArgumentParser(description="Test API CEM daily/cell/kpi (QoE muc cell)")
    # Mac dinh HOM QUA: CEM la du lieu THEO NGAY, hom nay chua chot so lieu.
    p.add_argument("--date", default=yesterday, help=f"yyyyMMdd (mac dinh hom qua: {yesterday})")
    p.add_argument("--cells", nargs="*", default=None, help="Ten cell; bo trong -> doc tu DB")
    p.add_argument("--session", type=int, default=DEFAULT_SESSION_ID, help="cr_session_id de lay cell")
    p.add_argument("--limit", type=int, default=2, help="So cell lay tu DB (mac dinh 2)")
    p.add_argument("--timeout", type=float, default=60, help="Timeout giay (mac dinh 60)")
    # Spec chi noi "lech khong qua 30 phut" ma khong noi mui gio -> cho phep thu
    # ca UTC neu gio local (GMT+7) bi tu choi 401.
    p.add_argument("--utc", action="store_true", help="Dung gio UTC thay vi gio may (thu khi bi 401)")
    p.add_argument(
        "--no-verify",
        action="store_true",
        help="Bo kiem tra chung chi TLS (chi khi phai ha SECLEVEL va cert noi bo khong verify duoc)",
    )
    return p.parse_args()


def main() -> int:
    # Console Windows mac dinh cp1252 -> in response CEM (co dau tieng Viet) se
    # nem UnicodeEncodeError va mat toan bo ket qua. errors="replace" de khong
    # bao gio chet vi ky tu la.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    load_env_file()
    args = parse_args()

    account = os.environ.get(ENV_ACCOUNT, "").strip()
    hash_key = os.environ.get(ENV_HASH_KEY, "").strip()
    if not account or not hash_key:
        # Dung han thay vi chay tiep voi key rong: goi voi key rong se tra 401
        # va nguoi dung se di do loi cong thuc hash / timestamp, trong khi
        # nguyen nhan that chi la thieu bien moi truong.
        thieu = [t for t, v in ((ENV_ACCOUNT, account), (ENV_HASH_KEY, hash_key)) if not v]
        print(f"Thieu {ENV_ACCOUNT} hoac {ENV_HASH_KEY} trong .env. Xin credential tu VNPT-TSC.")
        print(f"Bien dang thieu: {', '.join(thieu)}")
        return 1

    base_url = (os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}{API_PATH}"

    cells = resolve_cells(args)

    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc) if args.utc else datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    secure_code, masked_raw = build_secure_code(request_id, account, hash_key, timestamp)

    body = {
        "request_id": request_id,
        "timestamp": timestamp,
        "account": account,
        "secure_code": secure_code,
        "date": args.date,
        "cells": cells,
    }

    print()
    print("=" * 100)
    print("REQUEST")
    print("=" * 100)
    print(f"URL              : {url}")
    print(f"Gio dung de hash : {'UTC' if args.utc else 'local may'} -> {timestamp}")
    print()
    print("1) Chuoi truoc khi hash (hashKey da che):")
    print(f"   {masked_raw}")
    print("   Cong thuc: request_id + account + hashKey + \"@2022\" + timestamp (noi THANG, SHA-256)")
    print()
    print("2) secure_code sinh ra:")
    print(f"   {secure_code}")
    print()
    print("3) Body gui di (secure_code da che phan giua):")
    printable = dict(body, secure_code=mask_secure_code(secure_code))
    print(json.dumps(printable, ensure_ascii=False, indent=2))

    def post(verify) -> httpx.Response:
        return httpx.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=args.timeout,
            verify=verify,
        )

    try:
        # Thu bat tay TLS binh thuong truoc; chi ha SECLEVEL khi server tu choi
        # -> khong che giau viec server dung DH key yeu.
        try:
            resp = post(True)
        except httpx.HTTPError as exc:
            if not is_ssl_failure(exc):
                raise
            print()
            print(f"-- TLS mac dinh that bai: {exc} --")
            print("-- Thu lai voi SECLEVEL=1 (server CEM dung DH key ngan) --")
            resp = post(legacy_ssl_context(verify=not args.no_verify))
    except httpx.HTTPError as exc:
        print()
        print("-- LOI KET NOI (khong toi duoc server) --")
        print(f"{type(exc).__name__}: {exc}")
        cause = exc.__cause__ or exc.__context__
        if cause is not None:
            print(f"Nguyen nhan goc: {type(cause).__name__}: {cause}")
        return 1

    print()
    print("=" * 100)
    print("RESPONSE")
    print("=" * 100)
    print(f"4) HTTP status code: {resp.status_code}")
    print()

    text = resp.text
    print(f"5) Response body ({len(text)} ky tu):")
    print(text if len(text) < 5000 else text[:3000] + "\n... [CAT - body dai hon 5000 ky tu]")

    if resp.status_code != 200:
        print()
        print("-- DOAN NGUYEN NHAN (bang ma loi trong spec CEM) --")
        print(f"HTTP {resp.status_code}: {ERROR_HINTS.get(resp.status_code, 'Khong co trong bang ma loi spec')}")
        if resp.status_code == 401 and not args.utc:
            print("Goi y: chay lai voi --utc (spec chi noi lech <= 30 phut, khong noi mui gio).")
        return 1

    try:
        payload = resp.json()
    except ValueError:
        print()
        print("Response khong phai JSON hop le -> khong phan tich duoc.")
        return 1

    analyse(payload, cells)
    return 0


if __name__ == "__main__":
    sys.exit(main())
