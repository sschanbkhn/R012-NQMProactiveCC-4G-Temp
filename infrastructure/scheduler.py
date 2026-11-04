"""
Scheduler chay job xuat phieu tu dong (JOB TU DONG buoc 3/4).
Tu: yeu cau truc tiep user.

Chay TRONG process uvicorn qua APScheduler AsyncIOScheduler - KHONG them
tien trinh/ha tang moi (n8n hien chi trigger qua HTTP, xem docs/CONTEXT.md
SS5.5; job nay can chay dung 1 lan/ngay ke ca khi khong ai goi).

PHONG THU 2 LOP chong chay trung:
1. max_instances=1: chan luot moi khi luot cu CUA CUNG process chua xong.
2. pg_try_advisory_lock: chan NHIEU PROCESS (uvicorn --workers>1, hoac 2 may
   cung tro vao 1 DB). Lop 1 KHONG du - moi worker co scheduler rieng, deu
   thay dung gio va cung khoi dong job.
"""

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.enodeb_repo import EnodebRepo
from adapters.postgres.job_run_log_repo import JobRunLogRepo
from adapters.postgres.qoe_snapshot_repo import QoeSnapshotRepo
from adapters.postgres.qos_snapshot_repo import QosSnapshotRepo
from application.get_qoe_cells_use_case import GetQoeCellsUseCase
from application.xuat_phieu_use_case import XuatPhieuUseCase
from infrastructure.advisory_lock import KHOA_XUAT_PHIEU, giu_khoa
from infrastructure.db import AsyncSessionLocal
from infrastructure.dependencies import (
    get_cds_adapter,
    get_cts_adapter,
    get_enodeb_http_adapter,
    get_evaluation_service,
    get_soc_gateway,
    get_network_gateway,
    get_qos_sparkline_use_case,
    get_save_cell_clm_gateway,
)

load_dotenv()
logger = logging.getLogger(__name__)


def _co_bat(ten_bien: str) -> bool:
    # Chi coi la BAT khi ghi dung "true" (khong phan biet hoa thuong). Moi gia
    # tri khac - ke ca chuoi rong hay bien khong ton tai - deu la TAT: co lien
    # quan WRITE API that len TTS, mac dinh phai la an toan.
    return os.getenv(ten_bien, "false").strip().lower() == "true"


# V2 (12/08): CHI CON 1 CO. XUAT_PHIEU_AUTO_ENABLED (co cho phep POST that) da
# bi bo cung voi dry_run - giai doan quan sat da xong nen khong con nhu cau
# "chay lich nhung khong gui gi". Bat SCHEDULER_ENABLED = job chay dung gio VA
# POST phieu that len TTS.
SCHEDULER_ENABLED = _co_bat("SCHEDULER_ENABLED")

SCHEDULER_HOUR = int(os.getenv("SCHEDULER_HOUR", "8"))
SCHEDULER_MINUTE = int(os.getenv("SCHEDULER_MINUTE", "0"))

# BAT BUOC set timezone: toan project luu/tinh UTC (CONTEXT.md SS5.6), neu de
# APScheduler dung mac dinh thi hour=8 se la 8h UTC = 15h VN - lech quy trinh
# TTS hoan toan. tz database lay tu goi tzdata (dependency cua APScheduler).
_TIMEZONE = "Asia/Ho_Chi_Minh"

# Cua so 8h00-8h30 theo quy trinh TTS: job tre qua 30 phut (may vua khoi dong
# lai, event loop ket...) thi BO luot, cho hom sau - day phieu luc 15h la lech
# quy trinh, gay hieu nham cho ben tiep nhan.
_MISFIRE_GRACE_TIME = 1800

# Khoa advisory DA CHUYEN sang infrastructure/advisory_lock.py (20082026) de
# POST /jobs/xuat-phieu-auto dung CHUNG - 2 duong cung chay job nay thi phai
# cung mot khoa. KHONG dinh nghia lai o day.
_JOB_TYPE = "xuat_phieu_auto"
_JOB_ID = "xuat_phieu_auto_daily"

# Giu tham chieu scheduler o module level de shutdown() goi duoc tu lifespan.
_scheduler: AsyncIOScheduler | None = None


def _tao_use_case(session) -> XuatPhieuUseCase:
    # Job chay NGOAI request cua FastAPI nen khong co Depends() - phai tu ghep.
    # TAI DUNG cac factory khong can DB session trong infrastructure/
    # dependencies.py (network gateway / qos sparkline / save_cell_clm /
    # evaluation service) thay vi new lai tung adapter o day: neu sau nay doi
    # cach wire (vd doi adapter CTS) thi chi sua 1 cho, job tu theo.
    network_gw = get_network_gateway(get_cds_adapter(), get_cts_adapter(), get_enodeb_http_adapter())
    return XuatPhieuUseCase(
        cr_phieu_repo=CrPhieuRepo(session),
        cr_session_repo=CrSessionRepo(session),
        cr_affected_cells_repo=CrAffectedCellsRepo(session),
        enodeb_repo=EnodebRepo(session),
        qos_sparkline_use_case=get_qos_sparkline_use_case(network_gw),
        save_cell_clm_gateway=get_save_cell_clm_gateway(),
        evaluation_service=get_evaluation_service(),
        job_run_log_repo=JobRunLogRepo(session),
        # QoE ngang hang QoS (17082026). get_soc_gateway() tu re theo
        # CEM_ENABLED - CEM_ENABLED=false thi QoE la mock 3.5 cho moi cell
        # (moi cell deu PASS QoE) nen job hoat dong y nhu truoc.
        qoe_cells_use_case=GetQoeCellsUseCase(
            CrSessionRepo(session),
            CrAffectedCellsRepo(session),
            get_soc_gateway(),
            get_evaluation_service(),
            # SNAPSHOT PER-CELL (20082026). Job la NOI DUY NHAT chac chan da
            # qua T+7 nen day cung la noi GHI snapshot; truyen repo vao ca 2
            # nhanh de QoE tu luu (trong GetQoeCellsUseCase) va QoS tu luu
            # (trong XuatPhieuUseCase._luu_snapshot_qos).
            QoeSnapshotRepo(session),
        ),
        qos_snapshot_repo=QosSnapshotRepo(session),
    )


async def chay_job_xuat_phieu() -> None:
    """1 luot chay job. Duoc APScheduler goi, va co the goi tay de test."""
    # Khoa lay qua infrastructure/advisory_lock.py - DUNG CHUNG voi
    # POST /jobs/xuat-phieu-auto (20082026). Ly do phai la connection asyncpg
    # THO ngoai pool nam trong docstring cua module do.
    async with giu_khoa(KHOA_XUAT_PHIEU) as da_lay_duoc_khoa:
        if not da_lay_duoc_khoa:
            # Worker/may khac (hoac 1 luot chay TAY) dang chay. Day KHONG phai
            # loi - thoat em, KHONG raise (raise se lam APScheduler ghi
            # traceback moi ngay va co the bao dong nham cho van hanh).
            logger.info(
                "Job xuat phieu: luot khac dang chay, bo qua luot nay",
                extra={"job_type": _JOB_TYPE, "lock_key": KHOA_XUAT_PHIEU},
            )
            return

        try:
            # V2: khong con dry_run - toi day la POST THAT len TTS.
            logger.warning(
                "Job xuat phieu: BAT DAU luot chay - SE POST PHIEU THAT len TTS",
                extra={"job_type": _JOB_TYPE},
            )

            async with AsyncSessionLocal() as session:
                job_run_log_repo = JobRunLogRepo(session)
                # Ghi dong RUNNING TRUOC khi lam bat cu viec gi - de luot chay
                # co dau vet ke ca khi chet ngay sau do (bai hoc session #197
                # ket vinh vien RUNNING ma khong ai biet, C1.4-fix2).
                job_run = await job_run_log_repo.insert(
                    {"job_type": _JOB_TYPE, "trang_thai": "RUNNING"}
                )

                use_case = _tao_use_case(session)
                # execute_all_pending() tu ghi ket qua (DONE/FAILED + cac con
                # so) vao dung dong job_run_log nay - xem application/
                # xuat_phieu_use_case.py::_ghi_ket_qua_job().
                #
                # KHONG truyen tu_ngay/den_ngay: job tu dong giu nguyen PA A
                # (quet DUNG 1 ngay = hom nay - XUAT_PHIEU_AFTER_DAYS). 2 tham
                # so do CHI danh cho duong chay tay.
                ket_qua = await use_case.execute_all_pending(job_run_log_id=job_run["id"])

            logger.info(
                "Job xuat phieu: XONG luot chay",
                extra={"job_type": _JOB_TYPE, **ket_qua_tom_tat(ket_qua)},
            )

        except Exception as exc:  # noqa: BLE001 - CO Y bat rong: job chay nen,
            # khong ai bat loi ho. De loi thoat ra se lam APScheduler tu tat job
            # sau vai lan loi lien tiep. Log day du, KHONG raise - luot sau van chay.
            logger.error(
                "Job xuat phieu: luot chay THAT BAI",
                extra={"job_type": _JOB_TYPE, "loi": str(exc)},
            )


def ket_qua_tom_tat(ket_qua: dict) -> dict:
    # Chi lay cac con so de vao log - KHONG log ca "chi_tiet" (co the vai chuc
    # session x vai chuc cell, lam trong log file).
    return {k: v for k, v in ket_qua.items() if k != "chi_tiet"}


def khoi_tao_scheduler() -> AsyncIOScheduler | None:
    """Tao + start scheduler. Tra None khi SCHEDULER_ENABLED=false."""
    global _scheduler

    if not SCHEDULER_ENABLED:
        # KHONG dang ky job nao - cach an toan nhat de tat hoan toan (khac voi
        # dang ky roi kiem tra co ben trong job: van co rui ro job chay do doc
        # co sai thoi diem).
        logger.info("Scheduler: SCHEDULER_ENABLED=false - KHONG dang ky job nao")
        return None

    scheduler = AsyncIOScheduler(timezone=_TIMEZONE)
    scheduler.add_job(
        chay_job_xuat_phieu,
        trigger=CronTrigger(hour=SCHEDULER_HOUR, minute=SCHEDULER_MINUTE),
        id=_JOB_ID,
        # Bo luot neu tre qua cua so quy trinh TTS (xem _MISFIRE_GRACE_TIME).
        misfire_grace_time=_MISFIRE_GRACE_TIME,
        # Miss nhieu lan (may tat may ngay) -> chi chay 1 lan khi bat lai,
        # KHONG chay bu tung ngay da lo.
        coalesce=True,
        # Luot truoc chua xong thi KHONG khoi dong luot moi trong cung process.
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler: da dang ky job xuat phieu tu dong",
        extra={
            "gio_chay": f"{SCHEDULER_HOUR:02d}:{SCHEDULER_MINUTE:02d}",
            "timezone": _TIMEZONE,
        },
    )
    return scheduler


def dung_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        # wait=False: khong chan shutdown cua app de cho job dang chay xong
        # (job co the mat vai phut vi goi CTS/TTS). Dong job_run_log se ket
        # RUNNING - chap nhan duoc, dau vet do CHINH LA thu can de biet job bi
        # cat giua chung.
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler: da dung")
