"""
scripts/checkpoint_real_cr.py — chay TriggerCrUseCase.execute() THAT cho
tram_id=110548 (DB that, CDS that, ma_tinh that) NHUNG DUNG LAI TRUOC buoc SSH
Import/Provision (buoc 13-16) — KHONG bao gio goi SSH/NetAct that.

Co che dung lai AN TOAN: netact_gw duoc thay bang stub — LUU xml_content ra
file + KHONG goi SSH that + return False (ket qua nghiep vu "that bai" binh
thuong, giong currently netact that tra ve False khi Import/Provision loi).
=> TriggerCrUseCase tu dong di vao nhanh "if not ok: fail(); return session"
da co san (application/trigger_cr_use_case.py dong 274-276) — cr_session ket
thuc voi status=FAILED (KHONG bi ket ket o RUNNING mai mai, khong chan lan
trigger that sau nay cho cung tram, vi guard chi chan RUNNING/DONE).

Tu: yeu cau user 12072026 (Checkpoint 1: verify DB, Checkpoint 2: verify XML).

LUU Y QUAN TRONG (Checkpoint 2, cau hoi cua user):
- Script nay dung convention docs/logs/netact_runs/{timestamp}/ (GIONG
  scripts/run_real_cr.py, KHONG PHAI docs/logs/netact_test/{timestamp}/
  {filename}.xml + execution.log - quyet dinh nay chua duoc ghi lai trong
  docs). Dung nguyen convention da co san trong run_real_cr.py
  (nhat quan trong repo) - CHUA doi sang netact_test/, cho user xac nhan.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from application.trigger_cr_use_case import TriggerCrUseCase
from domain.entities.cr_session import CrStatus
from domain.value_objects.oss_instance import OssInstance
from infrastructure import dependencies as deps
from infrastructure.db import AsyncSessionLocal, _ASYNCPG_DSN
from infrastructure.logger import setup_logger

TRAM_ID = "110548"
TRAM_NAME = "4G-HKM005M-HNI"
ACTION = "shutdown"

_RUN_DIR = (
    Path(__file__).resolve().parent.parent
    / "docs" / "logs" / "netact_runs" / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_CHECKPOINT"
)

_captured = {"get_by_cell_names_result": None, "get_by_cell_names_query": None, "submit_cr_args": None}


class _LoggingCellParamsRepo:
    """Wrapper NGOAI CellParamsRepo that — bat lai ket qua get_by_cell_names()
    de bao cao Checkpoint 1, KHONG doi hanh vi thuc te."""

    def __init__(self, real_repo):
        self._real = real_repo

    async def get_by_tram_id(self, tram_id):
        return await self._real.get_by_tram_id(tram_id)

    async def get_by_cell_names(self, cell_names):
        result = await self._real.get_by_cell_names(cell_names)
        _captured["get_by_cell_names_query"] = list(cell_names)
        _captured["get_by_cell_names_result"] = result
        return result

    async def upsert(self, params):
        return await self._real.upsert(params)

    async def snapshot_before_cr(self, session_id):
        return await self._real.snapshot_before_cr(session_id)


class _StopBeforeSshNetActGateway:
    """KHONG BAO GIO goi SSH/NetAct that. Luu xml_content ra file that, return
    False (ket qua nghiep vu binh thuong) de TriggerCrUseCase tu ket thuc sach
    (FAILED), khong stuck RUNNING."""

    def __init__(self, run_dir: Path):
        self._run_dir = run_dir

    async def submit_cr(self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance) -> bool:
        # SUA 27092026 (Giai doan 1 buoc 2) - tham so doi tu ma_tinh: str
        # sang oss: OssInstance. CHI luu instance_id (khong luu password).
        _captured["submit_cr_args"] = {
            "plan_name": plan_name,
            "backup_name": backup_name,
            "oss_instance": oss.instance_id,
            "xml_content": xml_content,
        }
        xml_path = self._run_dir / "xml_content.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        print(f"\n[STOP-BEFORE-SSH] Da luu XML tai: {xml_path.resolve()}")
        print("[STOP-BEFORE-SSH] KHONG goi SSH/NetAct that. Tra ve False de ket thuc sach (FAILED).")
        return False


async def main() -> None:
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    setup_logger()
    file_handler = logging.FileHandler(_RUN_DIR / "run.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)

    # cell_infor_repo (quyet dinh 12/07/2026, them sau khi script nay viet lan dau) dung
    # raw asyncpg, khong phai AsyncSession - cung pattern run_real_cr.py.
    asyncpg_conn = await asyncpg.connect(_ASYNCPG_DSN)
    try:
        async with AsyncSessionLocal() as session:
            cds_adapter = deps.get_cds_adapter()
            cts_adapter = deps.get_cts_adapter()
            enodeb_http_adapter = deps.get_enodeb_http_adapter()
            network_gw = deps.get_network_gateway(cds_adapter, cts_adapter, enodeb_http_adapter)
            netact_gw = _StopBeforeSshNetActGateway(_RUN_DIR)
            cell_repo = _LoggingCellParamsRepo(deps.get_cell_params_repo(session))

            use_case = TriggerCrUseCase(
                network_gw=network_gw,
                netact_gw=netact_gw,
                session_repo=deps.get_cr_session_repo(session),
                cell_repo=cell_repo,
                cell_infor_repo=deps.get_cell_infor_repo(asyncpg_conn),
                enodeb_repo=deps.get_enodeb_repo(session),
                event_bus=deps.get_event_bus(),
                rsboost_calc=deps.get_rsboost_calculator(),
                qrxlevmin_calc=deps.get_qrxlevmin_calculator(),
                xml_builder=deps.get_xml_builder(),
                # affected_cells_repo/cr_log_repo (22/07/2026, Phuong an B) -
                # THIEU tu luc TriggerCrUseCase them 2 tham so nay (script
                # KHONG duoc cap nhat theo) - BO SUNG 02/10/2026 de script
                # chay duoc voi constructor hien tai, CHI sua cho du tham so,
                # KHONG them tinh nang gi (xem docs/DEV_LOG.md).
                affected_cells_repo=deps.get_cr_affected_cells_repo(session),
                cr_log_repo=deps.get_cr_log_repo(session),
                # Giai doan 1 buoc 2 (27/09/2026) - dinh tuyen OSS theo tung cell.
                oss_router=deps.get_oss_router(),
                # BO CDS (18/10/2026) - HO la nguon duy nhat, ho_neighbor_repo
                # bat buoc (truoc day script chay nhanh CDS mac dinh).
                ho_neighbor_repo=deps.get_ho_neighbor_repo(session),
            )

            result = await use_case.execute(TRAM_ID, TRAM_NAME, ACTION)

            print("\n" + "=" * 70)
            print(f"KET QUA execute(): status={result.status.value}, session_id={result.id}")
            print("=" * 70)

            (_RUN_DIR / "result.json").write_text(
                json.dumps(
                    {"id": result.id, "tram_id": result.tram_id, "status": result.status.value},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
    finally:
        await asyncpg_conn.close()

    # ===== CHECKPOINT 1 REPORT =====
    # LUU Y (13072026): get_by_cell_names() KHONG con duoc TriggerCrUseCase goi
    # nua tu sau khi chuyen sang cell_infor_repo (quyet dinh 12/07/2026, truoc thay doi
    # neighbor_cell_filter hom nay) - _LoggingCellParamsRepo wrapper o tren se
    # KHONG bao gio bat duoc gi (_captured luon None). Report nay da STALE tu
    # truoc, KHONG sua sau trong lan nay (ngoai pham vi yeu cau), chi sua loi
    # indentation do them cell_infor_repo gay ra.
    print("\n" + "=" * 70)
    print("CHECKPOINT 1 — get_by_cell_names()")
    print("=" * 70)
    query = _captured["get_by_cell_names_query"]
    cells = _captured["get_by_cell_names_result"]
    print(f"So cell_name query: {len(query) if query else 0}")
    print(f"Danh sach cell_name (tu CDS that + filter that): {query}")
    print(f"So dong get_by_cell_names() tra ve: {len(cells) if cells else 0}")
    if cells:
        for c in cells:
            print(f"  cell_name={c.cell_name} tram_id={c.tram_id} rsboost_current={c.rsboost_current} qrxlevmin_current={c.qrxlevmin_current}")

    with open(_RUN_DIR / "checkpoint1_get_by_cell_names.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "query_cell_names": query,
                "result": [
                    {
                        "cell_name": c.cell_name, "tram_id": c.tram_id,
                        "rsboost_current": c.rsboost_current.value if c.rsboost_current else None,
                        "qrxlevmin_current": c.qrxlevmin_current.value if c.qrxlevmin_current else None,
                    }
                    for c in (cells or [])
                ],
            },
            f, ensure_ascii=False, indent=2,
        )

    # ===== CHECKPOINT 1 — doi chieu doc lap qua asyncpg tho (KHONG qua CellParamsRepo/SQLAlchemy ORM) =====
    if query:
        import os
        dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                "SELECT tram_id, cell_name, rsboost_current, qrxlevmin_current "
                "FROM system_nsn_nqmproactivecc.cell_params WHERE cell_name = ANY($1::text[]) ORDER BY cell_name",
                query,
            )
            print("\n--- Doi chieu doc lap (asyncpg tho, KHONG qua CellParamsRepo) ---")
            for r in rows:
                print(f"  tram_id={r['tram_id']} cell_name={r['cell_name']} rsboost_current={r['rsboost_current']} qrxlevmin_current={r['qrxlevmin_current']}")
        finally:
            await conn.close()

    # ===== CHECKPOINT 2 REPORT =====
    print("\n" + "=" * 70)
    print("CHECKPOINT 2 — XML build")
    print("=" * 70)
    sc = _captured["submit_cr_args"]
    if sc is None:
        print("XML CHUA duoc build (execute() dung lai truoc buoc 12, VD loi som hon) - xem run.log")
    else:
        print(f"plan_name: {sc['plan_name']}")
        print(f"backup_name: {sc['backup_name']}")
        print(f"oss_instance: {sc['oss_instance']}")
        print(f"XML da luu tai: {(_RUN_DIR / 'xml_content.xml').resolve()}")
        print(f"Log SSH (khong co that vi da dung lai) + moi log khac cua run nay: {(_RUN_DIR / 'run.log').resolve()}")
        print("\n--- NOI DUNG XML DAY DU ---")
        print(sc["xml_content"])
        print("--- HET XML ---")

    print(f"\nThu muc log day du (checkpoint nay): {_RUN_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
