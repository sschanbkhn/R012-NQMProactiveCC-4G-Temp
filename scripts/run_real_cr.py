"""
scripts/run_real_cr.py — chay TriggerCrUseCase.execute() THAT, dung dung
infrastructure/dependencies.py (B8.1) de lay instance that: DB that (schema
system_nsn_nqmproactivecc), CDS/CTS that (gw-oneoss.vnpt.vn), NetAct that qua
SSH (NETACT_SERVERS trong .env). KHONG di qua HTTP/router (Part C1 chua code)
— goi thang application/trigger_cr_use_case.py nhu 1 script doc lap.
Tu: TASK_LIST.md C2.1 (script verify thuc te); yeu cau user 12072026.

***************************************************************************
* CANH BAO QUAN TRONG: neu truyen --confirm-real-run, script nay se thuc  *
* su Import + Provision len NetAct THAT — TAC DONG LIVE NETWORK (thay doi *
* rsboost/qrxlevmin that tren tram dang phuc vu khach hang that). Day     *
* KHONG PHAI mo phong VA KHONG THE "chay lai" de hoan tac.                 *
*                                                                          *
* Guardrail (13072026, sua tu input('YES') tuong tac sang flag ro rang    *
* theo yeu cau user): MAC DINH (khong truyen gi) DUNG TRUOC buoc 13 SSH   *
* — chay het tinh toan/build XML, KHONG bao gio goi SSH that. Phai truyen *
* --confirm-real-run moi thuc thi SSH that.                                *
***************************************************************************

Cach chay:
    python scripts/run_real_cr.py                     # DUNG TRUOC SSH (an toan)
    python scripts/run_real_cr.py --confirm-real-run   # SSH THAT len NetAct

Log + XML luu vao docs/logs/netact_runs/{YYYYMMDD_HHMMSS}/:
    run.log            - toan bo log text (logging module, ca console + file)
    sse_events.jsonl    - moi SSE event TriggerCrUseCase phat ra, dung thu tu,
                          1 dong JSON/event (khong doi qua real SSE stream vi
                          session_id chi sinh ra SAU khi execute() bat dau -
                          khong the subscribe truoc, xem _LoggingEventBus)
    xml_content.xml     - XML that da gui cho NetActAdapter.submit_cr() (chi
                          co neu chay toi buoc 12; rong neu fail truoc do)
    result.json         - CrSession cuoi cung (hoac exception neu loi truoc
                          khi tao duoc session - xem guard errors C2.1)

LUU Y: thu muc netact_runs/ co the chua du lieu van hanh that (ten plan,
cell that cua tram 110548) - CHUA quyet dinh co nen .gitignore hay commit
len GitHub hay khong, script nay KHONG tu dong git add/commit gi ca. Can
ban xac nhan truoc khi push thu muc nay len repo cong khai/noi bo.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# python scripts/run_real_cr.py chi dua thu muc scripts/ vao sys.path[0] (KHONG
# phai project root) - phai tu them project root truoc khi import cac module
# tuyet doi (application/, infrastructure/, domain/, adapters/) o duoi.
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
    / "docs"
    / "logs"
    / "netact_runs"
    / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
)


class _LoggingEventBus:
    # Wrapper NGOAI CrEventBus that (infrastructure/event_bus.py) - KHONG sua
    # doi code that, chi log lai moi event ra file truoc khi delegate. Ly do
    # KHONG dung subscribe()/Queue that: session_id chi duoc DB sinh ra (SERIAL)
    # BEN TRONG execute() (buoc 2), script khong biet truoc de subscribe() kip
    # thoi - publish() vao 1 session_id chua ai subscribe se bi drop am tham
    # (infrastructure/event_bus.py: "for q in self._queues.get(session_id, [])").
    def __init__(self, real_bus, events_log_path: Path):
        self._real_bus = real_bus
        self._events_log_path = events_log_path

    async def subscribe(self, session_id):
        return await self._real_bus.subscribe(session_id)

    async def unsubscribe(self, session_id, q):
        await self._real_bus.unsubscribe(session_id, q)

    async def publish(self, session_id, event: dict) -> None:
        line = json.dumps({"session_id": session_id, **event}, ensure_ascii=False)
        with open(self._events_log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"[SSE] step={event.get('step')} pct={event.get('pct')} status={event.get('status')} msg={event.get('msg')}")
        await self._real_bus.publish(session_id, event)


class _LoggingNetActGateway:
    # Wrapper NGOAI NetActAdapter that (adapters/netact/netact_adapter.py,
    # B7.3) - KHONG sua doi code that. Log CANH BAO truoc/sau khi goi
    # submit_cr() that - day la buoc CO TAC DONG LIVE NETWORK, can audit
    # trail ro rang truoc khi lenh that su duoc gui.
    # 15072026: BO doan tu ghi (self._run_dir / "xml_content.xml") o day -
    # TRUNG LAP voi NetActAdapter that (da sua de tu ghi xml_content.xml +
    # execution.log vao docs/logs/netact_runs/{DDMMYYYY_HHMM}/ ngay trong
    # submit_cr() that, dung chung 1 noi cho ca production va script nay) -
    # xac nhan voi user, khong con can run_dir rieng cho class nay nua.
    def __init__(self, real_gateway):
        self._real_gateway = real_gateway
        self._logger = logging.getLogger("run_real_cr.netact")

    async def submit_cr(self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance) -> bool:
        # SUA 27092026 (Giai doan 1 buoc 2) - tham so doi tu ma_tinh: str
        # sang oss: OssInstance (dinh tuyen theo tung cell, xem
        # application/trigger_cr_use_case.py). KHONG log oss.password.
        self._logger.warning(
            "SAP GOI submit_cr() THAT - Import+Provision len NetAct (TAC DONG LIVE NETWORK)",
            extra={"plan_name": plan_name, "backup_name": backup_name, "oss_instance": oss.instance_id},
        )
        result = await self._real_gateway.submit_cr(xml_content, plan_name, backup_name, oss)
        self._logger.warning("submit_cr() KET QUA THAT", extra={"result": result})
        return result


class _ConfirmRequiredNetActGateway:
    # Dung khi KHONG truyen --confirm-real-run - KHONG BAO GIO goi SSH that.
    # Cung co che voi _StopBeforeSshNetActGateway trong checkpoint_real_cr.py:
    # luu xml_content ra file that, return False (ket qua nghiep vu binh
    # thuong) de TriggerCrUseCase tu ket thuc sach (FAILED), khong stuck RUNNING.
    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._logger = logging.getLogger("run_real_cr.netact")

    async def submit_cr(self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance) -> bool:
        (self._run_dir / "xml_content.xml").write_text(xml_content, encoding="utf-8")
        msg = "DUNG TRUOC SSH — can --confirm-real-run de thuc thi SSH that len NetAct"
        self._logger.warning(msg, extra={"plan_name": plan_name, "backup_name": backup_name, "oss_instance": oss.instance_id})
        print(f"\n[DUNG TRUOC SSH] {msg}")
        print(f"[DUNG TRUOC SSH] plan_name={plan_name} backup_name={backup_name} oss_instance={oss.instance_id}")
        print(f"[DUNG TRUOC SSH] XML da luu tai: {(self._run_dir / 'xml_content.xml').resolve()}")
        return False


def _cr_session_to_dict(result) -> dict:
    return {
        "id": result.id,
        "tram_id": result.tram_id,
        "action": result.action,
        "status": result.status.value,
        "plan_name": result.plan_name,
        "backup_plan_name": result.backup_plan_name,
        "xml_filename": result.xml_filename,
        "executed_at": result.executed_at.isoformat() if result.executed_at else None,
    }


async def main(confirm_real_run: bool) -> None:
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    events_log_path = _RUN_DIR / "sse_events.jsonl"

    setup_logger()
    file_handler = logging.FileHandler(_RUN_DIR / "run.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)
    logger = logging.getLogger("run_real_cr")

    logger.warning("=== BAT DAU TriggerCrUseCase THAT ===")
    logger.warning(f"tram_id={TRAM_ID} tram_name={TRAM_NAME} action={ACTION}")
    logger.warning(f"Log day du luu tai: {_RUN_DIR}")

    result_data: dict = {}
    # cell_infor_repo (quyet dinh 12/07/2026, them sau khi script nay viet lan dau) dung
    # raw asyncpg, KHONG phai AsyncSession nhu cac repo khac - mo/dong connection
    # rieng bang tay o day, cung pattern infrastructure/db.py::get_asyncpg_connection()
    # (script khong di qua FastAPI Depends() nen khong the dung generator do truc tiep).
    asyncpg_conn = await asyncpg.connect(_ASYNCPG_DSN)
    try:
        async with AsyncSessionLocal() as session:
            cds_adapter = deps.get_cds_adapter()
            cts_adapter = deps.get_cts_adapter()
            enodeb_http_adapter = deps.get_enodeb_http_adapter()
            network_gw = deps.get_network_gateway(cds_adapter, cts_adapter, enodeb_http_adapter)
            netact_gw = (
                _LoggingNetActGateway(deps.get_netact_gateway())
                if confirm_real_run
                else _ConfirmRequiredNetActGateway(_RUN_DIR)
            )
            event_bus = _LoggingEventBus(deps.get_event_bus(), events_log_path)

            use_case = TriggerCrUseCase(
                network_gw=network_gw,
                netact_gw=netact_gw,
                session_repo=deps.get_cr_session_repo(session),
                cell_repo=deps.get_cell_params_repo(session),
                cell_infor_repo=deps.get_cell_infor_repo(asyncpg_conn),
                enodeb_repo=deps.get_enodeb_repo(session),
                event_bus=event_bus,
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

            try:
                result = await use_case.execute(TRAM_ID, TRAM_NAME, ACTION)
                result_data = _cr_session_to_dict(result)
                logger.warning(f"=== KET THUC: status={result.status.value} session_id={result.id} ===")
                if result.status == CrStatus.FAILED:
                    logger.error("CR THAT BAI - xem sse_events.jsonl + run.log de biet dung buoc nao loi")
            except Exception as e:
                # Guard errors (TramNotFoundError/CrAlreadyRunningError/
                # CrAlreadyDoneError/ValueError/NotImplementedError) RAISE truc
                # tiep tu execute() (chua co session de set FAILED - xem
                # application/trigger_cr_use_case.py, quyet dinh 2 dau file)
                result_data = {"exception": type(e).__name__, "message": str(e)}
                logger.exception("=== EXCEPTION TU execute() (guard error, truoc khi tao duoc cr_session) ===")
                raise
            finally:
                (_RUN_DIR / "result.json").write_text(
                    json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.warning(f"=== Log day du: {_RUN_DIR} ===")
    finally:
        await asyncpg_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-real-run",
        action="store_true",
        help="Bat buoc truyen de thuc thi SSH Import+Provision THAT len NetAct. Khong truyen se dung truoc buoc 13.",
    )
    args = parser.parse_args()

    print(f"tram_id={TRAM_ID} tram_name={TRAM_NAME} action={ACTION}")
    print(f"Log se luu tai: {_RUN_DIR}")
    if args.confirm_real_run:
        print(
            "*** --confirm-real-run: script se Import + Provision THAT len NetAct "
            f"cho tram_id={TRAM_ID} ({TRAM_NAME}). Day la hanh dong KHONG THE HOAN "
            "TAC bang cach 'chay lai' — tac dong truc tiep len mang dang phuc vu "
            "khach hang that. ***"
        )
    else:
        print(
            "Khong co --confirm-real-run: script se dung TRUOC buoc 13 (SSH "
            "Import/Provision) — chi tinh toan + build XML, KHONG goi SSH that."
        )
    asyncio.run(main(args.confirm_real_run))
