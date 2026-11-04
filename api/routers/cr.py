"""
POST /cr/trigger.
Tu: ARCHITECTURE.md Section 6.1; API_CONTRACTS.md Section 6 (POST /cr/trigger);
TASK_LIST.md C1.4

C1.4-fix (20072026): DA SUA bug thiet ke goc — truoc day router await ca
TriggerCrUseCase.execute() (guard+tao session VA toan bo 18 buoc, bao gom SSH
NetAct that o buoc 13-16, co the mat vai chuc giay/vai phut), khien HTTP
response luon bi block cho toi khi CR chay xong -> FE timeout 60s du CR van
chay ngam thanh cong (bang chung: session #196/tram 111035 DONE that trong DB
du FE bao loi timeout luc trigger). TriggerCrUseCase (C2.1) da duoc tach thanh
prepare_session() (buoc 1-2, dong bo) + run_cr_flow() (buoc 3-18, chay nen) -
xem application/trigger_cr_use_case.py. Router o day gio CHI await
prepare_session() (nhanh, thuan DB, cac loi tu choi request 409/404/422 van
tra ve dung luc request nhu cu) roi tra 202 NGAY, dung FastAPI BackgroundTasks
de chay run_cr_flow() O NEN.

C1.5-fix (20072026): DA SUA race condition SSE neu tren o ban dau (bao cao
luc [C1.4-fix], chua code ngay vi chua chac chan can thiet, nay da xac nhan
can va lam) - CrEventBus (infrastructure/event_bus.py) gio giu buffer
deque(maxlen=20)/session_id trong RAM, subscribe() moi (GET /cr/stream/
{session_id}, api/routers/sse.py) duoc replay lai toan bo buffer TRUOC khi
nhan event moi. FE mo EventSource cham hon luc run_cr_flow() da bat dau emit
(vi can them 1 vong round-trip network sau khi nhan 202) gio KHONG con mat
event dau nua. Xem infrastructure/event_bus.py cho chi tiet co che.
"""

from fastapi import APIRouter, BackgroundTasks, Depends

from api.schemas.cr_schemas import (
    AffectedCellItem,
    AffectedTramItem,
    CellNgoaiPhamViChiTiet,
    CrCellItem,
    OssSeDung,
    PreviewCrResponse,
    PreviewTramGoc,
    TriggerCrRequest,
    TriggerCrResponse,
)
from application.preview_cr_use_case import PreviewCrUseCase
from application.trigger_cr_use_case import TriggerCrUseCase
from infrastructure.dependencies import get_preview_cr_use_case, get_trigger_cr_use_case

router = APIRouter()


@router.post("/cr/trigger", response_model=TriggerCrResponse, status_code=202)
async def trigger_cr(
    body: TriggerCrRequest,
    background_tasks: BackgroundTasks,
    use_case: TriggerCrUseCase = Depends(get_trigger_cr_use_case),
) -> TriggerCrResponse:
    # Chi await prepare_session() (buoc 1-2: guard + tao session, thuan DB,
    # nhanh) - loi tu choi request (TramNotFoundError/CrAlreadyRunningError/
    # CrAlreadyDoneError/ValueError/NotImplementedError) van RAISE truc tiep
    # o day, duoc exception handler (api/middleware/error_handler.py) map
    # sang 409/404/422 dung nhu truoc, KHONG bi nuot vao background task.
    session = await use_case.prepare_session(
        tram_id=body.tram_id or "",
        tram_name=body.tram_name or "",
        action=body.action,
    )
    # run_cr_flow() (buoc 3-18, co SSH NetAct that o buoc 13-16) chay NEN qua
    # BackgroundTasks - KHONG await truc tiep, sua bug FE timeout 60s (xem
    # docstring dau file). FastAPI dam bao background task nay chi bat dau
    # SAU KHI response 202 duoi day da duoc tra ve client.
    background_tasks.add_task(use_case.run_cr_flow, session, body.tram_name or "", body.action)
    return TriggerCrResponse(
        session_id=session.id,
        status=session.status.value,
        message="CR da duoc khoi tao, theo doi qua SSE stream",
    )


@router.post("/cr/preview", response_model=PreviewCrResponse)
async def preview_cr(
    body: TriggerCrRequest,
    use_case: PreviewCrUseCase = Depends(get_preview_cr_use_case),
) -> PreviewCrResponse:
    # Chay dong bo, tra ve NGAY (KHONG BackgroundTasks nhu /cr/trigger) - preview
    # CHI goi CDS + tinh toan trong memory (buoc 3-10), KHONG SSH (buoc 13-16 la
    # phan cham/co the mat vai phut, preview khong dung toi) nen khong can tach
    # nen. Loi (TramNotFoundError/CdsApiError/CrNoNeighborCellError) RAISE truc
    # tiep, duoc middleware DomainError (api/middleware/error_handler.py) tu
    # map sang 404/502/422 - KHONG can try/except rieng o day, giong pattern
    # prepare_session() cua /cr/trigger o tren.
    result = await use_case.execute(
        tram_id=body.tram_id or "",
        tram_name=body.tram_name or "",
        action=body.action,
    )
    return PreviewCrResponse(
        tram_goc=PreviewTramGoc(
            tram_id=result.tram_goc.tram_id,
            tram_name=result.tram_goc.tram_name,
            longitude=result.tram_goc.longitude,
            latitude=result.tram_goc.latitude,
        ),
        cells_bi_anh_huong=[
            AffectedCellItem(
                cell_name=c.cell_name, huong_id=c.huong_id, tram_id=c.tram_id,
                pct_ho=c.pct_ho, so_ho=c.so_ho, sr=c.sr, layer=c.layer, co=c.co,
                sector=c.sector, sectors_khac=c.sectors_khac,
            )
            for c in result.cells_bi_anh_huong
        ],
        tram_bi_anh_huong=[
            AffectedTramItem(
                tram_id=t.tram_id, tram_name=t.tram_name, longitude=t.longitude, latitude=t.latitude
            )
            for t in result.tram_bi_anh_huong
        ],
        # 2 truong 07092026 - xem chu y trong api/schemas/cr_schemas.py
        so_cell_ngoai_pham_vi=len(result.cell_ngoai_pham_vi),
        cell_ngoai_pham_vi=result.cell_ngoai_pham_vi,
        # Ban chi tiet (V8, 09/2026) - THEM MOI, xem CellNgoaiPhamViChiTiet.
        cell_ngoai_pham_vi_chi_tiet=[
            CellNgoaiPhamViChiTiet(cell_name=d["cell_name"], ly_do=d["ly_do"], chi_tiet=d.get("chi_tiet"))
            for d in result.cell_ngoai_pham_vi_chi_tiet
        ],
        # OSS se dung (Giai doan 1 buoc 2, 09/2026) - CHI lo instance_id (host
        # bo 03/10/2026 - xem OssSeDung), TUYET DOI KHONG user/password.
        oss_se_dung=(
            OssSeDung(instance_id=result.oss_instance.instance_id)
            if result.oss_instance is not None
            else None
        ),
        cells_chay_cr=[
            CrCellItem(
                cell_name=c.cell_name,
                tram_id=c.tram_id,
                huong_id=c.huong_id,
                priority=c.priority,
                action_type=c.action_type,
                rsboost_cu=c.rsboost_cu,
                rsboost_moi=c.rsboost_moi,
                qrxlevmin_cu=c.qrxlevmin_cu,
                qrxlevmin_moi=c.qrxlevmin_moi,
                band=c.band,
                sector=c.sector,
                pct_ho=c.pct_ho, so_ho=c.so_ho, sr=c.sr, layer=c.layer,
            )
            for c in result.cells_chay_cr
        ],
        x_co=result.x_co,
        quan_he_day_du=result.quan_he_day_du,
        ban_do=result.ban_do,
        sectors_it_du_lieu=result.sectors_it_du_lieu,
    )
