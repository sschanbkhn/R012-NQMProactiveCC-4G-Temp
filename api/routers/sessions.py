"""
GET /sessions, GET /sessions/{id}.
Tu: ARCHITECTURE.md Section 6.1; API_CONTRACTS.md Section 6; TASK_LIST.md C1.6
"""

from datetime import datetime
from enum import IntEnum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.session_schemas import (
    AffectedCellItem,
    CellParamDetailItem,
    CrLogItem,
    SessionDetailResponse,
    SessionListItem,
    SessionListResponse,
    XoaSessionResponse,
)
from domain.ports.inbound.use_case_ports import IGetSessionDetailUseCase, IGetSessionsUseCase
from domain.ports.outbound.repo_ports import ICrSessionRepo, SessionFilter
from domain.services.danh_gia_dieu_kien_cr_moi import gan_nhan_ngoai_dieu_kien_moi
from application.xoa_session_use_case import XoaSessionUseCase
from fastapi.responses import PlainTextResponse
from pathlib import Path
from infrastructure.dependencies import (
    get_cr_session_repo,
    get_session_detail_use_case,
    get_sessions_use_case,
    get_xoa_session_use_case,
)

# goc project - tinh tu vi tri file nay (api/routers/sessions.py -> len 2 cap).
# Dung de resolve duong_dan_log (luu dang TUONG DOI trong DB de khong vo khi
# deploy sang may khac) va de chan path traversal.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

router = APIRouter()

# Sort server-side (22072026, xac nhan voi user) - FE truoc gio sort
# client-side CHI tren 1 trang da fetch (sai pham vi, gay hieu nham). Dung
# Literal (khong phai str thuong) cho sort_by - BAT BUOC whitelist, tranh SQL
# injection va sort vao cot khong ton tai: gia tri ngoai danh sach nay bi
# FastAPI/Pydantic tu choi NGAY O TANG VALIDATE (422 kem thong bao ro cac gia
# tri hop le), request KHONG BAO GIO toi duoc code xu ly - an toan hon tu
# kiem tra bang if/else trong than ham (co the quen 1 nhanh).
_SessionSortBy = Literal["id", "tram_id", "tram_name", "action", "status", "executed_at", "created_at"]
_SortOrder = Literal["asc", "desc"]


class BuocFilter(IntEnum):
    """Gia tri hop le cho query param ?buoc= (16082026).

    Dung IntEnum CHU KHONG PHAI Literal[1, 2, 4]: query param toi router luon la
    CHUOI ("4"), ma Literal so nguyen KHONG ep kieu chuoi -> moi request
    ?buoc=4 deu 422 "Input should be 1, 2 or 4" (bat duoc bang test truoc khi
    len UI). IntEnum thi Pydantic ep "4" -> BuocFilter.XUAT_PHIEU binh thuong.

    KHONG co gia tri 3: buoc 3 (dang danh gia) la trang thai thoang qua trong 1
    luot job, khong session nao nam o do. ?buoc=3 -> 422 (ro rang), thay vi tra
    danh sach rong (gay hieu nham "khong con session nao dang danh gia").
    """

    CR = 1  # CR dang chay hoac loi
    CHO_KPI = 2  # CR xong, dang cho thu thap KPI
    XUAT_PHIEU = 4  # da xuat phieu xong


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    q: str | None = None,
    status: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    sort_by: _SessionSortBy | None = None,
    order: _SortOrder = "desc",
    # Loc theo tien trinh (16082026) - xem BuocFilter.
    buoc: BuocFilter | None = None,
    qua_han: bool = False,
    use_case: IGetSessionsUseCase = Depends(get_sessions_use_case),
) -> SessionListResponse:
    filters = SessionFilter(
        q=q,
        status=status,
        date_from=from_,
        date_to=to,
        page=page,
        size=size,
        sort_by=sort_by,
        order=order,
        buoc=buoc,
        qua_han=qua_han,
    )
    result = await use_case.execute(filters)
    return SessionListResponse(
        total=result.total,
        data=[
            SessionListItem(
                id=r.session.id,
                tram_id=r.session.tram_id,
                tram_name=r.session.tram_name,
                action=r.session.action,
                status=r.session.status.value,
                qoe_result=r.session.qoe_result,
                qos_result=r.session.qos_result,
                executed_at=r.session.executed_at,
                evaluated_at=r.session.evaluated_at,
                created_at=r.session.created_at,
                # 3 con so dem tu repo (subquery), 3 gia tri tinh o use case -
                # router CHI anh xa, khong tinh gi (ARCHITECTURE.md SS6.1).
                so_cell_anh_huong=r.session.so_cell_anh_huong,
                so_phieu_da_xuat=r.session.so_phieu_da_xuat,
                so_cell_cho_xuat_tay=r.session.so_cell_cho_xuat_tay,
                ngay_du_kien_xuat_phieu=r.ngay_du_kien_xuat_phieu,
                con_bao_nhieu_ngay=r.con_bao_nhieu_ngay,
                buoc_hien_tai=r.buoc_hien_tai,
                so_cell_thanh_cong=r.session.so_cell_thanh_cong,
                so_cell_tong=r.session.so_cell_tong,
                oss_instance_id=r.session.oss_instance_id,
                noc=r.session.noc,
                ma_loi=r.session.ma_loi,
                so_cell_ngoai_dieu_kien_moi=r.so_cell_ngoai_dieu_kien_moi,
            )
            for r in result.items
        ],
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: int,
    use_case: IGetSessionDetailUseCase = Depends(get_session_detail_use_case),
) -> SessionDetailResponse:
    detail = await use_case.execute(session_id)
    s = detail.session
    # ngoai_dieu_kien_moi (THEM 04/10/2026, quyet dinh 04/10/2026 - CHI DOC,
    # KHONG sua cell_params/cr_affected_cells cu) - gan nhan LUC DOC, tinh tu
    # detail.affected_cells (cr_affected_cells CUNG session, mang dist_name
    # that cua tung cell) doi chieu voi detail.cell_params (cell DA CHAY CR).
    # Session cu (truoc 22/07/2026, Phuong an B) khong co affected_cells nao
    # -> dist_name_theo_cell rong -> MOI cell deu nhan KHONG_XAC_DINH_BAND
    # (dung y, khong phai loi - xem domain/services/danh_gia_dieu_kien_cr_moi.py).
    dist_name_theo_cell = {
        c["cell_name"]: c["dist_name"] for c in detail.affected_cells if c.get("dist_name")
    }
    ngoai_dieu_kien_moi_theo_cell = gan_nhan_ngoai_dieu_kien_moi(detail.cell_params, dist_name_theo_cell)
    return SessionDetailResponse(
        id=s.id,
        tram_id=s.tram_id,
        tram_name=s.tram_name,
        action=s.action,
        status=s.status.value,
        plan_name=s.plan_name,
        qoe_result=s.qoe_result,
        qos_result=s.qos_result,
        qoe_before=s.qoe_before,
        qoe_after=s.qoe_after,
        qos_before=s.qos_before,
        qos_after=s.qos_after,
        executed_at=s.executed_at,
        evaluated_at=s.evaluated_at,
        duong_dan_log=s.duong_dan_log,
        oss_instance_id=s.oss_instance_id,
        noc=s.noc,
        ma_loi=s.ma_loi,
        cell_params=[
            CellParamDetailItem(
                cell_name=cp.cell_name,
                huong_id=cp.huong_id,
                priority=cp.priority,
                action_type=cp.action_type,
                rsboost_before_cr=cp.rsboost_before_cr.value if cp.rsboost_before_cr else None,
                rsboost_new=cp.rsboost_new.value if cp.rsboost_new else None,
                qrxlevmin_before_cr=cp.qrxlevmin_before_cr.value if cp.qrxlevmin_before_cr else None,
                qrxlevmin_new=cp.qrxlevmin_new.value if cp.qrxlevmin_new else None,
                ngoai_dieu_kien_moi=ngoai_dieu_kien_moi_theo_cell.get(cp.cell_name, []),
            )
            for cp in detail.cell_params
        ],
        affected_cells=[
            AffectedCellItem(cell_name=c["cell_name"], tram_id=c["tram_id"], huong_id=c["huong_id"])
            for c in detail.affected_cells
        ],
        # 22072026 (xac nhan voi user) - THAT su doc tu cr_log (truoc gio LUON
        # [] - xem chu y day du trong application/get_session_detail_use_case.py).
        cr_logs=[
            CrLogItem(
                step=log["step"],
                step_name=log["step_name"],
                status=log["status"],
                message=log["message"],
                pct=log["pct"],
                ma_loi=log["ma_loi"],
                created_at=log["created_at"],
            )
            for log in detail.cr_logs
        ],
    )


@router.get("/sessions/{session_id}/log-netact", response_class=PlainTextResponse)
async def doc_log_netact(
    session_id: int,
    repo: ICrSessionRepo = Depends(get_cr_session_repo),
) -> PlainTextResponse:
    """Doc file log NetAct cua 1 session (B6).

    Tra ve text tho chu KHONG boc JSON: day la noi dung log nhieu dong de nguoi
    doc/copy ra file, boc JSON chi lam no thanh 1 chuoi dai co 
 ma FE lai phai
    tu tach ra.

    === VI SAO CAN ENDPOINT NAY ===
    Khi CR bao PARTIAL_SUCCESS/FAILED, cau hoi dau tien luon la "NetAct tra ve gi".
    Truoc day phai SSH vao server doc file tay - trong khi file da nam san tren
    dia cua BE. Ket hop voi cr_session.duong_dan_log (A6) thi doc duoc ngay tu UI.
    """
    session = await repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"cr_session id={session_id} khong ton tai")
    if not session.duong_dan_log:
        # 404 chu khong phai 200 kem chuoi rong: "khong co log" va "log rong" la
        # 2 chuyen khac nhau, tra 200 se lam FE hien mot khung trong kho hieu.
        # Session cu (chay truoc dot 02092026) deu roi vao nhanh nay.
        raise HTTPException(
            status_code=404,
            detail=f"cr_session id={session_id} khong co duong_dan_log (chay truoc khi co co che luu log)",
        )

    # CHONG PATH TRAVERSAL: duong_dan_log do BE tu ghi nen ve nguyen tac an toan,
    # nhung day la endpoint DOC FILE theo gia tri lay tu DB - neu cot do bi sua
    # tay thanh "../../.env" thi se doc mat file cau hinh. Ep duong dan phai nam
    # TRONG thu muc log da dinh truoc khi mo.
    goc_log = (_PROJECT_ROOT / "docs" / "logs" / "netact_runs").resolve()
    duong_dan = (_PROJECT_ROOT / session.duong_dan_log).resolve()
    if not duong_dan.is_relative_to(goc_log):
        raise HTTPException(status_code=400, detail="duong_dan_log nam ngoai thu muc log cho phep")
    if not duong_dan.is_file():
        # File da bi xoa/don dep - phan biet ro voi "chua bao gio co"
        raise HTTPException(status_code=404, detail=f"Khong tim thay file log: {session.duong_dan_log}")

    # errors="replace": log NetAct co the lan ky tu khong phai UTF-8; tha hien
    # vai ky tu hong con hon nem 500 va khong doc duoc gi ca
    return PlainTextResponse(duong_dan.read_text(encoding="utf-8", errors="replace"))


@router.delete("/sessions/{session_id}", response_model=XoaSessionResponse)
async def xoa_session(
    session_id: int,
    use_case: XoaSessionUseCase = Depends(get_xoa_session_use_case),
) -> XoaSessionResponse:
    """Xoa session FAILED/KHONG_CHAY + toan bo dong con. CHI 2 trang thai nay - xem use case.

    Cac DomainError bubble tu nhien len global handler (api/middleware/
    error_handler.py): CR_SESSION_NOT_FOUND -> 404,
    XOA_SESSION_KHONG_HOP_LE -> 409 kem message noi ro bao nhieu tram da doi
    RF that. KHONG try/except o day - dung pattern cua preview_cr()/xuat_phieu().
    """
    so_dong = await use_case.execute(session_id)
    return XoaSessionResponse(id=session_id, da_xoa=True, so_dong_da_xoa=so_dong)
