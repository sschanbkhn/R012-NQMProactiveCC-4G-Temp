"""
POST /jobs/sync-*, POST /jobs/evaluate-cr — n8n trigger, tra 202 + background task.
GET  /jobs/runs, GET /jobs/runs/{id} — lich su chay job (bang job_run_log), V3a
12/08: FE can hien trong tab Lich su phieu, truoc do chi doc duoc bang SQL tay.
Tu: ARCHITECTURE.md Section 6.1; CONTEXT.md Section 5.5; API_CONTRACTS.md Section 6;
TASK_LIST.md C1.8

PHAM VI (13072026, Nhom 3): POST /jobs/evaluate-cr (C2.2), /jobs/sync-rims (C2.5),
/jobs/sync-netact (C2.6) da duoc wire that. sync-status (BUSINESS_RULES.md SS10.3)
VAN CHUA co - khong co script/logic nao da chay that de boc lai (khac 2 job kia,
da co script thu cong xac nhan chay that) - KHONG tao route rong/nua-vau.

TU GIA DINH - CAN XAC NHAN (dat ten route): user yeu cau ten "/jobs/sync-enodeb"
va "/jobs/sync-cell-params", nhung API_CONTRACTS.md dong 731-734 + BUSINESS_RULES.md
SS10 da dat ten "/jobs/sync-rims" va "/jobs/sync-netact" cho 2 job nay (n8n/FE co
the da phu thuoc ten cu). Da CHON dung dung ten trong docs (sync-rims/sync-netact)
de khop dung API_CONTRACTS.md - can xac nhan lai neu muon doi ten.

Dependencies with yield (get_session) van con song qua luc BackgroundTasks chay -
FastAPI dam bao cleanup code (sau yield) chi chay SAU KHI background task hoan
thanh, nen AsyncSession khong bi dong som.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from api.routers.loc_ngay import khoang_ngay_gmt7
from api.schemas.job_schemas import (
    ChayJobXuatPhieuRequest,
    JobRunDetail,
    JobRunListItem,
    JobRunListResponse,
    XemTruocResponse,
)
from application.evaluate_cr_use_case import EvaluateCrUseCase
from domain.ports.inbound.use_case_ports import ISyncCellParamsUseCase, ISyncEnodebUseCase
from domain.ports.outbound.repo_ports import IJobRunLogRepo
from application.xuat_phieu_use_case import XUAT_PHIEU_AFTER_DAYS, XuatPhieuUseCase
from infrastructure.advisory_lock import KHOA_XUAT_PHIEU, giu_khoa
from infrastructure.dependencies import (
    get_evaluate_cr_use_case,
    get_job_run_log_repo,
    get_sync_cell_params_use_case,
    get_sync_enodeb_use_case,
    get_xuat_phieu_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Whitelist BAT BUOC bang Literal (khong phai str thuong) - FastAPI/Pydantic tu
# tra 422 ngay o tang validate, request khong bao gio toi duoc code xu ly. Cung
# co che da dung o /phieu, /sessions va /stations (C1.6-fix).
#
# 3 gia tri khop models/job_run_log.py::trang_thai. KHONG an gia tri nao.
# PARTIAL them 02092026 (B3): luot chay co CA phieu thanh cong LAN phieu that
# bai. Phai co trong enum LOC nay, khong thi FE khong loc rieng ra duoc dung
# nhung luot can xem nhat - va gui ?trang_thai=PARTIAL se bi tra 422.
_JobRunTrangThai = Literal["RUNNING", "DONE", "FAILED", "PARTIAL"]
_JobRunSortBy = Literal["id", "job_type", "started_at", "finished_at", "trang_thai"]
_SortOrder = Literal["asc", "desc"]

@router.post("/jobs/sync-rims", status_code=202)
async def job_sync_rims(
    background_tasks: BackgroundTasks,
    tram_id: str | None = None,
    use_case: ISyncEnodebUseCase = Depends(get_sync_enodeb_use_case),
) -> dict:
    # tram_id: query param TUY CHON, khong co trong API_CONTRACTS.md (endpoint
    # goc khong co tham so) - them de tien test nhanh 1 tram (dung y nghia
    # --tram-id cua script thu cong cu), mac dinh None = sync toan bo nhu docs.
    background_tasks.add_task(use_case.execute, tram_id)
    return {
        "job": "sync-rims",
        "status": "accepted",
        "message": "Job da duoc nhan, dang chay background",
    }


@router.post("/jobs/sync-netact", status_code=202)
async def job_sync_netact(
    background_tasks: BackgroundTasks,
    file_path: str,
    use_case: ISyncCellParamsUseCase = Depends(get_sync_cell_params_use_case),
) -> dict:
    # file_path: TU GIA DINH (xem application/sync_cell_params_use_case.py) -
    # duong dan file CSV DA CO SAN tren server BE, KHONG PHAI file upload qua
    # HTTP (khong co dinh nghia contract nao trong docs cho viec nay).
    background_tasks.add_task(use_case.execute, file_path)
    return {
        "job": "sync-netact",
        "status": "accepted",
        "message": "Job da duoc nhan, dang chay background",
    }


@router.get("/jobs/runs", response_model=JobRunListResponse)
async def list_job_runs(
    job_type: str | None = None,
    trang_thai: _JobRunTrangThai | None = None,
    # NGAY LICH GMT+7, ca hai DOC LAP nhau (khac /qos from+to phai di cap):
    # "tu 01/08 den nay" va "truoc 01/08" deu la cach loc tu nhien o man hinh
    # lich su, ep truyen ca cap chi lam FE phai bia 1 dau mut.
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    page: int = Query(default=1, ge=1),
    # le=100 theo dung yeu cau V3a. Thap hon /phieu (le=200) vi 1 dong o day la
    # tong ket ca luot chay - 100 dong da la vai thang lich su.
    size: int = Query(default=20, ge=1, le=100),
    sort_by: _JobRunSortBy | None = None,
    order: _SortOrder = "desc",
    job_run_log_repo: IJobRunLogRepo = Depends(get_job_run_log_repo),
) -> JobRunListResponse:
    # Goi THANG repo (khong qua use case) - dung tien le GET /phieu va GET
    # /stations: read-model thuan cho 1 man hinh, chi co filter + phan trang +
    # sort, khong co nghiep vu nao de dat vao application/.
    # Luat loc ngay (nua khoang [tu, den+1) + rang buoc tu <= den) da tach ra
    # api/routers/loc_ngay.py de GET /phieu dung CHUNG - 2 man hinh lich su phai
    # hieu "tu ngay X den ngay Y" giong het nhau.
    tu_moc, den_moc = khoang_ngay_gmt7(tu_ngay, den_ngay)

    total = await job_run_log_repo.count_job_runs(job_type, trang_thai, tu_moc, den_moc)
    rows = await job_run_log_repo.list_job_runs(
        job_type, page, size, sort_by, order, trang_thai, tu_moc, den_moc
    )
    return JobRunListResponse(
        total=total,
        page=page,
        size=size,
        data=[JobRunListItem(**row) for row in rows],
    )


@router.get("/jobs/runs/{id}", response_model=JobRunDetail)
async def get_job_run(
    id: int,
    job_run_log_repo: IJobRunLogRepo = Depends(get_job_run_log_repo),
) -> JobRunDetail:
    # Endpoint RIENG thay vi ?include_chi_tiet=true tren /jobs/runs: hinh dang
    # tra ve co dinh (FE khai bao 1 kieu cho danh sach, 1 kieu cho chi tiet,
    # khong phai kieu "co the co chi_tiet tuy query param"), va khong the vo
    # tinh keo 100 dong chi_tiet cung luc.
    row = await job_run_log_repo.get_by_id(id)
    if row is None:
        # 404 do ROUTER quyet dinh - repo tra None vi no khong biet gi ve HTTP.
        raise HTTPException(status_code=404, detail=f"Khong tim thay luot chay job id={id}")
    return JobRunDetail(**row)


@router.post("/jobs/evaluate-cr", status_code=202)
async def job_evaluate_cr(
    background_tasks: BackgroundTasks,
    use_case: EvaluateCrUseCase = Depends(get_evaluate_cr_use_case),
) -> dict:
    background_tasks.add_task(use_case.execute_all_pending)
    return {
        "job": "evaluate-cr",
        "status": "accepted",
        "message": "Job da duoc nhan, dang chay background",
    }

# === CHAY JOB XUAT PHIEU BANG TAY (20082026, yeu cau truc tiep user) ===
#
# VI SAO CAN (khong phai de test): PA A quet DUNG 1 ngay
# (executed_at::date == hom nay - XUAT_PHIEU_AFTER_DAYS). Job lo 1 ngay la MAT
# VINH VIEN ngay CR do - khong co duong chay bu nao ngoai xuat tay tung cell.
# Day la duong cuu duy nhat.

# job_type RIENG cho luot chay tay. KHONG them cot vao job_run_log: cot
# job_type la VARCHAR(50) co index va model da ghi ro y dinh "them loai job
# moi chi la them gia tri, KHONG phai migration doi kieu". Them cot se can
# migration VA bat moi cho doc phai xu ly 2 chieu.
JOB_TYPE_XUAT_PHIEU_TAY = "xuat_phieu_manual"

# Toi da 30 ngay 1 lan chay. VI SAO PHAI CO TRAN: khong co no thi 1 lan go
# nham nam (2025-01-01 -> 2026-08-20) se quet vai tram session, moi session
# ~48 request CTS/CEM va POST phieu THAT len CTS - khong dung lai duoc giua
# chung va khong thu hoi duoc. 30 ngay du rong cho moi tinh huong chay bu that
# (job lo lau nhat tu truoc den nay la 1 ngay).
_SO_NGAY_TOI_DA = 30


def _hom_nay_gmt7() -> date:
    # GMT+7 - CUNG cach tinh voi _lay_session_du_dieu_kien() (_to_gmt7). Lay
    # .date() tren UTC se lech 1 ngay trong khung UTC 17:00-23:59.
    return (datetime.now(timezone.utc) + timedelta(hours=7)).date()


def _kiem_khoang_ngay(tu_ngay: date, den_ngay: date) -> None:
    """3 chan an toan. Raise HTTPException 422 kem thong bao doc duoc.

    Dat o ROUTER chu khong o use case: day la luat cua GIAO DIEN (chan nguoi
    bam nham), khong phai luat nghiep vu. Script chay tay hoac job tuong lai
    van goi thang use case voi khoang bat ky khi co ly do chinh dang.
    """
    if tu_ngay > den_ngay:
        raise HTTPException(
            status_code=422,
            detail=f"tu_ngay ({tu_ngay}) phai <= den_ngay ({den_ngay})",
        )

    so_ngay = (den_ngay - tu_ngay).days + 1
    if so_ngay > _SO_NGAY_TOI_DA:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Khoang {so_ngay} ngay vuot gioi han {_SO_NGAY_TOI_DA} ngay. "
                "Chia nho thanh nhieu lan chay."
            ),
        )

    # Ngay CR phai da du XUAT_PHIEU_AFTER_DAYS ngay de co du 7 ngay KPI sau CR.
    # Khong chan thi job se danh gia tren cua so con thieu ngay va ket luan
    # sai - te hon la khong chay.
    han_cuoi = _hom_nay_gmt7() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
    if den_ngay > han_cuoi:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Session CR sau ngay {han_cuoi} chua du {XUAT_PHIEU_AFTER_DAYS} ngay "
                f"de danh gia. den_ngay toi da la {han_cuoi}."
            ),
        )


@router.post("/jobs/xuat-phieu-auto/xem-truoc", response_model=XemTruocResponse)
async def xem_truoc_xuat_phieu(
    body: ChayJobXuatPhieuRequest,
    use_case: XuatPhieuUseCase = Depends(get_xuat_phieu_use_case),
) -> XemTruocResponse:
    """Xem truoc: quet + danh gia DAY DU, KHONG POST CTS, KHONG ghi DB.

    === VI SAO BAT BUOC CO BUOC NAY ===
    POST phieu la hanh dong KHONG THU HOI - phieu da len CTS thi xoa dong
    cr_phieu ben nay cung khong go duoc phieu ben do. Bam nham 1 khoang ngay
    rong = hang tram phieu THAT len CTS. Nguoi bam PHAI biet truoc so luong.

    === VI SAO DONG BO (khong 202 nhu cac job khac o file nay) ===
    Mot nut "xem truoc" tra 202 roi bat nguoi dung di tra ket qua o cho khac
    thi khong con la xem truoc - ho bam no CHINH VI can con so NGAY LUC DO de
    quyet dinh co bam nut chay that hay khong.

    DANH DOI DA BIET: goi CTS + CEM day du (~48 request/session) nen co the
    mat vai phut voi khoang 30 ngay. Tran 30 ngay giu cho no huu han; FE de
    timeout dai cho RIENG nut nay.
    """
    _kiem_khoang_ngay(body.tu_ngay, body.den_ngay)
    ket_qua = await use_case.xem_truoc(body.tu_ngay, body.den_ngay)
    return XemTruocResponse(**ket_qua)


@router.post("/jobs/xuat-phieu-auto", status_code=202)
async def chay_xuat_phieu_bang_tay(
    body: ChayJobXuatPhieuRequest,
    background_tasks: BackgroundTasks,
    job_run_log_repo: IJobRunLogRepo = Depends(get_job_run_log_repo),
    use_case: XuatPhieuUseCase = Depends(get_xuat_phieu_use_case),
) -> dict:
    """Chay THAT: POST phieu len CTS. 202 + background.

    === KIEM KHOA TRUOC KHI TRA 202 (dong bo) ===
    Neu de viec lay khoa trong background thi 409 KHONG BAO GIO toi duoc nguoi
    bam - ho nhan 202 "da nhan" roi khong co gi xay ra, va se bam lai. Vi vay
    thu khoa NGAY tai day, chi tra 202 khi da chac chan co suat chay.

    Khoa la CUNG MOT khoa voi job tu dong (infrastructure/advisory_lock.py) -
    do la muc dich: 2 duong cung xuat phieu ma chay chong nhau se POST 2 phieu
    cho cung 1 cell.
    """
    _kiem_khoang_ngay(body.tu_ngay, body.den_ngay)

    # Thu khoa DONG BO roi nha ra ngay - background task tu lay lai.
    #
    # CUA SO HO da biet va CHAP NHAN: giua luc nha o day va luc background lay
    # lai, job tu dong CO THE chen vao; luc do background bo luot va ghi FAILED
    # kem ly do. VI SAO chap nhan: giu khoa xuyen qua ranh gioi request ->
    # background doi hoi connection asyncpg song ngoai vong doi request, ma neu
    # request bi huy giua chung thi khoa treo den khi connection timeout - JOB
    # TU DONG SANG HOM SAU KHONG CHAY DUOC. Danh doi nguoc lai te hon nhieu, va
    # cua so ho o day chi vai mili giay trong khi job tu dong chay 1 lan/ngay.
    async with giu_khoa(KHOA_XUAT_PHIEU) as lay_duoc:
        if not lay_duoc:
            raise HTTPException(status_code=409, detail="Job xuat phieu dang chay, thu lai sau")

    job_run = await job_run_log_repo.insert(
        {"job_type": JOB_TYPE_XUAT_PHIEU_TAY, "trang_thai": "RUNNING"}
    )

    background_tasks.add_task(
        _chay_nen_co_khoa, use_case, job_run_log_repo, job_run["id"], body.tu_ngay, body.den_ngay
    )
    return {
        "job": "xuat-phieu-auto",
        "status": "accepted",
        "job_run_log_id": job_run["id"],
        "tu_ngay": str(body.tu_ngay),
        "den_ngay": str(body.den_ngay),
        "message": (
            "Job da duoc nhan, dang chay background - SE POST PHIEU THAT len CTS. "
            "Theo doi ket qua tai GET /jobs/runs/{}".format(job_run["id"])
        ),
    }


async def _chay_nen_co_khoa(
    use_case: XuatPhieuUseCase,
    job_run_log_repo: IJobRunLogRepo,
    job_run_log_id: int,
    tu_ngay: date,
    den_ngay: date,
) -> None:
    """Background task: lay lai khoa roi chay. NUOT loi - khong ai bat ho."""
    async with giu_khoa(KHOA_XUAT_PHIEU) as lay_duoc:
        if not lay_duoc:
            # Job tu dong chen vao giua (xem chu y ve cua so ho o tren). Ghi
            # FAILED de nguoi bam THAY - de dong RUNNING treo se bi hieu nham
            # thanh "job chet giua chung".
            logger.warning(
                "Chay tay: khong lay duoc khoa o background, bo luot",
                extra={"job_run_log_id": job_run_log_id},
            )
            await _ghi_that_bai(
                job_run_log_repo, job_run_log_id, "Job khac da chiem khoa truoc, luot nay khong chay"
            )
            return

        try:
            logger.warning(
                "Chay tay: BAT DAU - SE POST PHIEU THAT len TTS",
                extra={
                    "job_run_log_id": job_run_log_id,
                    "tu_ngay": str(tu_ngay),
                    "den_ngay": str(den_ngay),
                },
            )
            await use_case.execute_all_pending(
                job_run_log_id=job_run_log_id, tu_ngay=tu_ngay, den_ngay=den_ngay
            )
        except Exception as exc:  # noqa: BLE001 - background task, khong ai bat loi ho.
            # execute_all_pending() da tu ghi FAILED vao job_run_log truoc khi
            # raise nen o day CHI log, KHONG ghi de lan nua.
            logger.error(
                "Chay tay: luot chay THAT BAI",
                extra={"job_run_log_id": job_run_log_id, "loi": str(exc)},
            )


async def _ghi_that_bai(job_run_log_repo: IJobRunLogRepo, job_run_log_id: int, ly_do: str) -> None:
    try:
        await job_run_log_repo.update_result(
            job_run_log_id,
            trang_thai="FAILED",
            finished_at=datetime.now(timezone.utc),
            error_message=ly_do,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Chay tay: khong ghi duoc FAILED vao job_run_log", extra={"loi": str(exc)})
