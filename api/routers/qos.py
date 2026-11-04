"""
GET /qos/{cell_name}.
Tu: ARCHITECTURE.md Section 6.1; API_CONTRACTS.md Section 6 (GET /qos/{cell_name});
TASK_LIST.md C1.7
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.qos_schemas import CuaSoNgay, NguongDanhGia, QosCellItem, QosCellsResponse
# Import THANG hang so nghiep vu de dien vao response - KHONG go lai so.
# _XUAT_PHIEU_QOS_THRESHOLD_DELTA la private cua module (dau _) nhung day chinh la
# hang so ma danh_gia_qos_tu_diem() dung; doc no o day de response va ket_qua khong
# the lech nhau. noqa PLC2701: co y import private, get_qos_cells_use_case cung da
# lam vay voi cung module nay
from application.xuat_phieu_use_case import _XUAT_PHIEU_QOS_THRESHOLD_DELTA  # noqa: PLC2701
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, MUC_TOI_THIEU
from application.get_qos_cells_use_case import GetQosCellsUseCase
from domain.ports.inbound.use_case_ports import IGetQosSparklineUseCase
from infrastructure.dependencies import get_qos_cells_use_case, get_qos_sparkline_use_case

router = APIRouter()

# Gap 1 (22072026, xac nhan voi user) - chan tren do rong window from/to, tranh
# user tu do chon 1 khoang qua lon lam CTS bi query qua nang (khac "days" da co
# san max=30 - from/to phuc vu truong hop can neo vao 1 ngay CU THE trong qua
# khu, VD quanh ngay CR, nen can rong hon 30 nhung van phai co tran).
_MAX_FROM_TO_WINDOW_DAYS = 60


@router.get("/qos/{cell_name}")
async def get_qos(
    cell_name: str,
    # days them sau (21072026, xac nhan voi user) - phuc vu chart QoS nhieu
    # ngay trong preview CR, khong chi Widget F33. Max=30 chan tren de tranh
    # goi CTS voi window qua rong khong can thiet (BR-05 chi can toi da 7+7).
    days: int = Query(default=7, ge=1, le=30),
    # from/to them Gap 1 (22072026) - lay QoS quanh 1 ngay CR TRONG QUA KHU
    # (vd danh gia lai 1 CR cu), "days" khong lam duoc vi luon neo cung to_dt=
    # hom qua (xem GetQosSparklineUseCase). Optional, alias "from"/"to" vi
    # "from" la tu khoa Python khong dat ten bien duoc (cung cach lam voi
    # api/routers/sessions.py::list_sessions() da co san).
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    use_case: IGetQosSparklineUseCase = Depends(get_qos_sparkline_use_case),
) -> dict:
    # KHONG truyen from/to -> giu NGUYEN hanh vi cu (window tu "days" neo vao
    # hom qua) - FE hien tai dang dung days, khong duoc pha (xac nhan pham vi
    # voi user). Chi khi truyen CA HAI from/to moi chuyen sang window tuong minh.
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
        # Mui gio: CTS nhan hau to "Z" nhung hieu la wall-clock GMT+7 (KHONG
        # phai UTC that - da xac nhan qua evaluate_cr_use_case.py, cung 1
        # gateway gw-oneoss.vnpt.vn) - gan tzinfo=utc o day CHI de co doi
        # tuong datetime hop le truyen xuong CtsHttpAdapter.strftime() dung
        # dinh dang "%Y-%m-%dT%H:%M:%SZ", KHONG phai convert UTC that. from/to
        # la NGAY LICH GMT+7 nguoi dung muon xem (vd ngay CR that).
        from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
        to_dt = datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc)

    data = await use_case.execute(cell_name, days, from_dt, to_dt)
    return {"cell_name": cell_name, "data": data}


@router.get("/sessions/{cr_session_id}/qos-cells", response_model=QosCellsResponse)
async def get_qos_cells(
    cr_session_id: int,
    use_case: GetQosCellsUseCase = Depends(get_qos_cells_use_case),
) -> QosCellsResponse:
    """Danh gia QoS cua TUNG cell bi anh huong trong session.

    Ban DOI XUNG cua GET /sessions/{id}/qoe-cells. Muc dich: FE thoi tu tinh
    lai luat trong qosEvaluation.ts - ban sao do da troi khoi BE 2 lan (lan
    gan nhat thieu ve avg_after >= 4.0, lam cell 117449 bi gan nhan KHONG DAT
    trong khi BE ket luan DAT).

    !!! CHI PHI KHAC HAN ban QoE !!!
    CTS tinh 1 REQUEST/CELL/CUA SO -> 17 cell = 34 request (2/cell).
    CEM thi 1 request/NGAY cho CA danh sach cell -> 15 request bat ke bao nhieu
    cell. Nen endpoint nay dat len TUYEN TINH theo so cell, con qoe-cells thi
    khong. Da giam bang lazy cache: cell nao co du 7+7 ngay trong qos_snapshot
    thi doc DB, 0 request. Sau khi job xuat phieu (T+8) chay, gan nhu moi cell
    deu co snapshot.
    """
    ket_qua, cs = await use_case.danh_gia_kem_cua_so(cr_session_id)
    return QosCellsResponse(
        cr_session_id=cr_session_id,
        # 3 truong cua so (04092026) - de FE hien duoc cau day du "6/7 ngay
        # (14-20/08)" va doi chieu 2 bang QoS/QoE khi so_ngay_* lech nhau.
        ngay_cr=cs["ngay_cr"],
        cua_so_before=CuaSoNgay(tu=cs["before_from"].date(), den=cs["before_to"].date()),
        cua_so_after=CuaSoNgay(tu=cs["after_from"].date(), den=cs["after_to"].date()),
        # THEM 18/10/2026 - None khi so lieu goi CTS/CEM truc tiep (chua danh gia).
        ngay_chup_snapshot=cs.get("ngay_chup_snapshot"),
        # LAY TU CHINH HANG SO, tuyet doi khong go lai so o day - go lai la tao them
        # mot ban sao nua, dung cai benh dang chua.
        # SUA 03/10/2026: _XUAT_PHIEU_QOS_THRESHOLD_DELTA gio DA la so duong
        # (0.5) - KHONG con doi dau o day nua (truoc day hang so goc la am).
        # Day CHINH LA hang so ma danh_gia_qos_tu_diem() dung de xep loai, nen
        # khong the lech voi ket_qua tra kem.
        nguong=NguongDanhGia(
            delta_toi_da=_XUAT_PHIEU_QOS_THRESHOLD_DELTA,
            muc_toi_thieu=MUC_TOI_THIEU,
            so_ngay_toi_thieu=MIN_DAYS_REQUIRED,
        ),
        total=len(ket_qua),
        data=[
            QosCellItem(
                cell_name=r.cell_name,
                avg_before=r.qos_eval.avg_before,
                avg_after=r.qos_eval.avg_after,
                delta=r.delta,
                so_ngay_before=r.so_ngay_before,
                so_ngay_after=r.so_ngay_after,
                ket_qua=r.qos_eval.result,
                diem_thap_nhat_sau=r.qos_eval.diem_thap_nhat_sau,
                so_ngay_dat_sau=r.qos_eval.so_ngay_dat_sau,
            )
            for r in ket_qua
        ],
    )
