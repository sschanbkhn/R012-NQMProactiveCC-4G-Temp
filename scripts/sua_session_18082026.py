"""
SUA SESSION 18/08/2026 tu FAILED -> PARTIAL_SUCCESS (chay 1 lan roi bo).

=== VI SAO CAN ===
Session CR tram 113492 ngay 18/08 (plan R012_NQMProactiveCC_113492_20260818_042813)
dang mang status FAILED do BAN CU ghi - luc do chua co PARTIAL_SUCCESS (them o
commit 1ff269e, 19/08). Thuc te provision 3/4 DN THANH CONG.

HAU QUA NEU KHONG SUA: FAILED KHONG nam trong XUAT_PHIEU_STATUS_WHITELIST
(application/xuat_phieu_use_case.py) -> session nay se KHONG BAO GIO duoc job
xuat phieu quet, du 3 tram DA doi tham so RF that va cell cua chung co the da
te di. Mat vinh vien - PA A chi quet moi session DUNG 1 lan.

=== BANG CHUNG cho so 3/4 (tu full stdout NetAct lan chay 18/08) ===
    DN: PLMN-PLMN/MRBTS-116952   Type: Info    STATUS : SUCCESS   FAILED MOS : 0
    DN: PLMN-PLMN/MRBTS-113975   Type: Info    STATUS : SUCCESS   FAILED MOS : 0
    DN: PLMN-PLMN/MRBTS-112685   Type: Info    STATUS : SUCCESS   FAILED MOS : 0
    DN: PLMN-PLMN/MRBTS-113508   Type: Error   java.net.NoRouteToHostException
-> 3 thanh cong / 4 tong

=== NGUON SO LIEU - 3 NHANH ===
1. Parse duoc tu cr_log buoc 13  -> DUNG SO DO (nguon he thong, dang tin nhat).
   Neu co truyen tham so ma LECH -> bao ro, uu tien so cua he thong.
2. KHONG parse duoc + CO tham so -> dung tham so, IN CANH BAO ro rang day la so
   do NGUOI TRUYEN VAO, khong phai he thong doc duoc.
3. KHONG parse duoc + KHONG tham so -> DUNG LAI, khong doan.

Nhanh 2 la duong du kien cho session nay: no chay TRUOC commit 1ff269e nen
cr_log buoc 13 khong co dong tom tat "3/4 DN" de parse.

=== AN TOAN ===
- Tim session theo DIEU KIEN (status=FAILED + ngay 18/08), KHONG hardcode id.
  Tim thay 0 hoac >1 -> DUNG LAI, bao nguoi.
- BAT BUOC go "YES" tren console truoc khi UPDATE. KHONG co co --yes.
- CHI update 3 cot: status, so_dn_thanh_cong, so_dn_tong.

Chay (sau khi migration 4ae6f4d7503b da duoc apply):
    python scripts/sua_session_18082026.py --so-dn-thanh-cong 3 --so-dn-tong 4
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

SCHEMA = "system_nsn_nqmproactivecc"
NGAY_CR = "2026-08-18"
TRANG_THAI_CU = "FAILED"
TRANG_THAI_MOI = "PARTIAL_SUCCESS"

COT_THEO_DOI = [
    "id", "tram_id", "status", "plan_name", "executed_at", "created_at",
    "so_dn_thanh_cong", "so_dn_tong",
]

# Khop dong tom tat buoc 13 do _tom_tat_provision() sinh ra:
#   "Provision 3/4 DN thanh cong (6/12 MO)"
_TOM_TAT_RE = re.compile(r"Provision\s+(\d+)\s*/\s*(\d+)\s+DN\s+thanh\s+cong")


async def _doc_trang_thai(conn, session_id: int) -> dict | None:
    row = await conn.fetchrow(
        f"SELECT {', '.join(COT_THEO_DOI)} FROM {SCHEMA}.cr_session WHERE id = $1", session_id
    )
    return dict(row) if row else None


def _fmt(v) -> str:
    return "NULL" if v is None else str(v)


async def main() -> int:
    p = argparse.ArgumentParser(description="Sua session 18/08 FAILED -> PARTIAL_SUCCESS (GHI DB)")
    p.add_argument("--so-dn-thanh-cong", type=int, default=None)
    p.add_argument("--so-dn-tong", type=int, default=None)
    # 2 tham so TUY CHON - mac dinh KHONG dong toi. Chi dien khi nguoi dung
    # quyet dinh ro: day la du lieu KHONG the doc tu he thong (buoc 17 chua
    # bao gio chay), phai lay tu ten plan / log NetAct ben ngoai.
    p.add_argument("--executed-at", default=None, help="ISO UTC, vd 2026-08-18T04:28:13")
    p.add_argument("--plan-name", default=None)
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("Thieu DATABASE_URL trong .env")
        return 1

    conn = await asyncpg.connect(dsn)
    try:
        # === BUOC 1: TIM session theo dieu kien, KHONG hardcode id ===
        rows = await conn.fetch(
            f"""SELECT c.id, c.tram_id, t.tram_name, c.status, c.executed_at, c.plan_name
                FROM {SCHEMA}.cr_session c
                LEFT JOIN {SCHEMA}.tram t ON t.tram_id = c.tram_id
                WHERE c.status = $1
                  AND (c.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = $2
                ORDER BY c.id""",
            TRANG_THAI_CU, date.fromisoformat(NGAY_CR),
        )
        print(f"=== Session {TRANG_THAI_CU} ngay {NGAY_CR} (gio VN) ===")
        for r in rows:
            print("  ", dict(r))
        if len(rows) != 1:
            print(f"\nDUNG LAI: tim thay {len(rows)} session (can DUNG 1). Khong doan.")
            return 1
        session_id = rows[0]["id"]

        # === BUOC 2: doc cr_log buoc 13 de lay SO THAT ===
        logs = await conn.fetch(
            f"SELECT message FROM {SCHEMA}.cr_log WHERE cr_session_id = $1 AND step = 13", session_id
        )
        tu_he_thong = None
        for lg in logs:
            m = _TOM_TAT_RE.search(lg["message"] or "")
            if m:
                tu_he_thong = (int(m.group(1)), int(m.group(2)))
                break

        print(f"\n=== cr_log buoc 13 ({len(logs)} dong) ===")
        for lg in logs:
            print("  ", (lg["message"] or "")[:120])

        if tu_he_thong:
            so_ok, so_tong = tu_he_thong
            print(f"\nPARSE DUOC tu cr_log: {so_ok}/{so_tong} DN")
            if args.so_dn_tong is not None and (args.so_dn_thanh_cong, args.so_dn_tong) != tu_he_thong:
                print(
                    f"CANH BAO: tham so truyen vao ({args.so_dn_thanh_cong}/{args.so_dn_tong}) "
                    f"LECH voi so he thong ({so_ok}/{so_tong}). UU TIEN so cua he thong."
                )
        elif args.so_dn_thanh_cong is not None and args.so_dn_tong is not None:
            so_ok, so_tong = args.so_dn_thanh_cong, args.so_dn_tong
            print("\nKHONG parse duoc tu cr_log (session chay TRUOC commit 1ff269e nen")
            print("khong co dong tom tat buoc 13).")
            print(f"!!! CANH BAO: dung so {so_ok}/{so_tong} do NGUOI TRUYEN VAO qua tham so")
            print("!!! dong lenh - KHONG phai he thong doc duoc. Xem BANG CHUNG trong")
            print("!!! docstring dau file de truy nguyen.")
        else:
            print("\nDUNG LAI: khong parse duoc tu cr_log VA khong co tham so")
            print("--so-dn-thanh-cong / --so-dn-tong. Khong doan so.")
            return 1

        truoc = await _doc_trang_thai(conn, session_id)

        # === CANH BAO executed_at NULL ===
        # CR fail o buoc 13 nen KHONG BAO GIO toi buoc 17 - noi duy nhat ghi
        # executed_at/plan_name. Doi status sang PARTIAL_SUCCESS la CHUA DU de
        # dat duoc muc dich: job xuat phieu loc theo
        #   executed_at IS NOT NULL AND ngay_CR == hom nay - XUAT_PHIEU_AFTER_DAYS
        # (_lay_session_du_dieu_kien), va _danh_gia_qos_cell() can executed_at de
        # dung cua so T-7/T+7. executed_at NULL -> session VAN khong duoc quet.
        if truoc["executed_at"] is None:
            print()
            print("!" * 74)
            print("CANH BAO: executed_at = NULL (CR fail o buoc 13, chua toi buoc 17).")
            print("Doi status sang PARTIAL_SUCCESS la CHUA DU - job xuat phieu loc theo")
            print("executed_at, nen session nay VAN se khong duoc quet.")
            print("Dung --executed-at de dien luon (xem --help).")
            print("!" * 74)

        # === BUOC 3: chot an toan ===
        print()
        them = ""
        if args.executed_at:
            them += f", executed_at -> {args.executed_at}"
        if args.plan_name:
            them += f", plan_name -> {args.plan_name}"
        print(
            f"SE UPDATE cr_session id={session_id}: status {TRANG_THAI_CU} -> {TRANG_THAI_MOI}, "
            f"so_dn={so_ok}/{so_tong}{them}."
        )
        if input("Go 'YES' de tiep tuc: ").strip() != "YES":
            print("Da huy - KHONG ghi gi.")
            return 0

        # === BUOC 4: UPDATE dung 3 cot ===
        await conn.execute(
            f"""UPDATE {SCHEMA}.cr_session
                SET status = $1, so_dn_thanh_cong = $2, so_dn_tong = $3
                WHERE id = $4""",
            TRANG_THAI_MOI, so_ok, so_tong, session_id,
        )
        # 2 cot TUY CHON - chi ghi khi nguoi dung truyen tuong minh. COALESCE
        # kieu "chi ghi neu dang NULL" de khong bao gio de len gia tri that.
        if args.executed_at:
            await conn.execute(
                f"UPDATE {SCHEMA}.cr_session SET executed_at = $1 WHERE id = $2 AND executed_at IS NULL",
                datetime.fromisoformat(args.executed_at).replace(tzinfo=timezone.utc),
                session_id,
            )
        if args.plan_name:
            await conn.execute(
                f"UPDATE {SCHEMA}.cr_session SET plan_name = $1 WHERE id = $2 AND plan_name IS NULL",
                args.plan_name, session_id,
            )
        sau = await _doc_trang_thai(conn, session_id)
    finally:
        await conn.close()

    # === BUOC 5: bang TRUOC/SAU ===
    print()
    print("=" * 78)
    print("SO SANH TRUOC / SAU")
    print("=" * 78)
    rong = max(len(c) for c in COT_THEO_DOI)
    rong_truoc = max([len(_fmt(truoc[c])) for c in COT_THEO_DOI] + [len("TRUOC")])
    header = f"{'cot'.ljust(rong)} | {'TRUOC'.ljust(rong_truoc)} | SAU"
    print(header)
    print("-" * len(header))
    for cot in COT_THEO_DOI:
        cu, moi = _fmt(truoc[cot]), _fmt(sau[cot])
        print(f"{cot.ljust(rong)} | {cu.ljust(rong_truoc)} | {moi}{'  <-- DOI' if cu != moi else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
