"""
GET /qoe/{cell_name} — diem QoE tho theo ngay cua 1 cell.
GET /sessions/{id}/qoe-cells — danh gia QoE PER-CELL cua 1 cr_session.
Tu: yeu cau truc tiep user 16082026.

Doi xung voi api/routers/qos.py - CO Y sao chep nguyen cach validate from/to de
FE dung 2 endpoint theo CUNG MOT khuon, khong phai hoc luat moi.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.qoe_schemas import QoeCellItem, QoeCellsResponse
from api.schemas.qos_schemas import CuaSoNgay, NguongDanhGia
# Hang so nghiep vu doc THANG tu noi dinh nghia - KHONG go lai so (xem NguongDanhGia).
# QoE dung nguong RIENG (_QOE_CELL_THRESHOLD_DELTA) chu khong dung chung voi QoS: 2
# chi so co the doi doc lap, lay nham la response noi sai ve chinh minh
from application.get_qoe_cells_use_case import _QOE_CELL_THRESHOLD_DELTA  # noqa: PLC2701
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, MUC_TOI_THIEU
from application.get_qoe_cells_use_case import GetQoeCellsUseCase
from domain.ports.inbound.use_case_ports import IGetQoeSparklineUseCase
from infrastructure.dependencies import get_qoe_cells_use_case, get_qoe_sparkline_use_case

router = APIRouter()

# Giong _MAX_FROM_TO_WINDOW_DAYS trong qos.py - chan tren do rong window de
# khong ai vo tinh xin 1 nam du lieu. Voi CEM con quan trong hon QoS: 1 REQUEST
# = 1 NGAY, nen window 365 ngay = 365 request cho DUNG 1 cell.
_MAX_FROM_TO_WINDOW_DAYS = 60


@router.get("/qoe/{cell_name}")
async def get_qoe(
    cell_name: str,
    days: int = Query(default=7, ge=1, le=30),
    # alias "from"/"to" vi "from" la tu khoa Python - giong qos.py/sessions.py.
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    use_case: IGetQoeSparklineUseCase = Depends(get_qoe_sparkline_use_case),
) -> dict:
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    if from_date is not None or to_date is not None:
        if from_date is None or to_date is None:
            raise HTTPException(
                status_code=422,
                detail="Phai truyen ca 'from' va 'to' cung luc, hoac khong truyen cai nao (dung 'days')",
            )
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="'from' phai <= 'to'")
        if (to_date - from_date).days > _MAX_FROM_TO_WINDOW_DAYS:
            raise HTTPException(
                status_code=422,
                detail=f"Khoang 'from'-'to' toi da {_MAX_FROM_TO_WINDOW_DAYS} ngay",
            )
        # tzinfo=utc CHI de co datetime hop le truyen xuong adapter - CEM nhan
        # truong "date" dang yyyyMMdd (khong co gio) nen mui gio o day khong anh
        # huong ket qua, khac CTS (co hau to "Z").
        from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
        to_dt = datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc)

    data = await use_case.execute(cell_name, days, from_dt, to_dt)
    return {"cell_name": cell_name, "data": data}


@router.get("/sessions/{cr_session_id}/qoe-cells", response_model=QoeCellsResponse)
async def get_qoe_cells(
    cr_session_id: int,
    use_case: GetQoeCellsUseCase = Depends(get_qoe_cells_use_case),
) -> QoeCellsResponse:
    """Danh gia QoE cua TUNG cell bi anh huong trong session.

    ENDPOINT RIENG, CO Y KHONG nhet vao GET /sessions/{id}: endpoint do da tra
    cell_params + affected_cells + cr_logs + 2 snapshot (da phinh), va moi lan
    mo chi tiet session se phai cho 15 request CEM du nguoi dung khong xem tab
    QoE. Tach ra thi FE chi goi khi that su can.
    """
    ket_qua, cs = await use_case.danh_gia_kem_cua_so(cr_session_id)
    return QoeCellsResponse(
        cr_session_id=cr_session_id,
        # 3 truong cua so (04092026) - de FE hien duoc cau day du "6/7 ngay
        # (14-20/08)" va doi chieu 2 bang QoS/QoE khi so_ngay_* lech nhau.
        ngay_cr=cs["ngay_cr"],
        cua_so_before=CuaSoNgay(tu=cs["before_from"].date(), den=cs["before_to"].date()),
        cua_so_after=CuaSoNgay(tu=cs["after_from"].date(), den=cs["after_to"].date()),
        # THEM 18/10/2026 - None khi so lieu goi CTS/CEM truc tiep (chua danh gia).
        ngay_chup_snapshot=cs.get("ngay_chup_snapshot"),
        # SUA 03/10/2026: _QOE_CELL_THRESHOLD_DELTA gio DA la so duong (0.5) -
        # KHONG con doi dau o day nua (truoc day hang so goc la am).
        nguong=NguongDanhGia(
            delta_toi_da=_QOE_CELL_THRESHOLD_DELTA,
            muc_toi_thieu=MUC_TOI_THIEU,
            so_ngay_toi_thieu=MIN_DAYS_REQUIRED,
        ),
        total=len(ket_qua),
        data=[
            QoeCellItem(
                cell_name=r.cell_name,
                avg_before=r.qoe_eval.avg_before,
                avg_after=r.qoe_eval.avg_after,
                delta=r.delta,
                so_ngay_before=r.so_ngay_before,
                so_ngay_after=r.so_ngay_after,
                ket_qua=r.qoe_eval.result,
                diem_thap_nhat_sau=r.qoe_eval.diem_thap_nhat_sau,
                so_ngay_dat_sau=r.qoe_eval.so_ngay_dat_sau,
            )
            for r in ket_qua
        ],
    )
