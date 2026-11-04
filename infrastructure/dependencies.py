"""
DI wiring — map Port interface -> Adapter implementation cho FastAPI Depends().
Tu: ARCHITECTURE.md Section 7.1; TASK_LIST.md B8.1

Quyet dinh design (xac nhan voi user 12072026):
- Chi wire toi tang adapter/repo/domain-service — ITriggerCrUseCase/
  IEvaluateCrUseCase (Part C, chua code) CHUA co factory o day, vi chinh use
  case do chua ton tai. Se bo sung khi C2.1/C2.2 code.
- get_network_gateway() tra ve NetworkGatewayFacade (adapters/http/
  network_gateway_facade.py, moi tao o B8.1) — giai quyet GAP tu B6.2
  (INetworkGateway 1 ABC nhung 3 adapter rieng, khong adapter nao du 3 method).
- get_event_bus() tra thang singleton `event_bus` (infrastructure/event_bus.py)
  — KHONG dung Depends() tran voi CrEventBus lam type (KI-01, se tao instance
  moi moi request, sai voi thiet ke SSE pub/sub dung chung 1 bus).
- Domain service thuan (khong state, khong I/O) instantiate truc tiep khong
  can Depends() rieng — nhung van cung cap factory o day de dong nhat cach
  TriggerCrUseCase (C2.1) nhan dependency, tranh 2 kieu wiring khac nhau
  trong cung 1 layer.
"""

import logging
import os

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.http.cds_http_adapter import CdsHttpAdapter
from adapters.http.cem_http_adapter import CemHttpAdapter
from adapters.http.cts_http_adapter import CtsHttpAdapter
from adapters.http.enodeb_http_adapter import EnodebHttpAdapter
from adapters.http.network_gateway_facade import NetworkGatewayFacade
from adapters.http.save_cell_clm_adapter import SaveCellClmAdapter
from adapters.http.soc_http_adapter import SocHttpAdapter
from adapters.netact.netact_adapter import NetActAdapter
from adapters.netact.oss_router_env import OssRouterEnv
from adapters.netact.xml_builder import XmlBuilder
from adapters.postgres.alert_repo import AlertRepo
from adapters.postgres.cell_infor_repo import CellInforRepo
from adapters.postgres.cell_params_repo import CellParamsRepo
from adapters.postgres.cell_vi_tri_uoc_luong_repo import CellViTriUocLuongRepo
from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_log_repo import CrLogRepo
from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.dashboard_repo import DashboardRepo
from adapters.postgres.enodeb_repo import EnodebRepo
from adapters.postgres.ho_neighbor_repo import HoNeighborRepo
from adapters.postgres.job_run_log_repo import JobRunLogRepo
from adapters.postgres.qoe_snapshot_repo import QoeSnapshotRepo
from adapters.postgres.qos_snapshot_repo import QosSnapshotRepo
from domain.ports.inbound.use_case_ports import (
    IGetQoeSparklineUseCase,
    IGetQosSparklineUseCase,
    IGetSessionDetailUseCase,
    IGetSessionsUseCase,
    ISyncCellParamsUseCase,
    ISyncEnodebUseCase,
    IXuatPhieuUseCase,
)
from domain.ports.outbound.gateway_ports import (
    INetActGateway,
    INetworkGateway,
    IOssRouter,
    ISaveCellClmGateway,
    ISocGateway,
)
from domain.ports.outbound.repo_ports import (
    IAlertRepo,
    ICellInforRepo,
    ICellParamsRepo,
    ICellViTriUocLuongRepo,
    ICrAffectedCellsRepo,
    ICrLogRepo,
    ICrPhieuRepo,
    ICrSessionRepo,
    IEnodebRepo,
    IHoNeighborRepo,
    IJobRunLogRepo,
    IQoeSnapshotRepo,
    IQosSnapshotRepo,
)
from domain.services.evaluation_service import EvaluationService
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.services.rsboost_calculator import RsboostCalculator
from infrastructure.db import get_asyncpg_connection, get_session
from infrastructure.event_bus import CrEventBus, event_bus
from application.alert_use_case import AlertUseCase
from application.dashboard_use_case import DashboardUseCase
from application.xuat_excel_hau_kiem_use_case import XuatExcelHauKiemUseCase
from application.evaluate_cr_use_case import EvaluateCrUseCase
from application.get_qoe_cells_use_case import GetQoeCellsUseCase
from application.get_stations_map_use_case import GetStationsMapUseCase
from application.get_qos_cells_use_case import GetQosCellsUseCase
from application.get_qoe_sparkline_use_case import GetQoeSparklineUseCase
from application.xoa_phieu_use_case import XoaPhieuUseCase
from application.xoa_session_use_case import XoaSessionUseCase
from application.get_qos_sparkline_use_case import GetQosSparklineUseCase
from application.get_session_detail_use_case import GetSessionDetailUseCase
from application.get_sessions_use_case import GetSessionsUseCase
from application.preview_cr_use_case import PreviewCrUseCase
from application.sync_cell_params_use_case import SyncCellParamsUseCase
from application.sync_enodeb_use_case import SyncEnodebUseCase
from application.trigger_cr_use_case import TriggerCrUseCase
from application.xuat_phieu_use_case import XuatPhieuUseCase

logger = logging.getLogger(__name__)


# === HTTP adapters (INetworkGateway qua facade) ===
def get_cds_adapter() -> CdsHttpAdapter:
    return CdsHttpAdapter()


def get_cts_adapter() -> CtsHttpAdapter:
    return CtsHttpAdapter()


def get_enodeb_http_adapter() -> EnodebHttpAdapter:
    return EnodebHttpAdapter()


def get_network_gateway(
    cds_adapter: CdsHttpAdapter = Depends(get_cds_adapter),
    cts_adapter: CtsHttpAdapter = Depends(get_cts_adapter),
    enodeb_adapter: EnodebHttpAdapter = Depends(get_enodeb_http_adapter),
) -> INetworkGateway:
    return NetworkGatewayFacade(cds_adapter, cts_adapter, enodeb_adapter)


def get_soc_gateway() -> ISocGateway:
    """Nguon QoE: CEM that (CEM_ENABLED=true) hoac mock cu (mac dinh).

    CONG TAT 1 DONG (16082026): SocHttpAdapter tra qoe=3.5 CUNG (OQ-01) van
    duoc GIU LAI nguyen ven - neu CEM co van de (doi credential, doi format,
    server chet) thi dat CEM_ENABLED=false la quay ve trang thai cu ngay, khong
    can revert code.

    CAN THAN KHI BAT: QoE that se THAM GIA danh gia cap session
    (EvaluateCrUseCase) - qoe_result cua session CO THE doi tu PASS sang FAIL
    hoac nguoc lai, vi truoc do moi so lieu deu la 3.5 nen qoe_before == qoe_after
    == 3.5 va LUON PASS. Xem .env.example muc CEM API.
    """
    # VI SAO PHAI LOG O DAY (them 16082026): truoc do KHONG co cach nao biet
    # dang chay adapter nao ngoai viec SUY RA TU SU VANG MAT cua dong
    # "SocHttpAdapter dung MOCK data" trong log - qua mong manh cho mot cong tac
    # co the doi ket qua danh gia that. Nguoi truc phai doc duoc TRUC TIEP.
    #
    # Nhanh CEM dung WARNING (khong phai INFO) CO CHU DINH: day la trang thai
    # "QoE that dang tham gia danh gia", phai noi bat trong log de khong ai bat
    # nham roi de chay nhieu ngay ma khong biet.
    if os.getenv("CEM_ENABLED", "false").strip().lower() == "true":
        logger.warning("QoE: dung CemHttpAdapter (API CEM THAT) - CEM_ENABLED=true")
        return CemHttpAdapter()
    logger.info("QoE: dung SocHttpAdapter (MOCK qoe=3.5) - CEM_ENABLED=false")
    return SocHttpAdapter()


# === NetAct adapter (INetActGateway) ===
def get_netact_gateway() -> INetActGateway:
    return NetActAdapter()


# === OSS router (IOssRouter, Giai doan 1 buoc 2 - 27/09/2026) ===
def get_oss_router() -> IOssRouter:
    # Doc NETACT_SERVERS TU DAY (KHONG con doc trong NetActAdapter) - tach
    # rieng viec CHON OSS (theo tung cell) khoi viec THUC THI SSH, xem
    # adapters/netact/oss_router_env.py.
    return OssRouterEnv()


# === PostgreSQL repos ===
def get_enodeb_repo(session: AsyncSession = Depends(get_session)) -> IEnodebRepo:
    return EnodebRepo(session)


# === GetStationsMapUseCase (BUOC 4c, 10/10/2026, GET /stations/map) ===
def get_stations_map_use_case(
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
) -> GetStationsMapUseCase:
    return GetStationsMapUseCase(enodeb_repo=enodeb_repo)


def get_cr_session_repo(session: AsyncSession = Depends(get_session)) -> ICrSessionRepo:
    return CrSessionRepo(session)


def get_cell_params_repo(session: AsyncSession = Depends(get_session)) -> ICellParamsRepo:
    return CellParamsRepo(session)


def get_cell_infor_repo(conn=Depends(get_asyncpg_connection)) -> ICellInforRepo:
    # CellInforRepo dung raw asyncpg (.fetch()), KHAC cac repo khac o tren
    # (SQLAlchemy AsyncSession) - da quyet dinh vay ngay 12/07/2026, xem chu y
    # trong infrastructure/db.py::get_asyncpg_connection().
    return CellInforRepo(conn)


def get_ho_neighbor_repo(session: AsyncSession = Depends(get_session)) -> IHoNeighborRepo:
    # BUOC 4b (08/10/2026, yeu cau truc tiep user) - thay CDS bang HO trong
    # xem truoc/chay CR. Xem domain/ports/outbound/repo_ports.py::IHoNeighborRepo.
    return HoNeighborRepo(session)


def get_cell_vi_tri_uoc_luong_repo(session: AsyncSession = Depends(get_session)) -> ICellViTriUocLuongRepo:
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - xem domain/ports/outbound/
    # repo_ports.py::ICellViTriUocLuongRepo.
    return CellViTriUocLuongRepo(session)


def get_alert_repo(session: AsyncSession = Depends(get_session)) -> IAlertRepo:
    return AlertRepo(session)


def get_qoe_snapshot_repo(session: AsyncSession = Depends(get_session)) -> IQoeSnapshotRepo:
    return QoeSnapshotRepo(session)


def get_qos_snapshot_repo(session: AsyncSession = Depends(get_session)) -> IQosSnapshotRepo:
    return QosSnapshotRepo(session)


def get_cr_affected_cells_repo(session: AsyncSession = Depends(get_session)) -> ICrAffectedCellsRepo:
    # Phuong an B (22072026, DA DUYET) - xem domain/ports/outbound/repo_ports.py::ICrAffectedCellsRepo.
    return CrAffectedCellsRepo(session)


def get_cr_log_repo(session: AsyncSession = Depends(get_session)) -> ICrLogRepo:
    # 22072026 (xac nhan voi user) - xem domain/ports/outbound/repo_ports.py::ICrLogRepo.
    return CrLogRepo(session)


def get_job_run_log_repo(session: AsyncSession = Depends(get_session)) -> IJobRunLogRepo:
    # JOB TU DONG buoc 1/4 (11/08, yeu cau truc tiep user) - xem
    # domain/ports/outbound/repo_ports.py::IJobRunLogRepo. CHUA co use case/
    # scheduler nao Depends() toi factory nay - se wire o buoc 3/4 (use case
    # xuat phieu tu dong), giong cach get_cr_phieu_repo() da cho o KHOI 2/5.
    return JobRunLogRepo(session)


def get_cr_phieu_repo(session: AsyncSession = Depends(get_session)) -> ICrPhieuRepo:
    # KHOI 2/5 SaveCellClm (yeu cau truc tiep user) - xem
    # domain/ports/outbound/repo_ports.py::ICrPhieuRepo. CHUA co use case nao
    # Depends() toi factory nay - de wire o KHOI 3/5.
    return CrPhieuRepo(session)


# === Event bus (KI-01 — PHAI tra singleton, khong Depends() tran) ===
def get_event_bus() -> CrEventBus:
    return event_bus


# === Domain services thuan (khong state/I-O) ===
def get_rsboost_calculator() -> RsboostCalculator:
    return RsboostCalculator()


def get_qrxlevmin_calculator() -> QrxlevminCalculator:
    return QrxlevminCalculator()


def get_xml_builder() -> XmlBuilder:
    return XmlBuilder()


# === TriggerCrUseCase (C1.4, 13072026 - bo sung factory con thieu tu B8.1) ===
def get_trigger_cr_use_case(
    network_gw: INetworkGateway = Depends(get_network_gateway),
    netact_gw: INetActGateway = Depends(get_netact_gateway),
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    cell_repo: ICellParamsRepo = Depends(get_cell_params_repo),
    cell_infor_repo: ICellInforRepo = Depends(get_cell_infor_repo),
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
    bus: CrEventBus = Depends(get_event_bus),
    rsboost_calc: RsboostCalculator = Depends(get_rsboost_calculator),
    qrxlevmin_calc: QrxlevminCalculator = Depends(get_qrxlevmin_calculator),
    xml_builder: XmlBuilder = Depends(get_xml_builder),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    cr_log_repo: ICrLogRepo = Depends(get_cr_log_repo),
    oss_router: IOssRouter = Depends(get_oss_router),
    ho_neighbor_repo: IHoNeighborRepo = Depends(get_ho_neighbor_repo),
    cell_vi_tri_uoc_luong_repo: ICellViTriUocLuongRepo = Depends(get_cell_vi_tri_uoc_luong_repo),
) -> TriggerCrUseCase:
    # C1.4-fix (20072026): tra ve TriggerCrUseCase CU THE (khong phai
    # ITriggerCrUseCase) - cung pattern get_evaluate_cr_use_case() o duoi,
    # vi router (api/routers/cr.py) can goi rieng prepare_session()/
    # run_cr_flow() (method CU THE, KHONG nam trong ABC chi co execute()).
    #
    # BO CDS (18/10/2026, quyet dinh user) - bo cong tac .env NEIGHBOR_SOURCE:
    # HO + Delaunay la nguon DUY NHAT (TriggerCrUseCase khong con nhanh CDS).
    return TriggerCrUseCase(
        network_gw=network_gw,
        netact_gw=netact_gw,
        session_repo=session_repo,
        cell_repo=cell_repo,
        cell_infor_repo=cell_infor_repo,
        enodeb_repo=enodeb_repo,
        event_bus=bus,
        rsboost_calc=rsboost_calc,
        qrxlevmin_calc=qrxlevmin_calc,
        xml_builder=xml_builder,
        affected_cells_repo=affected_cells_repo,
        cr_log_repo=cr_log_repo,
        oss_router=oss_router,
        ho_neighbor_repo=ho_neighbor_repo,
        cell_vi_tri_uoc_luong_repo=cell_vi_tri_uoc_luong_repo,
    )


# === PreviewCrUseCase (API preview /cr/preview, 21072026) ===
def get_preview_cr_use_case(
    trigger_use_case: TriggerCrUseCase = Depends(get_trigger_cr_use_case),
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
) -> PreviewCrUseCase:
    # Compose TriggerCrUseCase da wire san (KHONG tu tao lai tung dependency
    # rieng) - PreviewCrUseCase goi lai _resolve_tram_id()/_prepare_plan() cua
    # no, xem application/preview_cr_use_case.py.
    return PreviewCrUseCase(trigger_use_case=trigger_use_case, enodeb_repo=enodeb_repo)


# === GetSessionsUseCase / GetSessionDetailUseCase (C1.6, Nhom 2 13072026) ===
def get_sessions_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    # 2 repo THEM 04/10/2026 (so_cell_ngoai_dieu_kien_moi, CHI DOC) - tai dung
    # 2 factory CO SAN (da wire cho get_session_detail_use_case ben duoi),
    # KHONG tao factory moi.
    cell_params_repo: ICellParamsRepo = Depends(get_cell_params_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
) -> IGetSessionsUseCase:
    return GetSessionsUseCase(session_repo, cell_params_repo, affected_cells_repo)


def get_session_detail_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    cell_repo: ICellParamsRepo = Depends(get_cell_params_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    cr_log_repo: ICrLogRepo = Depends(get_cr_log_repo),
) -> IGetSessionDetailUseCase:
    return GetSessionDetailUseCase(session_repo, cell_repo, affected_cells_repo, cr_log_repo)


# === AlertUseCase (C2.7, Nhom 2 13072026) — collaborator noi bo cua EvaluateCrUseCase ===
def get_alert_use_case(
    alert_repo: IAlertRepo = Depends(get_alert_repo),
) -> AlertUseCase:
    return AlertUseCase(alert_repo)


# === EvaluateCrUseCase (C1.8/jobs.py, Nhom 2 13072026) ===
def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


def get_evaluate_cr_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    cell_repo: ICellParamsRepo = Depends(get_cell_params_repo),
    network_gw: INetworkGateway = Depends(get_network_gateway),
    soc_gw: ISocGateway = Depends(get_soc_gateway),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    alert_use_case: AlertUseCase = Depends(get_alert_use_case),
    qoe_snapshot_repo: IQoeSnapshotRepo = Depends(get_qoe_snapshot_repo),
    qos_snapshot_repo: IQosSnapshotRepo = Depends(get_qos_snapshot_repo),
) -> EvaluateCrUseCase:
    # Tra ve concrete EvaluateCrUseCase (khong phai IEvaluateCrUseCase) - jobs.py
    # can goi execute_all_pending(), method CU THE khong nam trong ABC (xem chu y
    # trong application/evaluate_cr_use_case.py).
    return EvaluateCrUseCase(
        session_repo,
        cell_repo,
        network_gw,
        soc_gw,
        evaluation_service,
        alert_use_case,
        qoe_snapshot_repo,
        qos_snapshot_repo,
    )


# === GetQosSparklineUseCase (C1.7, Nhom 2 13072026) ===
def get_qos_sparkline_use_case(
    network_gw: INetworkGateway = Depends(get_network_gateway),
) -> IGetQosSparklineUseCase:
    return GetQosSparklineUseCase(network_gw)


# === QoE per-cell (16082026) - doc lap voi qoe_result cap session ===
def get_qoe_sparkline_use_case(
    soc_gw: ISocGateway = Depends(get_soc_gateway),
) -> IGetQoeSparklineUseCase:
    return GetQoeSparklineUseCase(soc_gw)


def get_qoe_cells_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    soc_gw: ISocGateway = Depends(get_soc_gateway),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    # LAZY CACHE (20082026) - doc snapshot truoc, du 7+7 ngay thi khong goi CEM.
    qoe_snapshot_repo: IQoeSnapshotRepo = Depends(get_qoe_snapshot_repo),
) -> GetQoeCellsUseCase:
    # get_soc_gateway() -> tu dong theo cong tac CEM_ENABLED. Voi CEM_ENABLED=
    # false, endpoint nay tra QoE mock 3.5 cho moi cell (moi cell deu PASS) -
    # dung nhu moi duong QoE khac, khong tao ngoai le rieng.
    return GetQoeCellsUseCase(
        session_repo, affected_cells_repo, soc_gw, evaluation_service, qoe_snapshot_repo
    )


def get_qos_cells_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    qos_sparkline_use_case: IGetQosSparklineUseCase = Depends(get_qos_sparkline_use_case),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    # Lazy cache (04092026) - cell co du 7+7 ngay trong qos_snapshot thi doc DB,
    # tiet kiem 2 request CTS cho MOI cell do.
    qos_snapshot_repo: IQosSnapshotRepo = Depends(get_qos_snapshot_repo),
) -> GetQosCellsUseCase:
    return GetQosCellsUseCase(
        session_repo,
        affected_cells_repo,
        qos_sparkline_use_case,
        evaluation_service,
        qos_snapshot_repo,
    )


# === XOA (20082026, yeu cau truc tiep user) ===
def get_xoa_session_use_case(
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
) -> XoaSessionUseCase:
    # CHI can 1 repo: ca cascade nam trong CrSessionRepo.xoa_cascade() de giu
    # 1 transaction (xem chu y trong adapter).
    return XoaSessionUseCase(session_repo)


def get_xoa_phieu_use_case(
    cr_phieu_repo: ICrPhieuRepo = Depends(get_cr_phieu_repo),
) -> XoaPhieuUseCase:
    return XoaPhieuUseCase(cr_phieu_repo)


# === SaveCellClmAdapter (KHOI 1/5 SaveCellClm) ===
def get_save_cell_clm_gateway() -> ISaveCellClmGateway:
    return SaveCellClmAdapter()


# === XuatPhieuUseCase (KHOI 3a/5 SaveCellClm, yeu cau truc tiep user) - CHUA
# co router nao Depends() toi factory nay (KHOI 4/5 se wire endpoint). ===
def get_xuat_phieu_use_case(
    cr_phieu_repo: ICrPhieuRepo = Depends(get_cr_phieu_repo),
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
    qos_sparkline_use_case: IGetQosSparklineUseCase = Depends(get_qos_sparkline_use_case),
    save_cell_clm_gateway: ISaveCellClmGateway = Depends(get_save_cell_clm_gateway),
    # them (doi tieu chi QoS dat/khong dat) - tai dung LAI factory
    # get_evaluation_service() da co (dung chung voi EvaluateCrUseCase),
    # KHONG tao instance rieng.
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    # JOB TU DONG buoc 2/4 - chi execute_all_pending() dung (ghi ket qua luot
    # chay). Router POST /phieu khong cham toi, nhung wire san o day de scheduler
    # (buoc 3/4) tai dung DUNG factory nay, khong phai tu lap 1 ban khac.
    job_run_log_repo: IJobRunLogRepo = Depends(get_job_run_log_repo),
    # QoE ngang hang QoS (17082026) - job danh gia CA HAI chi so. Router
    # POST /phieu khong dung (execute() khong truyen qoe) nhung wire san de
    # scheduler tai dung DUNG factory nay.
    qoe_cells_use_case: GetQoeCellsUseCase = Depends(get_qoe_cells_use_case),
    # SNAPSHOT PER-CELL (20082026) - job da goi du CTS nen luu tai do ton 0
    # request phu (xem XuatPhieuUseCase._luu_snapshot_qos).
    qos_snapshot_repo: IQosSnapshotRepo = Depends(get_qos_snapshot_repo),
) -> XuatPhieuUseCase:
    # Tra ve concrete XuatPhieuUseCase (KHONG phai IXuatPhieuUseCase) - cung
    # pattern get_evaluate_cr_use_case(): caller (scheduler buoc 3/4) can goi
    # execute_all_pending(), method CU THE khong nam trong ABC (ABC chi co
    # execute() cho 1 cell). Router POST /phieu van chay nguyen ven vi
    # XuatPhieuUseCase van implement IXuatPhieuUseCase.
    return XuatPhieuUseCase(
        cr_phieu_repo=cr_phieu_repo,
        cr_session_repo=session_repo,
        cr_affected_cells_repo=affected_cells_repo,
        enodeb_repo=enodeb_repo,
        qos_sparkline_use_case=qos_sparkline_use_case,
        save_cell_clm_gateway=save_cell_clm_gateway,
        evaluation_service=evaluation_service,
        job_run_log_repo=job_run_log_repo,
        # QoE ngang hang QoS (17082026) - job danh gia CA HAI chi so.
        qoe_cells_use_case=qoe_cells_use_case,
        qos_snapshot_repo=qos_snapshot_repo,
    )


# === SyncEnodebUseCase / SyncCellParamsUseCase (C2.5/C2.6, Nhom 3 13072026) ===
def get_sync_enodeb_use_case(
    network_gw: INetworkGateway = Depends(get_network_gateway),
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
) -> ISyncEnodebUseCase:
    return SyncEnodebUseCase(network_gw, enodeb_repo)


def get_sync_cell_params_use_case(
    cell_infor_repo: ICellInforRepo = Depends(get_cell_infor_repo),
) -> ISyncCellParamsUseCase:
    return SyncCellParamsUseCase(cell_infor_repo)


def get_dashboard_use_case(session: AsyncSession = Depends(get_session)) -> DashboardUseCase:
    # GET /dashboard/tong-quan (18/10/2026) - chi 1 repo doc, khong gateway
    # ngoai: dashboard tinh tu DB, khong goi CTS/CEM.
    return DashboardUseCase(DashboardRepo(session))


def get_xuat_excel_hau_kiem_use_case(
    session: AsyncSession = Depends(get_session),
    session_repo: ICrSessionRepo = Depends(get_cr_session_repo),
    affected_cells_repo: ICrAffectedCellsRepo = Depends(get_cr_affected_cells_repo),
    cell_params_repo: ICellParamsRepo = Depends(get_cell_params_repo),
    cr_phieu_repo: ICrPhieuRepo = Depends(get_cr_phieu_repo),
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
    # Tai dung DUNG 2 use case cua bang hau kiem tren UI - Excel ra cung ket
    # luan, cung nguon so lieu (snapshot) voi man hinh.
    qos_cells_use_case: GetQosCellsUseCase = Depends(get_qos_cells_use_case),
    qoe_cells_use_case: GetQoeCellsUseCase = Depends(get_qoe_cells_use_case),
) -> XuatExcelHauKiemUseCase:
    return XuatExcelHauKiemUseCase(
        session_repo, DashboardRepo(session), affected_cells_repo, cell_params_repo,
        cr_phieu_repo, enodeb_repo, qos_cells_use_case, qoe_cells_use_case,
    )
