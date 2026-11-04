"""
DANH GIA DUNG 1 SESSION - goi thang EvaluateCrUseCase.execute(session_id).

VI SAO CAN SCRIPT NAY: `POST /api/v1/jobs/evaluate-cr` KHONG nhan session_id -
no goi `execute_all_pending()` va xu ly TAT CA session du 21 ngay (khao sat
16/08: 9 session, gom ca session mock va 6 session cu co 0 cell). Khong co cach
nao qua HTTP de danh gia dung 1 session. Script nay goi THANG use case, la
duong hep nhat de thu nghiem nguon QoE that (CEM) ma khong dung vao session khac.

=== CANH BAO: SCRIPT NAY GHI VAO DB ===
EvaluateCrUseCase.execute() CAP NHAT cr_session (status, qoe_result, qos_result,
qoe_before/after, qos_before/after, evaluated_at) VA ghi qoe_snapshot/
qos_snapshot. KHONG phai script chi doc.
Vi vay BAT BUOC go "YES" tren console truoc khi ghi - CO Y KHONG co co --yes de
bo qua buoc nay (chay hang loat/tu dong khong phai muc dich cua script).

Chay:
    python scripts/evaluate_mot_session.py --session 553
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

from adapters.http.cds_http_adapter import CdsHttpAdapter
from adapters.http.cts_http_adapter import CtsHttpAdapter
from adapters.http.enodeb_http_adapter import EnodebHttpAdapter
from adapters.http.network_gateway_facade import NetworkGatewayFacade
from adapters.postgres.alert_repo import AlertRepo
from adapters.postgres.cell_params_repo import CellParamsRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.qoe_snapshot_repo import QoeSnapshotRepo
from adapters.postgres.qos_snapshot_repo import QosSnapshotRepo
from application.alert_use_case import AlertUseCase
from application.evaluate_cr_use_case import EvaluateCrUseCase
from domain.services.evaluation_service import EvaluationService
from infrastructure.db import AsyncSessionLocal
from infrastructure.dependencies import get_soc_gateway

load_dotenv()

SCHEMA = "system_nsn_nqmproactivecc"

# Cac cot doi chieu TRUOC/SAU - dung DUNG danh sach trong yeu cau khao sat de
# bang so sanh doc duoc thang, khong phai do mat tim cot.
COT_THEO_DOI = [
    "id",
    "tram_id",
    "status",
    "qoe_result",
    "qos_result",
    "qoe_before",
    "qoe_after",
    "qos_before",
    "qos_after",
    "evaluated_at",
]


async def doc_trang_thai(conn, session_id: int) -> dict | None:
    row = await conn.fetchrow(
        f"SELECT {', '.join(COT_THEO_DOI)} FROM {SCHEMA}.cr_session WHERE id = $1", session_id
    )
    return dict(row) if row else None


def _fmt(v) -> str:
    return "NULL" if v is None else str(v)


def in_bang_so_sanh(truoc: dict, sau: dict) -> None:
    print()
    print("=" * 86)
    print("SO SANH TRUOC / SAU")
    print("=" * 86)

    rong_cot = max(len(c) for c in COT_THEO_DOI)
    rong_truoc = max([len(_fmt(truoc[c])) for c in COT_THEO_DOI] + [len("TRUOC")])
    header = f"{'cot'.ljust(rong_cot)} | {'TRUOC'.ljust(rong_truoc)} | SAU"
    print(header)
    print("-" * len(header))

    for cot in COT_THEO_DOI:
        cu, moi = _fmt(truoc[cot]), _fmt(sau[cot])
        # Danh dau cot DOI de doc nhanh - day la thu duy nhat can nhin.
        dau = "  <-- DOI" if cu != moi else ""
        print(f"{cot.ljust(rong_cot)} | {cu.ljust(rong_truoc)} | {moi}{dau}")


async def main() -> int:
    p = argparse.ArgumentParser(description="Danh gia DUNG 1 cr_session (GHI VAO DB)")
    # BAT BUOC, KHONG co mac dinh: mac dinh la duong ngan nhat den chay nham
    # session khac.
    p.add_argument("--session", type=int, required=True, help="cr_session id (BAT BUOC)")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("Thieu DATABASE_URL trong .env")
        return 1

    cem_enabled = (os.getenv("CEM_ENABLED", "false") or "").strip().lower() == "true"
    print("=" * 86)
    print(f"NGUON QoE: {'CemHttpAdapter (API CEM THAT)' if cem_enabled else 'SocHttpAdapter (MOCK qoe=3.5)'}")
    print(f"           CEM_ENABLED={os.getenv('CEM_ENABLED')!r}")
    print("=" * 86)

    conn = await asyncpg.connect(dsn)
    try:
        truoc = await doc_trang_thai(conn, args.session)
    finally:
        await conn.close()

    if truoc is None:
        print(f"KHONG TIM THAY cr_session id={args.session}")
        return 1

    print()
    print(f"TRANG THAI HIEN TAI cua cr_session id={args.session}:")
    for cot in COT_THEO_DOI:
        print(f"  {cot:15s} = {_fmt(truoc[cot])}")

    # === Chot an toan ===
    print()
    print(f"SE GHI VAO cr_session id={args.session} (va qoe_snapshot/qos_snapshot).")
    tra_loi = input("Go 'YES' de tiep tuc: ").strip()
    if tra_loi != "YES":
        print("Da huy - KHONG ghi gi.")
        return 0

    # === Chay that ===
    # Tu wire use case thay vi qua Depends() cua FastAPI (Depends chi hoat dong
    # trong request context). Danh sach tham so khop 1-1 voi
    # get_evaluate_cr_use_case() trong infrastructure/dependencies.py - neu cho
    # do them tham so thi phai sua ca o day.
    print()
    print("Dang chay EvaluateCrUseCase.execute()...")
    async with AsyncSessionLocal() as db:
        use_case = EvaluateCrUseCase(
            CrSessionRepo(db),
            CellParamsRepo(db),
            NetworkGatewayFacade(CdsHttpAdapter(), CtsHttpAdapter(), EnodebHttpAdapter()),
            # get_soc_gateway() - dung DUNG cong tat CEM_ENABLED nhu app that,
            # KHONG tu chon adapter o day (script phai phan anh dung hanh vi
            # production, khong duoc la duong rieng).
            get_soc_gateway(),
            EvaluationService(),
            AlertUseCase(AlertRepo(db)),
            QoeSnapshotRepo(db),
            QosSnapshotRepo(db),
        )
        ket_qua = await use_case.execute(args.session)

    print()
    print("Ket qua use case tra ve:")
    print(f"  qoe_result = {ket_qua.qoe_result}   qoe_before = {ket_qua.qoe_before}   qoe_after = {ket_qua.qoe_after}")
    print(f"  qos_result = {ket_qua.qos_result}   qos_before = {ket_qua.qos_before}   qos_after = {ket_qua.qos_after}")

    conn = await asyncpg.connect(dsn)
    try:
        sau = await doc_trang_thai(conn, args.session)
    finally:
        await conn.close()

    in_bang_so_sanh(truoc, sau)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
