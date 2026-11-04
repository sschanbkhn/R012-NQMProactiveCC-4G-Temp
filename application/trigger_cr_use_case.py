"""
TriggerCrUseCase — flow chinh 18 buoc, emit SSE event sau moi step.
Tu: ARCHITECTURE.md Section 4.1; WORKFLOW.md (18 buoc + SS6 SSE format + SS7 pct
mapping + SS8 error handling); BUSINESS_RULES.md Section 1; TASK_LIST.md C2.1

PHAM VI: chi flow chinh (action="shutdown"|"relocate", 18 buoc). action="cancel"
la Rollback Flow rieng (WORKFLOW.md SS3) - KHONG code o day, raise
NotImplementedError (xac nhan voi user 12072026).

Quyet dinh design quan trong (xac nhan voi user 12072026, xem log/DEV_LOG.md
muc C2.1 cho day du qua trinh phan tich):

1. Constructor them enodeb_repo: IEnodebRepo (KHONG co trong ARCHITECTURE.md
   SS4.1 pseudocode goc) - can cho ca 2 viec: resolve tram_id tu tram_name
   (buoc 1c) VA get_ma_tinh() cho NetAct multi-vung (buoc 13). KHONG co
   audit_svc (AuditService chua ton tai trong code - bo qua o C2.1 nay, TODO
   rieng sau).

2. Loi TRUOC khi tao cr_session (guard buoc 1c/1d: TramNotFoundError/
   CrAlreadyRunningError/CrAlreadyDoneError) - RAISE truc tiep, KHONG catch.
   Chua co session_id de emit SSE, va day la loi tu choi request dong bo (se
   duoc router C1.4 map sang HTTP 409/404 qua exception handler C1.2, ca 2
   chua code).

3. Loi SAU KHI cr_session da tao (buoc 3-18, chay trong run_cr_flow()) - CATCH,
   set session.status=FAILED, cr_session_repo.update(), emit SSE failed, ROI
   RETURN session (KHONG raise lai) - khop voi execute() -> CrSession (khong
   Optional) cua ITriggerCrUseCase (B2.9), va ban chat "fire-and-forget
   background task" (HTTP response da tra ve tu buoc 1-2, khong con ai bat
   exception luc nay).
   SUA LAI (C1.4-fix bo sung, 20072026, sau khi phat hien bug that session
   #197/tram 111138 ket RUNNING 4 ngay): TRUOC DAY chi catch DomainError -
   ly do luc do la "loi thuc su ngoai du kien (bug) van crash tu nhien,
   khong bi nuot am tham thanh FAILED nghiep vu", NHUNG gia dinh nay SAI khi
   run_cr_flow() chuyen sang chay qua FastAPI BackgroundTasks (khong con ai
   o router await/bat exception nua) - 1 exception "crash tu nhien" trong
   background task KHONG lam sup app, chi bi Starlette log roi nuot lang le,
   con session thi KET VINH VIEN o RUNNING (khong ai set FAILED). Gio CATCH
   CA Exception chung (ngoai DomainError) - moi loai loi deu PHAI dan session
   ve FAILED, khong con truong hop nao "crash tu nhien" nua trong ngu canh
   background task. Xem run_cr_flow() cuoi ham cho chi tiet 2 nhanh except.

4. cr_log (bang JSONB detail tung buoc) CHUA co port/repo nao (giong
   AuditService) - BO QUA viec ghi DB o day, TODO rieng. Thong tin chi tiet
   van co trong SSE event (field "detail"/"error") o thoi gian thuc, chi
   khong persist.

5. Buoc 13-16 (SSH: upload+Import+Provision+verify) GOP thanh 1 khoi SSE duy
   nhat (submit_cr() B7.3 la 1 call dong bo, khong co hook bao tien do giua
   chung) - emit "running" truoc khi goi, "success"/"failed" sau khi co ket
   qua, pct nhay thang 70% -> 90%.

6. Timestamp cho plan_name/backup_name/xml_filename/executed_at: dung UTC
   (BUSINESS_RULES.md SS7.2 "Timestamp: UTC") - KHAC voi <log dateTime> ben
   trong XML (GMT+7, da xac nhan bang file that o B7.1) vi 2 gia tri nay khac
   nhau hoan toan, KHONG co bang chung file that nao noi plan_name/timestamp
   filename can GMT+7 (template that dung ten thu cong "check_rsboost_cbg_...",
   khong theo pattern R012_NQMProactiveCC_{tram_id}_{ts}).

7. Buoc 7/9 (SUA LAI LAN 2, 12072026 — thay the quyet dinh cu o
   duoi): KHONG con doc rsboost_current/qrxlevmin_current tu cell_params
   (ICellParamsRepo.get_by_cell_names(), da tung sua o lan dau vi bug tram_id)
   — chuyen hoan toan sang doc tu bang MOI cell_infor (du lieu tho tu Admin
   CLI export, xem adapters/netact/import_4G_cell_infor.py) qua
   ICellInforRepo.get_rsboost_by_neighbor_dns()/get_qrxlevmin_by_neighbor_dns(),
   query theo Cell.dist_name (KHONG phai cell_name) — match bang LIKE tren
   dn_fdd/dn_sib cua cell_infor (repo tu quyet dinh, TriggerCrUseCase chi
   truyen dist_name). Cell KHONG co du lieu trong cell_infor (chua tung sync)
   -> LOAI HOAN TOAN khoi CR (khong tinh rsboost_new/qrxlevmin_new, khong dua
   vao XML) — xac nhan voi user 12072026, KHAC quyet dinh default 0dB/-128 da
   dung khi con doc cell_params (WORKFLOW.md dong 130/157 gio KHONG con ap
   dung cho nhanh nay nua, chi con lien quan lich su).
   cell_params VAN ghi binh thuong o buoc 11 (upsert) + snapshot_before_cr()
   o buoc 7 KHONG doi — chi phan DOC current_rsboost/current_qrxlevmin la
   chuyen nguon, phan GHI cell_params + XmlBuilder giu nguyen (xac nhan voi
   user). RsboostCalculator/QrxlevminCalculator (domain/services/) cung da
   sua song song: BO tham so tram_id dau vao, tu parse tram_id tu
   cell.dist_name (regex MRBTS-(\\d+)) — nhan tien giai quyet dut diem bug cu
   (calculator truoc day dung chung 1 tram_id cua CR cho MOI CellParam ket
   qua, sai voi cell lan gieng thuoc nhieu tram vat ly khac nhau, da phat
   hien + bao cao 12072026 truoc do trong session nay).

8. cell_id cho XmlCellData (buoc 12): dung Cell.dist_name (KHONG dung
   Cell.cell_id) - ARCHITECTURE.md dong 77 danh dau ro dist_name la field
   chua format "PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y" dung cho distName XML;
   Cell.cell_id (dong 75) chi de check null (SS2.2 rule 2). Hien tai 2 field
   trung gia tri (neighbor_cell_service.py, B3.2) nhung dist_name moi la field
   dung dung thiet ke.

9. Resolve tram_name tu tram_id (buoc 1c, khi thieu tram_id): dung
   enodeb_repo.find(tram_name) + loc EXACT match (tram_name.lower() ==
   query.lower()) - KHONG lay ket qua ILIKE dau tien mu quang (rui ro nham
   tram, tram_name KHONG co UNIQUE constraint trong DB). 0 ket qua hoac >1 ket
   qua deu raise TramNotFoundError (tai su dung, khong co error class nao
   khop nghia "nhieu tram trung ten" - xac nhan voi user).

10. Buoc 5: NbLncelFilter (moi, domain/services/nb_lncel_filter.py) chay NGAY
    SAU BandPriorityFilter, GOP CHUNG 1 buoc SSE (khong tao buoc rieng, khong
    renumber buoc 6-18) - xac nhan voi user 12072026. Loai cell_name prefix
    "NB-"/"MBF_" VA/HOAC LNCEL local id bat dau bang "2" - phat sinh tu quan
    sat du lieu that qua scripts/test_neighbor_filter.py, CHUA co trong
    BUSINESS_RULES.md goc (da cap nhat rieng WORKFLOW.md Step 5 mo ta cac
    dieu kien nay, BUSINESS_RULES.md CHUA cap nhat - can theo doi).

11. Buoc 5 (tiep): HuongCellSelector (moi, domain/services/
    huong_cell_selector.py) chay NGAY SAU NbLncelFilter, VAN GOP CHUNG buoc 5
    (khong buoc SSE rieng) - xac nhan voi user 12072026. Chon toi da
    MAX_CELLS_PER_HUONG cell/huong_id, uu tien priority tang dan, dedup xuyen
    huong theo thu tu huong_id tang dan.
    CAP NHAT 09/2026 (quyet dinh van hanh, user chot): tran nay la **2**
    cell/huong = 1 rsboost (rank 1) + 1 qrxlevmin (rank 2). Con so va y nghia
    nghiep vu deu da ro, KHONG con la "minh thi khong nguon" nhu ghi chu cu.
    Nguon: quyet dinh van hanh 09/2026; hang so tai
    domain/services/neighbor_cell_filter.py::MAX_CELLS_PER_HUONG, map rank tai
    domain/services/priority_assigner.py::RSBOOST_RANKS/QRXLEVMIN_RANKS.
    (Truoc do la 4 = 2 rsboost + 2 qrxlevmin, va con so 4 thi that su KHONG co
    trong BUSINESS_RULES.md/WORKFLOW.md goc - BUSINESS_RULES.md SS4.2 noi ve
    so luong BIEN DOI, khong phai gioi han chon.)

12. BUOC 4b (08/10/2026, yeu cau truc tiep user) - THAY CDS bang HO trong xem
    truoc/chay CR. SUA 18/10/2026 (quyet dinh user - BO CDS): cong tac
    NEIGHBOR_SOURCE va nhanh CDS (_lay_du_lieu_goc_cds/NeighborCellFilter/
    PriorityAssigner) DA BO - HO + Delaunay la nguon DUY NHAT. Session cu
    (truoc 12/10, cell lay qua CDS) GIU NGUYEN cr_affected_cells/cell_params,
    KHONG tinh lai. Doan duoi day la lich su thiet ke 2 nhanh. KHONG tu dong roi ve CDS khi nhanh HO
    loi (yeu cau truc tiep user) - loi HO (netact khong xac dinh duoc/khong
    co du lieu/thieu mau) deu raise HoNoDataError (422) ro rang, KHONG catch
    roi fallback sang goi CDS.

    `_prepare_plan()` tach thanh 2 nhanh LAY DU LIEU GOC rieng (CDS: raw_huongs
    tu INetworkGateway + NeighborCellFilter; HO: ho_neighbor + domain
    phan_loai_toa_do/phan_lop_delaunay/chon_cell_cr) roi GOP LAI CHAY CHUNG 1
    duong tinh cho PHAN SAU - dinh tuyen OSS theo tung cell
    (_chon_oss_va_loc_cells(), DUNG CHUNG), PriorityAssigner (CHI goi cho CDS -
    nhanh HO da tu gan action_type qua CellUngVien.rank_b trong
    domain.chon_cell_cr(), goi lai se ghi de SAI), roi lay rsboost/qrxlevmin_
    current (ICellInforRepo) + tinh gia tri moi (RsboostCalculator/
    QrxlevminCalculator) - 2 buoc nay THUAN TUY doc Cell.action_type/dist_name/
    cell_name (KHONG quan tam nguon goc), nen dung lai NGUYEN VEN cho ca 2
    nhanh - DUNG yeu cau "1 duong tinh, khong viet 2 ban" tu diem nay tro di.

    Nhanh HO quy doi CellUngVien (domain/services/ho_cell_selector.py) sang
    Cell entity (dist_name = dn_lncel tra tu ICellInforRepo.get_dn_map_theo_enb_lcr(),
    action_type = rank_b hoac "" cho Nhanh A, band = band_tu_lncel(LNCEL cua
    chinh cell)) - CellUngVien.can_ghep_ten=True (KHONG resolve duoc ten/DN
    qua cell_infor) KHONG tao duoc Cell hop le (thieu dist_name) nen bi LOAI
    khoi ca affected_cells VA cells (xem _cell_ung_vien_to_cell()) - PHAN ANH
    dung yeu cau "A chi cell Nokia co ten -> cr_affected_cells". Thong tin PHU
    (% HO/so HO/SR/layer/co moi cell, co cua X, quan he day du, nguon du lieu -
    CA cell CAN_GHEP_TEN khong ghep duoc Cell) duoc tra RIENG qua
    PlanResult.ho_extra (dict, chi PreviewCrUseCase doc - run_cr_flow() khong
    dung, giu field "n_*"/"cells"/"affected_cells" hien co KHONG doi nghia).

TODO: KHONG resolve chieu nguoc lai (tram_name tu tram_id khi chi co tram_id)
- WORKFLOW.md/BUSINESS_RULES.md SS1 chi mo ta chieu tram_name->tram_id. Neu
  caller chi truyen tram_id (tram_name rong), buoc 3 (CdsHttpAdapter) se nhan
  tram_name="" trong request body CDS - CHUA ro CDS API xu ly the nao (khong
  co bang chung/tai lieu). Rui ro chap nhan duoc thuc te se hiem gap (FE luon
  co ca 2 tu station search grid, UI_DESIGN.md Zone A) - can theo doi khi test
  that (Part D/E).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from adapters.netact.xml_builder import XmlBuilder
from domain.entities.cell import Cell
from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrSession, CrStatus
from domain.entities.xml_cell_data import XmlCellData
from domain.errors import (
    CauHinhNetactLoiError,
    CrAlreadyDoneError,
    CrAlreadyRunningError,
    CrNhieuOssError,
    DomainError,
    HoNoDataError,
    SshConnectionError,
    TramNotFoundError,
)
from domain.ports.inbound.use_case_ports import ITriggerCrUseCase
from domain.ports.outbound.gateway_ports import INetActGateway, INetworkGateway, IOssRouter
from domain.ports.outbound.repo_ports import (
    ICellInforRepo,
    ICellParamsRepo,
    ICellViTriUocLuongRepo,
    ICrAffectedCellsRepo,
    ICrLogRepo,
    ICrSessionRepo,
    IEnodebRepo,
    IHoNeighborRepo,
)
from domain.services.dist_name import co_dang_dn_nokia, extract_lnbts
from domain.services.geo_utils import duong_bao_hinh_sao, sap_theo_goc
from domain.services.ho_cell_selector import (
    CellUngVien,
    KhongCoDuLieuHoError,
    ThongTinTramDich,
    chon_cell_cr,
)
from domain.services.ho_delaunay import (
    L1_CUNG_SITE,
    TOA_DO_DUNG_CHUNG,
    TramDiem,
    TramPhanLop,
    phan_loai_toa_do,
    phan_lop_delaunay,
)
from domain.services.loai_tram import NHOM_IBS, loai_tram_tu_ten_tram
from domain.services.neighbor_cell_filter import (
    LY_DO_OSS_CHUA_CAU_HINH,
    LY_DO_TEN_CELL_SAI_MAU,
    MAX_CELLS_PER_HUONG,
    band_tu_lncel,
)
from domain.services.oss_routing import ma_tinh_cu_tu_ten_cell
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.services.rsboost_calculator import RsboostCalculator
from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.ten_tinh import ten_tinh_tu_ma
from domain.value_objects.vendor import chuan_hoa_vendor
from domain.value_objects.rsboost_level import RsboostLevel
from domain.value_objects.vendor import Vendor
from infrastructure.event_bus import CrEventBus

logger = logging.getLogger(__name__)

# C1.4-fix5 (20072026): buoc 13 (submit_cr - SSH connect/mkdir/SFTP/Import/
# Provision) co the mat vai phut (NETACT_CMD_TIMEOUT gio la 600s/lenh) ma
# KHONG emit event gi giua chung - can heartbeat dinh ky de SSE stream
# (api/routers/sse.py) khong bi idle-gap timeout cat nham ket noi cua FE
# trong luc CR van dang chay binh thuong o nen. 30s < 90s (idle-gap timeout
# moi cua sse.py) nen binh thuong khong bao gio cham nguong, chi cham khi
# heartbeat THAT SU ngung (task chet/process crash that).
_HEARTBEAT_INTERVAL_SECONDS = 30

# THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - buoc dau
# tien THAT SU gui lenh len NetAct qua SSH (xem current_step=13 o run_cr_flow()
# truoc khi goi submit_cr()). Loi o buoc < BUOC_SSH_BAT_DAU -> status=KHONG_CHAY
# (chua gui gi); loi o buoc >= BUOC_SSH_BAT_DAU -> status=FAILED nhu cu (da gui/
# dang gui that, ke ca khi SSH/Provision that bai hoan toan) - xem _fail().
BUOC_SSH_BAT_DAU = 13


@dataclass
class PlanResult:
    # Ket qua _prepare_plan() (buoc 3-10) - cac field "n_*/len_*" CHI de dung
    # lai NGUYEN VAN cac message SSE cua run_cr_flow() (KHONG doi noi dung khi
    # refactor tach _prepare_plan() ra). PreviewCrUseCase chi can cells/
    # rsboost_results/qrxlevmin_results/affected_cells, bo qua phan con lai.
    #
    # affected_cells them 22072026 (xac nhan voi user) - Nhanh A (danh gia
    # pham vi anh huong, KHONG loc huong/band), KHAC cells (Nhanh B, danh
    # sach THAT SU dieu chinh rsboost/qrxlevmin) - chi PreviewCrUseCase dung,
    # run_cr_flow() (CR that) khong doc field nay.
    n_huongs: int
    # Tong so cell NGUON (truoc loc) - SUA 18/10/2026 (BO CDS): doi ten tu
    # n_cell_cds, nay la so dong A cua nhanh HO. Ghi chu lich su ben duoi
    # (18092026) viet cho thoi con CDS.
    #
    # VI SAO KHONG DUNG n_huongs: n_huongs == 0 chi bat duoc truong hop CDS tra
    # danh sach huong RONG. CDS con co the tra VE HUONG nhung moi huong
    # cells=[] - luc do n_huongs > 0 ma that ra khong co cell nao, se bi xep
    # nham vao nhom "bi loc het" va bao nguoi truc di xem lai luat loc trong
    # khi thuc te la thieu du lieu nguon. Dem o MUC CELL moi dung ban chat.
    n_cell_goc: int
    affected_cells: list[Cell]
    cells: list[Cell]
    n_after_filter: int
    n_rsboost_assigned: int
    n_qrxlevmin_assigned: int
    len_current_rsboost: int
    len_missing_rsboost: int
    rsboost_results: list[CellParam]
    n_skip_rsboost: int
    len_current_qrxlevmin: int
    len_missing_qrxlevmin: int
    qrxlevmin_results: list[CellParam]
    n_skip_qrxlevmin: int
    # Ten cac cell CDS KHONG quan ly (cell_id dang phang) - da bi loai o Nhanh
    # A. Them 07092026 de PreviewCrUseCase tra ra cho nguoi dung: ket qua
    # THIEU cell ma nguoi dung tuong la du con nguy hiem hon loi 500.
    # Mac dinh [] (khong phai None) de moi cho doc khong phai kiem None.
    cell_ngoai_pham_vi: list[str] = field(default_factory=list)
    # Ban CHI TIET (V8, 09/2026) - THEM SONG SONG voi cell_ngoai_pham_vi
    # (KHONG doi field cu, FE dang doc list[str]): moi phan tu
    # {"cell_name":.., "ly_do":..} - xem domain/services/neighbor_cell_filter.py
    # ve cac ma ly do co the co.
    cell_ngoai_pham_vi_chi_tiet: list[dict] = field(default_factory=list)
    # OSS se dung cho CR nay (Giai doan 1 buoc 2, 27/09/2026) - None khi
    # KHONG con cell nao route duoc (moi cell da bi loai vao
    # cell_ngoai_pham_vi_chi_tiet). PreviewCrUseCase tra field nay ra cho
    # nguoi dung biet TRUOC KHI bam nut chay that; run_cr_flow() dung de goi
    # INetActGateway.submit_cr() (thay the get_ma_tinh() cu - xem
    # _chon_oss_va_loc_cells()).
    oss_instance: OssInstance | None = None
    # BUOC 4b (08/10/2026) - dict ket qua rieng nhanh HO (tu 18/10/2026 HO la
    # nguon duy nhat nen luon co gia tri; truoc do None khi "CDS") (GIU NGUYEN moi field khac - khong dung chung 1 field
    # "n_*"/"cells" de nhoi them du lieu HO rieng biet, xem muc 12 dau file).
    # PreviewCrUseCase doc field nay de tra them cac muc OPTIONAL cua API
    # preview; run_cr_flow() KHONG dung.
    ho_extra: dict | None = None


class TriggerCrUseCase(ITriggerCrUseCase):
    def __init__(
        self,
        network_gw: INetworkGateway,
        netact_gw: INetActGateway,
        session_repo: ICrSessionRepo,
        cell_repo: ICellParamsRepo,
        cell_infor_repo: ICellInforRepo,
        enodeb_repo: IEnodebRepo,
        event_bus: CrEventBus,
        rsboost_calc: RsboostCalculator,
        qrxlevmin_calc: QrxlevminCalculator,
        xml_builder: XmlBuilder,
        affected_cells_repo: ICrAffectedCellsRepo,
        cr_log_repo: ICrLogRepo,
        oss_router: IOssRouter,
        # BO CDS (18/10/2026): HO la nguon DUY NHAT -> bat buoc.
        ho_neighbor_repo: IHoNeighborRepo,
        cell_vi_tri_uoc_luong_repo: ICellViTriUocLuongRepo | None = None,
    ):
        self._network_gw = network_gw
        self._netact_gw = netact_gw
        self._session_repo = session_repo
        self._cell_repo = cell_repo
        self._cell_infor_repo = cell_infor_repo
        self._enodeb_repo = enodeb_repo
        self._event_bus = event_bus
        self._rsboost_calc = rsboost_calc
        self._qrxlevmin_calc = qrxlevmin_calc
        self._xml_builder = xml_builder
        # Giai doan 1 buoc 2 (27/09/2026) - chon OSS theo TUNG CELL (khong
        # phai theo tram tat nhu get_ma_tinh() cu, xem _chon_oss_va_loc_cells()).
        self._oss_router = oss_router
        # Phuong an B (22072026, DA DUYET) - luu 47 cell Nhanh A (affected_cells)
        # gan voi session, de sau nay danh gia chat luong tren dung pham vi RF
        # bi anh huong. Chi dung trong run_cr_flow() buoc 11 - _prepare_plan()
        # (dung chung voi preview) KHONG ghi DB gi, giu nguyen thiet ke cu.
        self._affected_cells_repo = affected_cells_repo
        # 22072026 (xac nhan voi user) - persist tung buoc CR vao DB SONG SONG
        # voi SSE (khong thay the) - SSE chi real-time, dong tab la mat het
        # lich su, GET /sessions/{id} truoc gio cr_logs[] LUON RONG. Dung
        # trong _log_step() (goi tu _emit()/_fail() ben duoi).
        self._cr_log_repo = cr_log_repo
        # BO CDS (18/10/2026, quyet dinh user) - danh sach cell CHI lay tu
        # thuat toan R012 (HO + Delaunay), xem muc 12 dau file. Cong tac
        # NEIGHBOR_SOURCE da bo.
        self._ho_neighbor_repo = ho_neighbor_repo
        # BUOC 4c (10/10/2026) - vi tri uoc luong CRAN CHI DUNG DE HIEN THI
        # (ban do xem truoc) - co the None (khong hien du lieu ban do, KHONG
        # anh huong thuat toan chon cell), xem domain/services/
        # cran_vi_tri_estimator.py ve ly do doc lap hoan toan voi chon_cell_cr().
        self._cell_vi_tri_uoc_luong_repo = cell_vi_tri_uoc_luong_repo

    async def execute(self, tram_id: str, tram_name: str, action: str) -> CrSession:
        # C1.4-fix (20072026): execute() gio la wrapper goi lien tiep
        # prepare_session() + run_cr_flow() - KHONG doi hanh vi (120 unit
        # test hien co goi thang execute() va ky vong chay het 18 buoc dong
        # bo, tach ham la de router goi rieng tung phan, khong phai de doi
        # test). Xem prepare_session()/run_cr_flow() ben duoi cho ly do tach.
        session = await self.prepare_session(tram_id, tram_name, action)
        # tram_name truyen rieng (khong doc tu session.tram_name) - field do
        # la read-model join tu bang tram luc list session (domain/entities/
        # cr_session.py dong 65-66), KHONG duoc set khi tao session o day.
        return await self.run_cr_flow(session, tram_name, action)

    async def prepare_session(self, tram_id: str, tram_name: str, action: str) -> CrSession:
        # C1.4-fix (20072026): tach rieng buoc 1-2 (guard + tao session) -
        # day la phan BAT BUOC PHAI dong bo, vi router (api/routers/cr.py)
        # can tra ve session_id that su ton tai trong DB NGAY trong response
        # 202, va cac loi tu choi request (409/404/422) phai tra ve dung luc
        # request, KHONG the giau trong background task. Sua bug goc: router
        # cu await ca ham execute() (bao gom SSH NetAct that o buoc 13-16,
        # co the mat vai phut) khien FE luon timeout 60s du CR chay ngam
        # thanh cong (bang chung: session #196/tram 111035 DONE that trong
        # DB nhung FE bao loi timeout).
        # ===== Buoc 1a-1d: Validate + Guard (loi o day RAISE truc tiep) =====
        if not tram_id and not tram_name:
            # Khong DomainError nao khop "input rong hoan toan" - ValueError
            # ro rang hon de crash tu nhien mo ho (cung pattern
            # CrSessionRepo.update(), B5.2)
            raise ValueError("Phai co it nhat tram_id hoac tram_name")

        if action not in ("shutdown", "cancel", "relocate"):
            # BUSINESS_RULES.md SS1 dong 13/17 - "Kiem tra action hop le:
            # shutdown|cancel|relocate". Cung ly do ValueError nhu tren.
            raise ValueError(f"action khong hop le: {action!r} (phai la shutdown|cancel|relocate)")

        if action == "cancel":
            # Rollback flow (WORKFLOW.md SS3) - flow khac hoan toan, ngoai
            # pham vi C2.1 nay (xac nhan voi user 12072026)
            raise NotImplementedError("Rollback flow (action=cancel) chua duoc code - xem WORKFLOW.md SS3")

        tram_id = await self._resolve_tram_id(tram_id, tram_name)

        existing_sessions = await self._session_repo.get_by_tram_id(tram_id)
        if any(s.status == CrStatus.RUNNING for s in existing_sessions):
            raise CrAlreadyRunningError(f"Tram {tram_id} dang co CR RUNNING", tram_id=tram_id)
        if any(s.status == CrStatus.DONE for s in existing_sessions):
            raise CrAlreadyDoneError(f"Tram {tram_id} da co CR DONE", tram_id=tram_id)

        # ===== Buoc 2: Tao cr_session (status=RUNNING) =====
        session = await self._session_repo.create(
            CrSession(id=0, tram_id=tram_id, action=action, status=CrStatus.RUNNING, plan_name=None)
        )
        await self._emit(session.id, 1, "Validate input", 5, "success", "Input hop le")
        await self._emit(session.id, 2, "Query tram + tao session", 10, "success", f"Tao session #{session.id}")
        return session

    async def _resolve_tram_id(self, tram_id: str, tram_name: str) -> str:
        # Tach rieng tu prepare_session() (buoc 1c cu) - dung CHUNG cho ca
        # prepare_session() (flow trigger that) VA PreviewCrUseCase (API
        # preview, application/preview_cr_use_case.py) vi ca 2 deu can resolve
        # tram_name -> tram_id truoc khi goi CDS, nhung preview KHONG duoc
        # dinh guard RUNNING/DONE ben duoi (guard do gan voi viec sap tao
        # cr_session that, preview khong tao session nen khong ap dung - xem
        # PreviewCrUseCase.execute()). Giu nguyen logic cu, KHONG doi hanh vi.
        if tram_id:
            return tram_id
        candidates = await self._enodeb_repo.find(tram_name)
        matches = [t for t in candidates if t.tram_name.lower() == tram_name.lower()]
        if len(matches) == 0:
            raise TramNotFoundError(f"Khong tim thay tram_name={tram_name}", tram_name=tram_name)
        if len(matches) > 1:
            # tram_name KHONG co UNIQUE constraint trong DB - tu chon 1 la
            # rui ro voi CR tac dong live network, tu choi ro rang thay vi
            # doan (xac nhan voi user 12072026)
            raise TramNotFoundError(
                f"Nhieu tram trung ten tram_name={tram_name}, can tram_id chinh xac", tram_name=tram_name
            )
        return matches[0].tram_id

    async def _prepare_plan(
        self,
        tram_id: str,
        tram_name: str,
        action: str,
    ) -> PlanResult:
        # Buoc 3-10 THUAN (goc du lieu -> filter/chon cell -> assign priority ->
        # tinh gia tri rsboost/qrxlevmin_new) - KHONG emit SSE, KHONG ghi DB
        # (KHONG goi cell_repo.snapshot_before_cr()/upsert(), 2 method do can
        # session_id THAT da ton tai trong DB, khong ap dung cho preview). Dung
        # CHUNG boi run_cr_flow() (buoc 3-10 cua flow trigger that, xem goi ben
        # duoi) VA PreviewCrUseCase (application/preview_cr_use_case.py, API
        # preview /cr/preview) - 1 noi DUY NHAT tinh toan CR, tranh 2 luong
        # lech nhau theo thoi gian neu sua rieng tung noi.
        #
        # BUOC 4b (08/10/2026) - "LAY DU LIEU GOC" (buoc 3-5 CDS, hoac tuong
        # duong ben HO) TACH rieng theo nguon, "PHAN SAU" (dinh tuyen OSS +
        # rsboost/qrxlevmin, buoc 6-10) DUNG CHUNG - xem muc 12 dau file.
        # BO CDS (18/10/2026): nhanh _lay_du_lieu_goc_cds() da xoa - HO la
        # nguon duy nhat, KHONG con fallback.
        affected_cells, cells, n_huongs, n_cell_goc, cell_ngoai_pham_vi, cell_ngoai_pham_vi_chi_tiet, ho_extra = (
            await self._lay_du_lieu_goc_ho(tram_id)
        )
        n_after_filter = len(cells)

        # --- Dinh tuyen OSS theo TUNG CELL (Giai doan 1 buoc 2, 27/09/2026) ---
        # Lam TRUOC priority_assigner: cell khong route duoc (ten sai mau/OSS
        # chua cau hinh) bi LOAI KHOI CR o day, tranh ton cong tra cuu
        # cell_infor/rsboost/qrxlevmin cho cell roi cung se bi bo. n_after_filter
        # o tren GIU NGUYEN (dai dien rieng cho ket qua loc/chon cell, khong
        # tinh ca buoc dinh tuyen - giong cach missing_rsboost/missing_qrxlevmin
        # o duoi tiep tuc thu hep "cells" ma khong sua lai n_after_filter). DUNG
        # CHUNG ca 2 nhanh (CDS/HO) - dinh tuyen chi dua vao TEN CELL + vendor,
        # khong quan tam du lieu lay tu dau (xem domain/services/oss_routing.py).
        cells, oss_instance = self._chon_oss_va_loc_cells(
            cells, cell_ngoai_pham_vi, cell_ngoai_pham_vi_chi_tiet
        )

        # action_type DA gan san trong _lay_du_lieu_goc_ho() (CellUngVien.rank_b)
        # - PriorityAssigner (luat CDS) khong con duoc goi (BO CDS 18/10/2026).
        n_rsboost_assigned = sum(1 for c in cells if c.action_type == "rsboost")
        n_qrxlevmin_assigned = sum(1 for c in cells if c.action_type == "qrxlevmin")

        rsboost_dns = [c.dist_name for c in cells if c.action_type == "rsboost"]
        current_rsboost: dict[str, RsboostLevel] = await self._cell_infor_repo.get_rsboost_by_neighbor_dns(
            rsboost_dns
        )
        missing_rsboost = [
            c for c in cells if c.action_type == "rsboost" and c.dist_name not in current_rsboost
        ]
        for c in missing_rsboost:
            logger.warning(
                "Cell khong co rsboost trong cell_infor (chua tung sync), LOAI KHOI CR",
                extra={"cell_name": c.cell_name, "dist_name": c.dist_name},
            )
        if missing_rsboost:
            missing_names = {c.cell_name for c in missing_rsboost}
            cells = [c for c in cells if c.cell_name not in missing_names]

        rsboost_results = self._rsboost_calc.calculate(cells, current_rsboost)
        n_skip_rsboost = sum(1 for p in rsboost_results if p.action_type == "skip")

        qrxlevmin_dns = [c.dist_name for c in cells if c.action_type == "qrxlevmin"]
        current_qrxlevmin: dict[str, Qrxlevmin] = await self._cell_infor_repo.get_qrxlevmin_by_neighbor_dns(
            qrxlevmin_dns
        )
        missing_qrxlevmin = [
            c for c in cells if c.action_type == "qrxlevmin" and c.dist_name not in current_qrxlevmin
        ]
        for c in missing_qrxlevmin:
            logger.warning(
                "Cell khong co qrxlevmin trong cell_infor (chua tung sync), LOAI KHOI CR",
                extra={"cell_name": c.cell_name, "dist_name": c.dist_name},
            )
        if missing_qrxlevmin:
            missing_names = {c.cell_name for c in missing_qrxlevmin}
            cells = [c for c in cells if c.cell_name not in missing_names]

        qrxlevmin_results = self._qrxlevmin_calc.calculate(cells, current_qrxlevmin)
        n_skip_qrxlevmin = sum(1 for p in qrxlevmin_results if p.action_type == "skip")

        return PlanResult(
            n_huongs=n_huongs,
            n_cell_goc=n_cell_goc,
            affected_cells=affected_cells,
            cells=cells,
            n_after_filter=n_after_filter,
            n_rsboost_assigned=n_rsboost_assigned,
            n_qrxlevmin_assigned=n_qrxlevmin_assigned,
            len_current_rsboost=len(current_rsboost),
            len_missing_rsboost=len(missing_rsboost),
            rsboost_results=rsboost_results,
            n_skip_rsboost=n_skip_rsboost,
            len_current_qrxlevmin=len(current_qrxlevmin),
            len_missing_qrxlevmin=len(missing_qrxlevmin),
            qrxlevmin_results=qrxlevmin_results,
            n_skip_qrxlevmin=n_skip_qrxlevmin,
            cell_ngoai_pham_vi=cell_ngoai_pham_vi,
            cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet,
            oss_instance=oss_instance,
            ho_extra=ho_extra,
        )

    async def _lay_du_lieu_goc_ho(
        self, tram_id: str,
    ) -> tuple[list[Cell], list[Cell], int, int, list[str], list[dict], dict]:
        """BUOC 4b (08/10/2026) - THAY THE buoc 3-5 CDS: doc ho_neighbor +
        goi domain.chon_cell_cr() (xem muc 12 dau file). Tra (affected_cells,
        cells, n_huongs=0, n_cell_nguon=so dong A, cell_ngoai_pham_vi=[]
        (HO khong co khai niem nay), cell_ngoai_pham_vi_chi_tiet=[], ho_extra).

        Loi (khong xac dinh duoc NetAct/khong co dong HO/moi sector duoi
        N_MIN) deu raise HoNoDataError (422) - KHONG tu dong fallback CDS
        (yeu cau truc tiep user)."""
        try:
            x_enb = int(tram_id)
        except ValueError as e:
            raise HoNoDataError(
                f"tram_id={tram_id} khong phai so (khong khop quy uoc enb cua du lieu HO)",
                tram_id=tram_id,
            ) from e

        # 1 LAN doc TOAN BO tram co toa do - dung lam CA (a) tap diem Delaunay/
        # phan loai toa do, (b) thong tin tram dich (vendor/toa do) - xem
        # domain/ports/outbound/repo_ports.py::IEnodebRepo.get_all_with_coords().
        tram_rows = await self._enodeb_repo.get_all_with_coords()
        tram_theo_enb: dict[int, dict] = {}
        for r in tram_rows:
            try:
                tram_theo_enb[int(r["tram_id"])] = r
            except (ValueError, TypeError):
                continue

        x_info = tram_theo_enb.get(x_enb)
        if x_info is None:
            raise HoNoDataError(
                f"Tram {tram_id} khong co toa do trong bang tram - khong chay duoc thuat toan HO",
                tram_id=tram_id,
            )

        # --- NetAct cua X: IOssRouter DANG CO (ma tinh cu + vendor) - yeu cau
        # truc tiep user "dung IOssRouter dang co", KHONG viet co che dinh
        # tuyen rieng cho buoc nay. instance_id CHINH LA khoa "netact" cua
        # bang ho_neighbor (vd "NA09" cho HNI|NOKIA - xem .env NETACT_SERVERS
        # va docs/BUSINESS_RULES.md). ---
        ma_tinh_cu = ma_tinh_cu_tu_ten_cell(x_info["tram_name"])
        vendor_x = chuan_hoa_vendor(x_info["ten_thiet_bi"])
        oss = self._oss_router.chon_oss(ma_tinh_cu, vendor_x) if ma_tinh_cu else None
        if oss is None:
            if not ma_tinh_cu:
                # Ten tram sai mau - van de DU LIEU tram, khong phai cau hinh NA.
                raise HoNoDataError(
                    f"Khong xac dinh duoc NetAct cho tram {tram_id}: ten tram khong suy duoc ma tinh cu",
                    tram_id=tram_id,
                )
            # 23/10/2026: ma_loi RIENG CAU_HINH_NETACT_LOI (khong dung
            # KHONG_CO_DU_LIEU_HO - sai nghia) + cau RO NA nao thieu gi, vao
            # ma_loi/cr_log. Chi ten NA, KHONG host/IP.
            ly_do = self._ly_do_oss(ma_tinh_cu, vendor_x)
            raise CauHinhNetactLoiError(
                f"Khong xac dinh duoc NetAct cho tram {tram_id}: "
                f"{ly_do or f'OSS chua cau hinh cho {ma_tinh_cu}|{vendor_x.value}'}",
                tram_id=tram_id,
            )
        netact = oss.instance_id

        ho_rows = await self._ho_neighbor_repo.get_by_source_enb(netact, x_enb)
        if not ho_rows:
            # SUA 15/10/2026 (yeu cau truc tiep user, "SUA THONG BAO KHI THIEU
            # HO") - phan biet 3 nguyen nhan thay vi 1 thong bao chung chung:
            # (a) X khong HO RA nhung CO HO VAO (tu tram khac) -> nghi tram
            # chua khai bao neighbor hoac rat it UE, van CO the phat song
            # (khac "khong phat song"); (b) X khong HO ca 2 chieu -> nghi
            # KHONG phat song trong ky du lieu; (c) ca NetAct KHONG co du lieu
            # gi (chua tung nap) -> GIU NGUYEN thong bao CU (khong doi ve
            # NetAct, chi la X chua co du lieu rieng ma la CA he thong).
            ho_rows_vao = await self._ho_neighbor_repo.get_by_target_enb(netact, x_enb)
            if ho_rows_vao:
                n = sum(r["ho_attempt"] for r in ho_rows_vao)
                k = len({r["source_enb"] for r in ho_rows_vao})
                raise HoNoDataError(
                    f"Tram {x_info['tram_name']} ({tram_id}) khong co luot HO di ra nao "
                    f"(chi nhan {n} luot HO vao tu {k} tram). Kha nang tram chua khai bao "
                    "neighbor hoac rat it UE. Khong chon duoc cell chay CR tu dong - xu ly "
                    "tay, de nghi kiem cau hinh neighbor cua tram.",
                    tram_id=tram_id, netact=netact,
                )
            if await self._ho_neighbor_repo.co_du_lieu_netact(netact):
                raise HoNoDataError(
                    f"Tram {x_info['tram_name']} ({tram_id}) khong co du lieu HO ca chieu "
                    "di lan chieu den. Kha nang tram khong phat song trong ky du lieu. "
                    "Xu ly tay.",
                    tram_id=tram_id, netact=netact,
                )
            raise HoNoDataError(
                f"Chua co du lieu HO cua {netact} cho tram {tram_id}",
                tram_id=tram_id, netact=netact,
            )

        tram_diem_list = [
            TramDiem(tram_id=str(enb), tram_name=info["tram_name"], lat=info["latitude"], lon=info["longitude"])
            for enb, info in tram_theo_enb.items()
        ]
        phan_loai = phan_loai_toa_do(tram_diem_list)
        x_diem = TramDiem(tram_id=tram_id, tram_name=x_info["tram_name"], lat=x_info["latitude"], lon=x_info["longitude"])
        ung_vien = [d for d in tram_diem_list if d.tram_id != tram_id]
        l1_l2 = phan_lop_delaunay(x_diem, ung_vien, phan_loai)
        x_la_dung_chung = phan_loai.get(tram_id) == TOA_DO_DUNG_CHUNG
        # THEM 12/10/2026 (yeu cau truc tiep user, "X LA IBS") - CALLER tu tinh
        # qua loai_tram_tu_ten_tram(), truyen vao chon_cell_cr() (ham domain
        # KHONG tu tinh lai) - xem dac ta "X LA IBS" o domain/services/
        # ho_cell_selector.py. GIONG mau hinh x_la_dung_chung o tren.
        x_la_ibs = loai_tram_tu_ten_tram(x_info["tram_name"]) == NHOM_IBS

        dn_map = await self._cell_infor_repo.get_dn_map_theo_enb_lcr()
        cell_name_theo_enb_lcr = {k: v["cell_name"] for k, v in dn_map.items()}
        tram_dich_theo_enb = {
            enb: ThongTinTramDich(
                tram_id=str(enb), tram_name=info["tram_name"], ten_thiet_bi=info["ten_thiet_bi"],
                lat=info["latitude"], lon=info["longitude"],
                toa_do_dung_chung=phan_loai.get(str(enb)) == TOA_DO_DUNG_CHUNG,
            )
            for enb, info in tram_theo_enb.items()
        }

        try:
            kq = chon_cell_cr(
                tram_id, ho_rows, l1_l2, tram_dich_theo_enb, cell_name_theo_enb_lcr,
                x_lat=x_info["latitude"], x_lon=x_info["longitude"], x_la_toa_do_dung_chung=x_la_dung_chung,
                x_la_ibs=x_la_ibs,
            )
        except KhongCoDuLieuHoError as e:
            raise HoNoDataError(str(e), tram_id=tram_id, netact=netact) from e

        affected_cells: list[Cell] = []
        for c in kq.a:
            cell = self._cell_ung_vien_to_cell(c, dn_map)
            if cell is not None:
                affected_cells.append(cell)

        cells: list[Cell] = []
        for c in kq.b:
            cell = self._cell_ung_vien_to_cell(c, dn_map)
            if cell is None:
                # SUA 09/10/2026 (yeu cau truc tiep user, bug phat hien qua
                # xem truoc tram 117713 that): domain.chon_cell_cr() DA loai
                # can_ghep_ten=True (chua sync cell_infor) KHOI B TRUOC khi
                # xep hang top 2/sector (xem domain/services/ho_cell_selector.py)
                # - nhanh nay gio la PHONG VE 2 LOP (khong tin tuyet doi domain
                # da loc dung, giong nhieu noi khac trong du an), tren thuc te
                # KHONG con xay ra tru khi dn_map o day LECH voi
                # cell_name_theo_enb_lcr da truyen vao chon_cell_cr() (ly
                # thuyet khong xay ra, xem _cell_ung_vien_to_cell()).
                logger.warning(
                    "Cell trong danh sach B (HO) khong resolve duoc DN tu cell_infor - LOAI KHOI CR "
                    "(PHONG VE 2 LOP - domain da loc can_ghep_ten khoi B, xem SUA 09/10/2026)",
                    extra={"target_enb": c.target_enb, "target_lcr": c.target_lcr},
                )
                continue
            cells.append(cell)

        bat_thuong_ids = {id(c) for c in kq.bat_thuong}

        def _co_cua_cell(c: CellUngVien) -> list[str]:
            co: list[str] = []
            if c.can_ghep_ten:
                co.append("CAN_GHEP_TEN")
            if id(c) in bat_thuong_ids:
                co.append("BAT_THUONG")
            return co

        # sector/sectors_khac THEM cho bang A (12/10/2026, yeu cau truc tiep
        # user: "FE khong hien duoc, nguoi dung thay %HO lech so lan HO khac
        # mau so sector" - vi A hien tai KHONG lo sector nen nguoi dung khong
        # biet %HO/so_ho dang tinh tren mau so sector NAO). sectors_theo_khoa
        # gom TU quan_he_day_du (GIU CA sector "phu" TRUOC dedup xuyen sector,
        # xem QuanHe o domain/services/ho_cell_selector.py) - 1 cell co the
        # nhan HO tu NHIEU sector cua X, chi "thang" 1 sector (GD4, da la
        # c.sector sau dedup) nhung cac sector "phu" con lai VAN la thong tin
        # that (co HO sang cell nay), FE can biet de khong tuong %HO/so_ho
        # hien tai da GOM CA cac sector do (KHONG - no la % CUA RIENG sector
        # thang, xem GD1).
        sectors_theo_khoa: dict[tuple[int, int], list[int]] = {}
        for q in kq.quan_he_day_du:
            sectors_theo_khoa.setdefault((q.target_enb, q.target_lcr), []).append(q.sector)

        theo_cell_name: dict[str, dict] = {}
        khong_ghep_ten: list[dict] = []
        for c in kq.a:
            cac_sector = sorted(set(sectors_theo_khoa.get((c.target_enb, c.target_lcr), [c.sector])))
            sectors_khac = [s for s in cac_sector if s != c.sector]
            chi_tiet = {
                "pct_ho": c.pct_trong_sector, "so_ho": c.ho_attempt, "sr": c.ho_sr,
                "layer": c.layer, "co": _co_cua_cell(c),
                "sector": c.sector, "sectors_khac": sectors_khac,
            }
            if c.cell_name is not None:
                theo_cell_name[c.cell_name] = chi_tiet
            else:
                khong_ghep_ten.append({
                    "target_enb": c.target_enb, "target_lcr": c.target_lcr,
                    "vendor": c.vendor, **chi_tiet,
                })

        x_co: list[str] = []
        if x_la_dung_chung:
            x_co.append("TOA_DO_DUNG_CHUNG")
        if x_la_ibs:
            # THEM 12/10/2026 (yeu cau truc tiep user) - giai thich VI SAO
            # l1_l2 rong/B thuan theo HO (xem dac ta "X LA IBS" o
            # domain/services/ho_cell_selector.py), GIONG CACH co
            # TOA_DO_DUNG_CHUNG giai thich cho truong hop CRAN.
            x_co.append("TRAM_IBS")
        if kq.ho_di_xa_x:
            x_co.append("HO_DI_XA")
        if kq.sectors_it_du_lieu:
            x_co.append("IT_DU_LIEU")

        ban_do = await self._xay_du_lieu_ban_do(
            x_enb, x_info, netact, l1_l2, kq, phan_loai, tram_theo_enb, x_la_dung_chung, x_co, dn_map,
        )

        # BO truong "nguon_du_lieu" (14/10/2026, yeu cau truc tiep user) - gia
        # dinh "7 ngay" (_SO_NGAY_BAO_CAO_HO, da XOA) SAI: NA14 THAT ra cung
        # gop theo TUAN giong NA09 (PERIOD_START_TIME = ngay dau tuan, Thu
        # Hai), KHONG phai 1 ngay nhu khao sat truoc do nham tuong (file chi
        # co 1 dong PERIOD_START_TIME vi CA TUAN do GOP VE 1 moc, khong phai
        # thieu du lieu). User quyet dinh KHONG hien dong nay tren man xem
        # truoc nua (thay vi sua lai chuoi cho dung) - xem docs/BUSINESS_RULES.md.
        # Cot ho_neighbor.ngay_du_lieu VAN GIU (biet du lieu cu/moi khi can
        # tra DB truc tiep), chi KHONG lo ra API nay nua.
        ho_extra = {
            "x_co": x_co,
            "sectors_it_du_lieu": sorted(kq.sectors_it_du_lieu),
            "theo_cell_name": theo_cell_name,
            "khong_ghep_ten": khong_ghep_ten,
            "quan_he_day_du": [
                {
                    "sector": q.sector, "target_enb": q.target_enb, "target_lcr": q.target_lcr,
                    "pct_trong_sector": q.pct_trong_sector, "ho_attempt": q.ho_attempt,
                    "ho_sr": q.ho_sr, "layer": q.layer,
                }
                for q in kq.quan_he_day_du
            ],
            # BUOC 4c (10/10/2026) - xem _xay_du_lieu_ban_do().
            "ban_do": ban_do,
        }

        return affected_cells, cells, 0, len(kq.a), [], [], ho_extra

    async def _xay_du_lieu_ban_do(
        self,
        x_enb: int,
        x_info: dict,
        netact: str,
        l1_l2: list[TramPhanLop],
        kq,
        phan_loai: dict[str, str],
        tram_theo_enb: dict[int, dict],
        x_la_dung_chung: bool,
        x_co: list[str],
        dn_map: dict[tuple[int, int], dict],
    ) -> dict:
        """BUOC 4c (10/10/2026, yeu cau truc tiep user) - du lieu PHU TRO cho
        ban do xem truoc CR (field OPTIONAL, chi PreviewCrUseCase doc). CHI
        DUNG DE HIEN THI - domain.chon_cell_cr()/phan_lop_delaunay() da chay
        XONG roi moi goi ham nay, KHONG co chieu nguoc lai anh huong thuat toan."""
        cran_map: dict[tuple[int, int], dict] = {}
        if self._cell_vi_tri_uoc_luong_repo is not None:
            try:
                cran_map = await self._cell_vi_tri_uoc_luong_repo.get_by_netact(netact)
            except Exception:
                logger.warning("Khong doc duoc cell_vi_tri_uoc_luong - ban do se thieu vi tri CRAN", exc_info=True)

        x_lat, x_lon = x_info["latitude"], x_info["longitude"]
        ma_tinh_x = x_info.get("ma_tinh")

        vi_tri_uoc_luong_x = None
        if x_la_dung_chung:
            # cell_name (THEM, yeu cau truc tiep user) - ghep theo LNBTS (x_enb)
            # + LCR: "lcr" trong cell_vi_tri_uoc_luong THUC CHAT la source_sector
            # (0-9, xem domain/services/cran_vi_tri_estimator.py), KHONG phai
            # LNCEL id that (vd 11/12/51/52) nen KHONG the dn_map.get((x_enb,lcr))
            # truc tiep - phai doi chieu qua "real_lcr % 10 == sector" (CUNG quy
            # uoc voi cran_map.get((c.target_enb, c.target_lcr % 10)) da dung
            # cho tram DICH o duoi). Nhieu band CUNG sector (vd LCR 11 va 51
            # cung sector 1) -> LAY cell CO LCR THAT NHO NHAT (xac dinh, khong
            # ngau nhien) lam dai dien hien thi; khong tim duoc -> None.
            cell_name_theo_sector_x: dict[int, str | None] = {}
            for (enb_dn, real_lcr), info_dn in sorted(dn_map.items(), key=lambda kv: kv[0]):
                if enb_dn != x_enb:
                    continue
                cell_name_theo_sector_x.setdefault(real_lcr % 10, info_dn["cell_name"])
            vi_tri_uoc_luong_x = [
                {"lcr": lcr, "cell_name": cell_name_theo_sector_x.get(lcr), **info}
                for (enb, lcr), info in cran_map.items() if enb == x_enb
            ]

        # TAM duong bao (THEM 10/10/2026, yeu cau truc tiep user) - X la CRAN:
        # toa do X (lat/lon tren) la vi tri TONG DAI/baseband, KHONG phai anten
        # - dung LAM TAM de sap goc/ve duong bao se SAI (lech huong thuc te cac
        # cell toa ra). Tam DUNG = trung binh vi tri CAC CELL DA UOC LUONG cua
        # X (vi_tri_uoc_luong_x, chinh ban than X - KHAC vi_tri_uoc_luong cua
        # tram DICH dung trong theo_tram_dich duoi day). KHONG cell nao uoc
        # luong duoc (CRAN nhung chua du dieu kien uoc luong - xem
        # domain/services/cran_vi_tri_estimator.py) -> danh fallback ve toa do
        # tong dai, danh dau tam_la_tong_dai=True de FE biet vi tri nay KEM TIN
        # CAY (ghi chu "vi tri uoc luong" cho marker X trong truong hop nguoc
        # lai, tam_la_tong_dai=False).
        if x_la_dung_chung and vi_tri_uoc_luong_x:
            tam_lat = sum(c["lat"] for c in vi_tri_uoc_luong_x) / len(vi_tri_uoc_luong_x)
            tam_lon = sum(c["lon"] for c in vi_tri_uoc_luong_x) / len(vi_tri_uoc_luong_x)
            tam_la_tong_dai = False
        elif x_la_dung_chung:
            # CRAN nhung KHONG cell nao uoc luong duoc - fallback TAM VE toa do
            # tong dai (van TOT HON la khong co tam nao, nhung PHAI danh dau
            # ro de FE biet do tin cay THAP, xem ghi chu dau khoi).
            tam_lat, tam_lon = x_lat, x_lon
            tam_la_tong_dai = True
        else:
            # X KHONG phai CRAN - toa do X CHINH la vi tri anten thuc, khong co
            # van de "tong dai" nao de fallback.
            tam_lat, tam_lon = x_lat, x_lon
            tam_la_tong_dai = False

        x_block = {
            "lat": x_lat, "lon": x_lon,
            "ma_tinh": ma_tinh_x,
            "ten_tinh": ten_tinh_tu_ma(ma_tinh_x),
            "khu_vuc": khu_vuc_tu_ma_tinh(ma_tinh_x),
            "co": x_co,
            "vi_tri_uoc_luong_cell": vi_tri_uoc_luong_x,
            "tam_lat": tam_lat, "tam_lon": tam_lon, "tam_la_tong_dai": tam_la_tong_dai,
            # loai_tram THEM (11-12/10/2026, yeu cau truc tiep user, "PHAN LOAI
            # TRAM + DO ANH HUONG") - CHI hien thi, KHONG doi cach tinh L1/L2/
            # vung Z/danh sach B (xem dac ta domain/services/loai_tram.py).
            "loai_tram": loai_tram_tu_ten_tram(x_info["tram_name"]),
        }

        def _diem_tram_phan_lop(t: TramPhanLop) -> dict:
            return {
                "tram_id": t.tram_id, "ten": t.tram_name, "lat": t.lat, "lon": t.lon,
                "loai_tram": loai_tram_tu_ten_tram(t.tram_name),
            }

        # SUA 14/10/2026 (yeu cau truc tiep user, "VONG L1/L2 TRA VE"), SUA LAI
        # 15/10/2026 (yeu cau truc tiep user, "GIU TUONG THICH NGUOC") - lan
        # dau doi han ban_do.l1/l2 tu list phang sang dict (lam vo FE dang
        # doc list truc tiep). NAY: ban_do.l1/l2 GIU NGUYEN la list (nhu truoc
        # 14/10/2026) - CHI sap theo goc don thuan (sap_theo_goc()). Thong tin
        # "vong hinh sao" (chen X lam dinh khi khoang trong goc > 180 do, co
        # x_tren_vien - dung CHUNG ham duong_bao_hinh_sao() voi "duong bao
        # vung bi anh huong", xem domain/services/geo_utils.py) chuyen sang 2
        # field MOI, TACH RIENG: ban_do.l1_vong/l2_vong = {danh_sach, x_tren_vien}.
        # X khong phai CRAN/IBS tai day (l1_l2 da rong neu la 2 truong hop do,
        # xem tren) nen DUNG THANG x_lat/x_lon (khong can "tam" uoc luong CRAN).
        def _vong_hinh_sao(diem_list: list[dict]) -> dict:
            if x_lat is None or x_lon is None or len(diem_list) < 3:
                return {"danh_sach": diem_list, "x_tren_vien": False}
            x_diem_vong = {
                "tram_id": str(x_enb), "ten": x_info["tram_name"], "lat": x_lat, "lon": x_lon,
                "loai_tram": loai_tram_tu_ten_tram(x_info["tram_name"]),
            }
            kq_vong = duong_bao_hinh_sao(x_diem_vong, diem_list)
            return {"danh_sach": kq_vong["polygon"], "x_tren_vien": kq_vong["x_tren_vien"]}

        # SUA 16/10/2026 (yeu cau truc tiep user, "VONG L1 KHONG LAY TRAM CUNG
        # SITE") - ban_do.l1 (list phang, tuong thich nguoc) GIU NGUYEN gom ca
        # tram L1_CUNG_SITE (van la "L1" ve y nghia). RIENG l1_vong (duong bao
        # hinh sao ve tren ban do) chi lay L1 HINH HOC THAT (tu Delaunay) -
        # tram cung site thuong trung/gan sat toa do X, dua vao se lam MEO
        # vong (khong co y nghia hinh hoc de ve).
        l1_list = [_diem_tram_phan_lop(t) for t in l1_l2 if t.layer in ("L1", L1_CUNG_SITE)]
        l1_vong_nguon = [_diem_tram_phan_lop(t) for t in l1_l2 if t.layer == "L1"]
        l2_list = [_diem_tram_phan_lop(t) for t in l1_l2 if t.layer == "L2"]
        if x_lat is not None and x_lon is not None:
            l1_list = sap_theo_goc(l1_list, (x_lat, x_lon), key=lambda d: (d["lat"], d["lon"]))
            l1_vong_nguon = sap_theo_goc(l1_vong_nguon, (x_lat, x_lon), key=lambda d: (d["lat"], d["lon"]))
            l2_list = sap_theo_goc(l2_list, (x_lat, x_lon), key=lambda d: (d["lat"], d["lon"]))
        l1_vong = _vong_hinh_sao(l1_vong_nguon)
        l2_vong = _vong_hinh_sao(l2_list)

        # --- Tram bi anh huong (gom theo tram dich cua tung cell trong A) ---
        # SUA 11/10/2026 (yeu cau truc tiep user, bug phat hien tren ban do that
        # tram 117903): tong_pct_ho TRUOC DAY = CONG % TUNG SECTOR cua tung cell
        # (c.pct_trong_sector, mau so la tong HO cua RIENG sector do) - SAI
        # NGHIA vi cac sector co mau so KHAC NHAU (sector it du lieu -> % 1 cell
        # bi THOI PHONG), cong lai VUOT 100%/tram, tong CA ban do tram 117903
        # len toi 215%. DUNG: % cua 1 tram = (tong HO cell gui SANG tram do,
        # CONG DON QUA MOI sector) / (TONG HO cua X - CHINH LA sum(ho_attempt)
        # tren TOAN BO kq.a, dinh nghia GIONG HET "Tong HO cua X" cua luat
        # HO_DI_XA - xem GD2 o domain/services/ho_cell_selector.py) - 1 mau so
        # DUY NHAT cho MOI tram nen tong cac tram <= 100%. % tung cell/sector
        # trong "cells" GIU NGUYEN (pct_trong_sector, dung cho bang cell, KHONG
        # phai dung de suy ra % tram).
        tong_ho_x = sum(c.ho_attempt for c in kq.a)

        theo_tram_dich: dict[str, dict] = {}
        tong_ho_theo_tram: dict[str, int] = {}
        # Tich luy HO theo TUNG VI TRI (tram_id, lat, lon) song song voi vong
        # lap tren - dung truc tiep cho dinh duong bao duoi, KHONG can quet lai
        # nhom["cells"] (vi "cells" chi co pct_trong_sector, khong co ho_attempt
        # tho de tinh % moi).
        tong_ho_theo_vi_tri: dict[tuple[str, float, float], int] = {}

        for c in kq.a:
            if c.tram_dich_id is None:
                continue  # KHONG ro tram dich (vd KHONG_RO_TRAM) - khong co gi de gom vao ban do
            nhom = theo_tram_dich.setdefault(c.tram_dich_id, {
                "tram_id": c.tram_dich_id, "ten": c.tram_dich_ten,
                "lat": tram_theo_enb.get(c.target_enb, {}).get("latitude"),
                "lon": tram_theo_enb.get(c.target_enb, {}).get("longitude"),
                "tong_pct_ho": 0.0, "cells": [],
                # loai_tram THEM (11-12/10/2026) - CHI hien thi, xem dac ta o
                # x_block o tren (cung 1 field, cung quy uoc).
                "loai_tram": loai_tram_tu_ten_tram(c.tram_dich_ten),
            })
            tong_ho_theo_tram[c.tram_dich_id] = tong_ho_theo_tram.get(c.tram_dich_id, 0) + c.ho_attempt

            dich_la_dung_chung = phan_loai.get(str(c.target_enb)) == TOA_DO_DUNG_CHUNG
            lat_cell, lon_cell, khong_xac_dinh = None, None, False
            if dich_la_dung_chung:
                uoc_luong = cran_map.get((c.target_enb, c.target_lcr % 10))
                if uoc_luong is not None:
                    lat_cell, lon_cell = uoc_luong["lat"], uoc_luong["lon"]
                else:
                    khong_xac_dinh = True
            else:
                lat_cell = tram_theo_enb.get(c.target_enb, {}).get("latitude")
                lon_cell = tram_theo_enb.get(c.target_enb, {}).get("longitude")
                khong_xac_dinh = lat_cell is None or lon_cell is None

            nhom["cells"].append({
                "cell_name": c.cell_name, "target_enb": c.target_enb, "target_lcr": c.target_lcr,
                "pct_ho": c.pct_trong_sector, "lat": lat_cell, "lon": lon_cell,
                "khong_xac_dinh_vi_tri": khong_xac_dinh,
            })
            if not khong_xac_dinh:
                khoa_vi_tri = (c.tram_dich_id, lat_cell, lon_cell)
                tong_ho_theo_vi_tri[khoa_vi_tri] = tong_ho_theo_vi_tri.get(khoa_vi_tri, 0) + c.ho_attempt

        for tram_id, nhom in theo_tram_dich.items():
            nhom["tong_pct_ho"] = (tong_ho_theo_tram[tram_id] / tong_ho_x) if tong_ho_x else 0.0

        # --- Duong bao hinh sao quanh X (THEM 10/10/2026, THAY THE convex hull
        # - yeu cau truc tiep user "X o trong, MOI tram bi anh huong la 1 dinh").
        # Diem: moi tram bi anh huong -> 1 diem (lay VI TRI RIENG theo tong_ho_theo_vi_tri
        # o tren - tram THUONG het cells cung 1 vi tri (toa do tram) nen tu
        # nhien gom ve 1 diem; tram CRAN co the co NHIEU vi tri uoc luong khac
        # nhau theo sector -> nhieu diem rieng, dung yeu cau "moi vi tri cell
        # uoc luong la 1 diem rieng"). pct_ho cua MOI dinh = % TREN TONG HO cua
        # X (CUNG cong thuc voi tong_pct_ho cua tram o tren, SUA 11/10/2026).
        ten_theo_tram_dich = {tid: nhom["ten"] for tid, nhom in theo_tram_dich.items()}
        loai_theo_tram_dich = {tid: nhom["loai_tram"] for tid, nhom in theo_tram_dich.items()}
        diem_bao: list[dict] = [
            {
                "tram_id": tram_id, "ten": ten_theo_tram_dich[tram_id],
                "lat": lat, "lon": lon,
                "pct_ho": (attempt / tong_ho_x) if tong_ho_x else 0.0,
                # loai_tram THEM (11-12/10/2026) - CHI hien thi tren dinh duong bao.
                "loai_tram": loai_theo_tram_dich[tram_id],
            }
            for (tram_id, lat, lon), attempt in tong_ho_theo_vi_tri.items()
        ]

        if tam_lat is not None and tam_lon is not None:
            # Dung TAM (tam_lat/tam_lon cua x_block, co the la trung binh cac
            # cell CRAN uoc luong cua X - xem dac ta TAM duong bao o tren),
            # KHONG dung thang x_lat/x_lon - sai huong neu X la CRAN. loai_tram
            # cua X cung dua vao dinh X (neu bi chen vao polygon do khoang
            # trong goc > 180 do) de dong nhat shape voi cac dinh khac.
            x_diem_bao = {
                "tram_id": str(x_enb), "ten": x_info["tram_name"], "lat": tam_lat, "lon": tam_lon,
                "loai_tram": x_block["loai_tram"],
            }
            duong_bao = duong_bao_hinh_sao(x_diem_bao, diem_bao)
        else:
            duong_bao = {"polygon": None, "doan": [], "x_tren_vien": False}

        return {
            "x": x_block,
            "l1": l1_list,
            "l2": l2_list,
            # l1_vong/l2_vong THEM 15/10/2026 (yeu cau truc tiep user, "GIU
            # TUONG THICH NGUOC") - field MOI, OPTIONAL, song song voi l1/l2
            # (KHONG thay the) - xem dac ta _vong_hinh_sao() o tren.
            "l1_vong": l1_vong,
            "l2_vong": l2_vong,
            "tram_bi_anh_huong": list(theo_tram_dich.values()),
            "duong_bao": duong_bao,
        }

    def _cell_ung_vien_to_cell(self, c: CellUngVien, dn_map: dict[tuple[int, int], dict]) -> Cell | None:
        """CellUngVien (domain/services/ho_cell_selector.py) -> Cell entity
        (dung CHUNG voi nhanh CDS o "phan sau" cua _prepare_plan() - xem muc
        12 dau file). can_ghep_ten=True (khong resolve duoc ten/DN qua
        cell_infor) -> None, KHONG tao Cell "thieu dist_name" (RsboostCalculator/
        QrxlevminCalculator/XmlBuilder deu BAT BUOC can dist_name hop le)."""
        if c.can_ghep_ten or c.cell_name is None:
            return None
        thong_tin = dn_map.get((c.target_enb, c.target_lcr))
        if thong_tin is None:
            # Ly thuyet khong xay ra (cell_name_theo_enb_lcr truyen vao
            # chon_cell_cr() lay TU CHINH dn_map nay) - an toan tra None thay
            # vi crash neu co lech du lieu hiem gap nao do.
            return None
        dn = thong_tin["dn_lncel"]
        return Cell(
            cell_id=dn,
            cell_name=c.cell_name,
            dist_name=dn,
            priority=0,  # HO khong co khai niem priority CDS - gia tri trung lap, downstream KHONG dung de loc/sap xep
            huong_id=None,  # HO khong co khai niem huong_id CDS
            # rank_b: "rsboost"|"qrxlevmin" cho Nhanh B; None cho Nhanh A
            # (affected, khong chay CR) -> "" GIONG quy uoc filter_affected()
            # cu (xem domain/services/neighbor_cell_filter.py).
            action_type=c.rank_b or "",
            status="active",
            sector=c.sector,
            band=band_tu_lncel(f"LNCEL-{c.target_lcr}"),
        )

    def _ly_do_oss(self, ma_tinh_cu: str, vendor: Vendor) -> str | None:
        # Chi nhan chuoi: router fake/MagicMock trong test cu tra doi tuong
        # Mock - khong duoc lot vao thong bao loi/JSON.
        ly_do = self._oss_router.ly_do_khong_chon(ma_tinh_cu, vendor)
        return ly_do if isinstance(ly_do, str) else None

    def _chon_oss_va_loc_cells(
        self,
        cells: list[Cell],
        cell_ngoai_pham_vi: list[str],
        cell_ngoai_pham_vi_chi_tiet: list[dict],
    ) -> tuple[list[Cell], OssInstance | None]:
        """Gom cell theo OSS se dung, loai cell KHONG route duoc.

        Giai doan 1 buoc 2 (27/09/2026, quyet dinh dinh tuyen OSS theo TUNG
        CELL - khong phai theo tram tat nhu get_ma_tinh() cu):
          - Voi MOI cell: suy ma_tinh_cu tu TEN CELL (domain/services/
            oss_routing.py - da xac nhan 456/456 cell that dung mau, KHONG
            dung tram_name/cot tram.ma_tinh, xem ly do trong module do).
            Khong suy duoc -> loai, ly do TEN_CELL_SAI_MAU.
          - vendor: NOKIA neu cell_id la DN Nokia. Tai THOI DIEM nay moi cell
            da qua filter_affected()/filter_for_cr() (chi giu cell_id dang DN
            Nokia - xem neighbor_cell_filter.py::co_dang_dn_nokia()) nen TREN
            THUC TE luon la NOKIA; van goi lai ham kiem tra (khong hardcode
            Vendor.NOKIA) de code tu dung neu sau nay ho tro them vendor khac
            qua NetAct.
          - self._oss_router.chon_oss(ma_tinh_cu, vendor) tra None -> loai,
            ly do OSS_CHUA_CAU_HINH (chua co route, hoac credential con la
            placeholder "???" - xem IOssRouter.chon_oss()).
          - Sau khi gom: > 1 OSS khac nhau trong CUNG 1 CR -> raise
            CrNhieuOssError (422) - 1 CR hien tai CHI build 1 XML/goi 1 lan
            submit_cr(), KHONG the tu dong tach gui nhieu OSS. Danh sach cell
            KHONG bi mat truoc khi raise (van nam trong "cells" dau vao) -
            loi nay CHAN CA CR, khac cac ly do loai TUNG CELL rieng le o tren.

        cell_ngoai_pham_vi/cell_ngoai_pham_vi_chi_tiet: TRUYEN VAO de APPEND
        THEM (khong tao list moi) - 2 danh sach nay da duoc filter_affected()
        dien mot phan (ly do CELL_ID_PHANG), dung CHUNG co che bao cao "cell
        nay vi sao khong nam trong CR" cho ca 2 nguon (xem
        neighbor_cell_filter.py dau file, doan comment canh 2 hang so
        LY_DO_TEN_CELL_SAI_MAU/LY_DO_OSS_CHUA_CAU_HINH).
        """
        theo_oss: dict[OssInstance, list[Cell]] = {}
        cells_da_route: list[Cell] = []

        for c in cells:
            ma_tinh_cu = ma_tinh_cu_tu_ten_cell(c.cell_name)
            if ma_tinh_cu is None:
                logger.warning(
                    "Ten cell khong dung mau 4G-...-XXX, khong suy duoc ma tinh cu de dinh tuyen OSS - LOAI KHOI CR",
                    extra={"cell_name": c.cell_name},
                )
                if c.cell_name not in cell_ngoai_pham_vi:
                    cell_ngoai_pham_vi.append(c.cell_name)
                cell_ngoai_pham_vi_chi_tiet.append({"cell_name": c.cell_name, "ly_do": LY_DO_TEN_CELL_SAI_MAU})
                continue

            vendor = Vendor.NOKIA if co_dang_dn_nokia(c.cell_id) else Vendor.UNKNOWN
            oss = self._oss_router.chon_oss(ma_tinh_cu, vendor)
            if oss is None:
                logger.warning(
                    "Khong co OSS da cau hinh cho (ma_tinh_cu, vendor) nay - LOAI KHOI CR",
                    extra={"cell_name": c.cell_name, "ma_tinh_cu": ma_tinh_cu, "vendor": vendor.value},
                )
                if c.cell_name not in cell_ngoai_pham_vi:
                    cell_ngoai_pham_vi.append(c.cell_name)
                # ly_do giu MA CO DINH (FE map ma -> text); chi_tiet (23/10/2026)
                # mang cau cu the "NA14 cau hinh loi: thieu password".
                cell_ngoai_pham_vi_chi_tiet.append({
                    "cell_name": c.cell_name, "ly_do": LY_DO_OSS_CHUA_CAU_HINH,
                    "chi_tiet": self._ly_do_oss(ma_tinh_cu, vendor),
                })
                continue

            theo_oss.setdefault(oss, []).append(c)
            cells_da_route.append(c)

        if len(theo_oss) > 1:
            chi_tiet = "; ".join(f"{oss.instance_id}: {len(cs)} cell" for oss, cs in theo_oss.items())
            raise CrNhieuOssError(
                f"Cell lan can thuoc {len(theo_oss)} OSS khac nhau ({chi_tiet}) - "
                "1 CR khong the tu dong tach thanh nhieu XML gui nhieu OSS. "
                "Can nguoi van hanh quyet dinh (co the phai tach thanh nhieu CR rieng theo vung).",
            )

        oss_instance = next(iter(theo_oss), None)
        return cells_da_route, oss_instance

    async def run_cr_flow(self, session: CrSession, tram_name: str, action: str) -> CrSession:
        # C1.4-fix (20072026): buoc 3-18 - phan CHAY NEN (router goi qua
        # FastAPI BackgroundTasks, KHONG await truc tiep trong request/response
        # cycle nua). Co the mat vai chuc giay den vai phut vi buoc 13-16 goi
        # SSH NetAct that (submit_cr) - day chinh la ly do PHAI tach khoi
        # prepare_session(), neu khong HTTP response se bi block cho toi khi
        # SSH xong (bug goc, xem CHANGELOG o prepare_session()).
        tram_id = session.tram_id  # da resolve xong (tram_name->tram_id neu can) o prepare_session, dung lai nguyen ven

        # ===== Buoc 3-18: moi loi DomainError sau day CATCH, set FAILED, RETURN =====
        # current_step_* theo doi buoc dang chay - dung khi except DomainError
        # o cuoi can biet CHINH XAC buoc nao that bai de emit SSE/step dung
        # (KHONG hardcode step=0 chung chung cho moi loai loi).
        current_step, current_step_name, current_step_pct = 3, "Goi CDS API /cell/neighbors", 18
        # oss_da_chon (02/10/2026) - theo doi OSS DA XAC DINH duoc (neu co) tai
        # THOI DIEM loi, de _fail() ghi lai cr_session.oss_instance_id/noc
        # ngay ca khi CR that bai SAU buoc chon OSS (vd Import/Provision hong
        # tren NetAct that - OSS VAN duoc dung that, chi ket qua la loi). Mac
        # dinh None: neu _prepare_plan() raise TRUOC KHI tra ve plan (vd
        # CrNhieuOssError - nhieu OSS, KHONG chon duoc 1 cai cu the; hoac loi
        # CDS o buoc 3 TRUOC CA buoc dinh tuyen) thi gia tri nay GIU NGUYEN
        # None - dung y nghia "CR bi tu choi TRUOC khi chon OSS -> de NULL".
        oss_da_chon: OssInstance | None = None
        try:
            # --- Buoc 3-10: CDS -> filter -> assign priority -> tinh gia tri
            # rsboost/qrxlevmin_new - GOM vao _prepare_plan() (21072026, API
            # preview) de PreviewCrUseCase (application/preview_cr_use_case.py)
            # dung lai CHINH XAC cung 1 code path (khong viet lai filter/
            # calculator o 2 noi). _prepare_plan() KHONG emit SSE/KHONG ghi DB
            # (de dung duoc cho ca preview) - emit lai o day sau khi co ket
            # qua, GIU NGUYEN thu tu/noi dung message nhu truoc refactor. ---
            # BO CDS (18/10/2026) - buoc 3 la doc ho_neighbor (HO + Delaunay).
            await self._emit(session.id, 3, "Lay du lieu HO", 18, "running", "Dang doc du lieu HO...")
            plan = await self._prepare_plan(tram_id, tram_name, action)
            # _prepare_plan() da tra ve thanh cong -> da biet OSS nao duoc
            # chon (co the van la None neu moi cell lan can bi loai khoi dinh
            # tuyen - xem guard truoc buoc 13 ben duoi) - ghi lai NGAY de moi
            # nhanh that bai SAU diem nay (buoc 12 XML/buoc 13-16 SSH) deu co
            # du lieu cho _fail() ghi vao cr_session.
            oss_da_chon = plan.oss_instance
            await self._emit(session.id, 3, "Lay du lieu HO", 18, "success", f"Nhan {plan.n_cell_goc} cell nguon")

            await self._emit(session.id, 4, "Filter cell", 25, "success", f"Sau filter: {plan.n_after_filter} cells hop le")
            await self._emit(
                session.id, 5, "Band priority filter", 30, "success",
                # Doc THANG tu hang so (khong go so): thong bao SSE nay hien
                # len man hinh nguoi truc - go cung "4" thi lan doi tran tiep
                # theo no se noi doi ma khong ai nhan ra.
                f"Band priority + loai NB-/MBF_/LNCEL-2xx + chon toi da "
                f"{MAX_CELLS_PER_HUONG} cell/huong: con {plan.n_after_filter} cells hop le",
            )

            await self._emit(
                session.id, 6, "Assign priority", 35, "success",
                f"Assign: {plan.n_rsboost_assigned} cells rsboost, {plan.n_qrxlevmin_assigned} cells qrxlevmin",
            )

            await self._emit(
                session.id, 7, "Lay rsboost_current", 42, "success",
                f"Lay duoc rsboost_current cho {plan.len_current_rsboost} cells, loai {plan.len_missing_rsboost} cell chua co du lieu trong cell_infor",
            )

            n_skip_rsboost = plan.n_skip_rsboost
            await self._emit(
                session.id, 8, "Tinh rsboost_new", 48, "success",
                f"{len(plan.rsboost_results) - n_skip_rsboost} cells thay doi, {n_skip_rsboost} cells o cap (skip)",
            )

            await self._emit(
                session.id, 9, "Lay qrxlevmin_current", 52, "success",
                f"Lay duoc qrxlevmin_current cho {plan.len_current_qrxlevmin} cells, loai {plan.len_missing_qrxlevmin} cell chua co du lieu trong cell_infor",
            )

            n_skip_qrxlevmin = plan.n_skip_qrxlevmin
            await self._emit(
                session.id, 10, "Tinh qrxlevmin_new", 56, "success",
                f"{len(plan.qrxlevmin_results) - n_skip_qrxlevmin} cells thay doi, {n_skip_qrxlevmin} cells o floor (skip)",
            )

            cells = plan.cells

            # --- Buoc 11: Luu cell_params ---
            # snapshot_before_cr PHAI chay TRUOC upsert (copy rsboost_current/
            # qrxlevmin_current hien tai sang *_before_cr truoc khi bi ghi de) -
            # chuyen ra day (thay vi giua buoc 7 nhu truoc refactor) vi
            # _prepare_plan() khong duoc ghi DB (dung chung voi preview), nhung
            # thu tu tuong doi voi upsert() KHONG doi.
            await self._cell_repo.snapshot_before_cr(session.id)
            all_params: list[CellParam] = plan.rsboost_results + plan.qrxlevmin_results
            for p in all_params:
                p.cr_session_id = session.id  # calculator KHONG tu set (B3.4/B3.5)
            await self._cell_repo.upsert(all_params)
            await self._emit(session.id, 11, "Luu cell_params", 60, "success", f"Da luu {len(all_params)} cell params vao DB")

            # Phuong an B (22072026, DA DUYET) - luu CUNG buoc 11, 47 cell Nhanh A
            # (plan.affected_cells) vao cr_affected_cells, de sau nay danh gia chat
            # luong tren dung pham vi RF bi anh huong (KHAC 12 cell Nhanh B vua
            # upsert o tren - do la cell THAT SU duoc dieu chinh tham so). KHONG
            # emit SSE step rieng (van la 1 phan cua buoc 11, giu nguyen 18 buoc
            # da co, tranh vo test/FE dang dem step theo thu tu co dinh).
            #
            # Loi o day KHONG duoc lam FAIL ca CR - day la data PHU TRO cho danh
            # gia sau nay (chua co gi doc no trong luong CR that), khac 12 cell
            # cell_params vua upsert THANH CONG o tren (du lieu CORE, van tiep tuc
            # binh thuong). Chi log WARNING + tiep tuc (xac nhan lua chon voi user).
            try:
                affected_cells_data = [
                    {
                        "cell_name": c.cell_name,
                        "tram_id": extract_lnbts(c.dist_name),
                        "huong_id": c.huong_id,
                        "dist_name": c.dist_name,
                        # THEM 04/10/2026 (luat xuat phieu toi da 2/sector cua
                        # tram tat) - filter_affected() da tinh san qua ten huong.
                        "sector": c.sector,
                    }
                    for c in plan.affected_cells
                ]
                await self._affected_cells_repo.bulk_insert(session.id, affected_cells_data)
            except Exception as e:
                logger.warning(
                    "Ghi cr_affected_cells that bai - KHONG anh huong CR (chi mat "
                    "data danh gia phu tro, 12 cell cell_params da luu binh thuong)",
                    extra={"cr_session_id": session.id, "error": str(e)},
                )

            # --- Buoc 12: Build XML (merge Cell + CellParam -> XmlCellData) ---
            current_step, current_step_name, current_step_pct = 12, "Build XML", 65
            xml_cells = self._build_xml_cells(cells, all_params)
            now_utc = datetime.now(timezone.utc)
            plan_name = f"R012_NQMProactiveCC_{tram_id}_{now_utc:%Y%m%d_%H%M%S}"
            xml_content = self._xml_builder.build_xml(xml_cells, plan_name)
            await self._emit(session.id, 12, "Build XML", 65, "success", f"Build XML: {len(xml_cells)} managedObject blocks")

            # --- Buoc 13-16: Upload + Import + Provision + Verify (gop 1 SSE) ---
            current_step, current_step_name, current_step_pct = BUOC_SSH_BAT_DAU, "SSH: Upload+Import+Provision", 70
            # SUA 27092026 (Giai doan 1 buoc 2) - KHONG con goi get_ma_tinh()
            # o day (ham VAN CON, dung rieng cho dashboard GET /stations) -
            # OSS DA duoc chon SAN theo TUNG CELL trong _prepare_plan() (xem
            # _chon_oss_va_loc_cells()), luu trong plan.oss_instance.
            if plan.oss_instance is None:
                # Tat ca cell lan can da bi loai khoi dinh tuyen OSS (ten sai
                # mau/OSS chua cau hinh - xem cell_ngoai_pham_vi_chi_tiet) nen
                # KHONG con cell nao de gui SSH. Raise ro rang thay vi goi
                # submit_cr(None) se crash AttributeError kho hieu.
                # 23/10/2026: noi kem cac nguyen nhan cau hinh NA (khong trung lap)
                # de loi CR tu noi NA nao can sua.
                ly_do_na = sorted({d["chi_tiet"] for d in plan.cell_ngoai_pham_vi_chi_tiet if d.get("chi_tiet")})
                raise SshConnectionError(
                    "Khong co OSS nao duoc chon cho CR nay - tat ca cell lan can "
                    "da bi loai khoi dinh tuyen (xem cell_ngoai_pham_vi_chi_tiet: "
                    "TEN_CELL_SAI_MAU/OSS_CHUA_CAU_HINH)"
                    + (f". {'; '.join(ly_do_na)}" if ly_do_na else "")
                )
            backup_name = f"R012_backup_{tram_id}_{now_utc:%Y%m%d_%H%M%S}"
            await self._emit(session.id, 13, "SSH: Upload+Import+Provision", 70, "running", "Dang upload+Import+Provision len NetAct...")
            current_step_pct = 90  # tu day tro di, loi la ket qua SSH that bai (pct 90), khong phai luc bat dau (70)
            # Heartbeat chay SONG SONG voi submit_cr() (khong await tuan tu -
            # asyncio.create_task de khong block/lam cham SSH that) - PHAI
            # cancel() + await lai trong finally du submit_cr() thanh cong hay
            # loi, tranh task heartbeat song vo thoi han sau khi buoc 13 xong.
            heartbeat_task = asyncio.create_task(self._emit_heartbeat_loop(session.id))
            try:
                kq_netact = await self._netact_gw.submit_cr(xml_content, plan_name, backup_name, plan.oss_instance)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass  # huy chu dong, khong phai loi that
            # SUA 18082026 - TACH thong bao Import vs Provision. Truoc day 2
            # buoc dung CHUNG 1 cau "Import/Provision that bai" nen nguoi van
            # hanh khong biet hong o dau, trong khi 2 tinh huong rat khac nhau:
            # Import hong -> submit_cr DUNG LUON, Provision CHUA CHAY, thiet bi
            # KHONG doi gi. Provision hong -> plan da vao NetAct roi.
            if not kq_netact["ok"]:
                if kq_netact["buoc_loi"] == "import":
                    thong_bao = f"Import plan vao NetAct that bai - CHUA chay Provision, thiet bi KHONG doi"
                else:
                    thong_bao = f"Provision that bai tren NetAct: {kq_netact['tom_tat']}"
                # oss=oss_da_chon (02/10/2026): OSS DA duoc dung that (submit_cr()
                # vua duoc goi voi no) du ket qua la that bai o Import/Provision -
                # KHAC "tu choi TRUOC khi chon OSS", van phai ghi lai de tra lich su.
                await self._fail(session, 13, "SSH: Upload+Import+Provision", 90, thong_bao, oss=oss_da_chon)
                return session

            # SUA 18082026 - ghi cr_log buoc 13 CHI TIET THEO TUNG DN. Truoc day
            # chi co 1 dong "thanh cong", khong biet tram nao da doi tham so.
            await self._emit(
                session.id, 16, "Parse ket qua SSH + Verify", 90, "success", kq_netact["tom_tat"]
            )

            # --- Buoc 17: Cap nhat cr_session DONE ---
            # PARTIAL_SUCCESS khi CHI MOT SO DN provision duoc - KHONG bao DONE
            # (tram hong bi giau) cung KHONG bao FAILED (3 tram kia DA doi that).
            session.status = CrStatus(kq_netact["trang_thai"])
            # ghi TY LE CELL cung luc voi status (B1 - truoc day dem theo DN).
            # Truoc do thong tin
            # nay chi nam trong cr_log buoc 13 dang chu -> khong truy van/loc/
            # sap xep duoc. None khi provision chua chay xong (khac 0/0).
            session.so_cell_thanh_cong = kq_netact["so_cell_thanh_cong"]
            session.so_cell_tong = kq_netact["so_cell_tong"]
            # A6 - duong dan log NetAct de sau nay doc lai qua
            # GET /sessions/{id}/log-netact. .get() chu khong ["..."]: adapter cu
            # (hoac test stub) khong co khoa nay, KeyError o buoc 17 se lam hong
            # ca CR da chay THANH CONG chi vi thieu 1 duong dan log
            session.duong_dan_log = kq_netact.get("duong_dan_log")
            session.plan_name = plan_name
            session.backup_plan_name = backup_name
            session.xml_filename = f"{plan_name}.xml"
            session.executed_at = now_utc
            # oss_instance_id/noc (02/10/2026) - CR chay toi day nghia la OSS
            # da duoc dung THAT (plan.oss_instance khong None - da guard o
            # tren truoc buoc 13), ghi lai de tra lich su "session nay chay
            # tren NetAct/NOC nao" (xem models/cr_session.py).
            session.oss_instance_id = oss_da_chon.instance_id if oss_da_chon else None
            session.noc = oss_da_chon.noc if oss_da_chon else None
            session = await self._session_repo.update(session)
            await self._emit(session.id, 17, "Cap nhat cr_session Status", 95, "success", f"CR session #{session.id} da hoan thanh")

            # --- Buoc 18: Snapshot QoS baseline (KHONG fail CR neu loi) ---
            try:
                # cell_names lay tu TOAN BO cells da filter (buoc 4-6), khong
                # chi rieng cells thuc su thay doi - baseline QoS can cho ca
                # tram, khong chi cells co trong xml_cells (chua ro chuan xac
                # tu docs, quyet dinh hop ly nhat co the voi thong tin hien co)
                cell_names = [c.cell_name for c in cells]
                to_dt = now_utc - timedelta(days=1)
                from_dt = to_dt - timedelta(days=6)
                qos_data = await self._network_gw.get_qos_metrics(cell_names, from_dt, to_dt)
                # TODO: chua co IQosSnapshotRepo/port de luu qos_snapshot - bo
                # qua persist o C2.1 nay (xac nhan voi user 12072026), chi goi
                # CTS lay data roi bo — lam task rieng sau.
                await self._emit(session.id, 18, "Snapshot QoS baseline", 100, "success", "CR hoan thanh. Danh gia sau 21 ngay.", done=True)
                logger.info("QoS baseline snapshot", extra={"session_id": session.id, "days": len(qos_data)})
            except DomainError as e:
                # Buoc 18 KHONG fail CR (WORKFLOW.md SS8: "Step 18 fail -> KHONG
                # fail CR session")
                logger.warning("CTS snapshot fail, KHONG fail CR", extra={"session_id": session.id, "error": str(e)})
                await self._emit(session.id, 18, "Snapshot QoS baseline", 100, "success", "CR hoan thanh (QoS baseline se lay lai sau).", done=True)

            return session

        except DomainError as e:
            # current_step/current_step_name/current_step_pct phan anh dung
            # buoc dang chay tai thoi diem loi (xem khoi tao + cap nhat truoc
            # buoc 3/12/13 o tren) - KHONG hardcode step=0 chung chung.
            # oss=oss_da_chon (02/10/2026): van None neu loi xay ra TRUOC khi
            # _prepare_plan() tra ve (vd CrNhieuOssError - khong chon duoc 1
            # OSS cu the; hoac CdsApiError o buoc 3) - dung y "tu choi truoc
            # khi chon OSS -> NULL". Neu loi xay ra SAU do (vd buoc 12 XML)
            # thi oss_da_chon da duoc gan tu plan.oss_instance, van ghi lai.
            await self._fail(
                session, current_step, current_step_name, current_step_pct, str(e),
                oss=oss_da_chon, error_code=e.error_code,
            )
            return session
        except Exception as e:
            # C1.4-fix bo sung (20072026): BAT Exception CHUNG, khong chi
            # DomainError - neu khong, loi ha tang ngoai du kien (vd
            # ConnectionError/TimeoutError tu SSH library, KeyError/TypeError
            # do bug code chua luong truoc) se LOT THANG ra ngoai run_cr_flow(),
            # vi ham nay gio chay qua BackgroundTasks (khong con ai await/bat
            # lai o router nua) - khien session KET VINH VIEN o RUNNING. Dung
            # bug that da phat hien: session #197 (tram 111138) ket RUNNING
            # hon 4 ngay vi 1 loi khong phai DomainError xay ra giua chung,
            # khong bao gio duoc _fail() xu ly. logger.exception() ghi FULL
            # traceback vao server log de debug sau - KHONG day traceback tho
            # ra SSE/FE (chi str(e) ngan gon), tranh lo chi tiet noi bo he
            # thong ra ngoai qua kenh nguoi dùng nhin thay.
            logger.exception(
                "run_cr_flow() gap loi ha tang ngoai du kien (khong phai DomainError) - "
                "van phai set FAILED, khong duoc de session ket RUNNING",
                extra={"session_id": session.id, "step": current_step},
            )
            await self._fail(
                session, current_step, current_step_name, current_step_pct, f"Loi he thong ngoai du kien: {e}",
                oss=oss_da_chon,
            )
            return session

    def _build_xml_cells(self, cells: list[Cell], all_params: list[CellParam]) -> list[XmlCellData]:
        # Merge Cell (dist_name) + CellParam (action_type/rsboost_new/
        # qrxlevmin_new) theo cell_name - loai bo "skip" truoc khi tao
        # XmlCellData (WORKFLOW.md buoc 12; xac nhan voi user 12072026:
        # dist_name la field dung, khong phai cell_id - xem chu y dau file)
        params_by_name = {p.cell_name: p for p in all_params}
        xml_cells: list[XmlCellData] = []
        for cell in cells:
            param = params_by_name.get(cell.cell_name)
            if param is None or param.action_type == "skip":
                continue
            xml_cells.append(
                XmlCellData(
                    cell_id=cell.dist_name,
                    action_type=param.action_type,
                    rsboost_new=param.rsboost_new,
                    qrxlevmin_new=param.qrxlevmin_new,
                )
            )
        return xml_cells

    async def _emit(
        self, session_id: int, step: int, step_name: str, pct: int, status: str, msg: str, done: bool = False
    ) -> None:
        # WORKFLOW.md SS6 - SSE event format day du
        await self._event_bus.publish(
            session_id,
            {
                "step": step,
                "step_name": step_name,
                "pct": pct,
                "status": status,
                "msg": msg,
                "detail": {},
                "done": done,
                "error": None,
            },
        )
        # 22072026 - ghi DB SONG SONG voi SSE (khong thay the) - xem
        # _log_step() cho ly do day du.
        await self._log_step(session_id, step, step_name, status, msg, pct)

    async def _log_step(
        self, session_id: int, step: int, step_name: str, status: str, msg: str | None, pct: int | None,
        ma_loi: str | None = None,
    ) -> None:
        # Persist tung buoc CR vao cr_log de xem lai duoc SAU KHI CR xong (SSE
        # chi real-time qua CrEventBus trong RAM, dong tab la mat het lich su
        # - GET /sessions/{id} truoc gio cr_logs[] LUON RONG vi chua co repo).
        # Loi ghi log KHONG duoc lam FAIL CR - day la data PHU TRO de xem lai,
        # khong phai buoc CORE cua flow (giong cach da lam voi cr_affected_cells,
        # 22072026) - chi log warning + tiep tuc, KHONG raise/propagate.
        try:
            await self._cr_log_repo.insert(session_id, step, step_name, status, msg, pct, ma_loi=ma_loi)
        except Exception as e:
            logger.warning(
                "Ghi cr_log that bai - KHONG anh huong CR (chi mat 1 dong log de xem lai)",
                extra={"cr_session_id": session_id, "step": step, "error": str(e)},
            )

    async def _emit_heartbeat_loop(self, session_id: int) -> None:
        # C1.4-fix5 (20072026) - vong lap chay NEN song song submit_cr(), publish
        # 1 event heartbeat moi _HEARTBEAT_INTERVAL_SECONDS (30s) cho toi khi bi
        # cancel() (submit_cr() da xong, xem noi goi o buoc 13). Cau truc event
        # CHI co "type"/"msg" - KHAC HOAN TOAN schema cua _emit()/_fail() (khong
        # co step/pct/status/done/error) de FE de dang phan biet va bo qua,
        # khong hien nham thanh 1 dong log tien trinh binh thuong.
        elapsed = 0
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
            elapsed += _HEARTBEAT_INTERVAL_SECONDS
            await self._event_bus.publish(
                session_id,
                {"type": "heartbeat", "msg": f"Dang xu ly... ({elapsed}s)"},
            )

    async def _fail(
        self, session: CrSession, step: int, step_name: str, pct: int, error_msg: str,
        oss: OssInstance | None = None, error_code: str | None = None,
    ) -> None:
        # WORKFLOW.md SS8 - loi bat ky buoc nao -> SSE failed + cr_session=FAILED
        # (hoac KHONG_CHAY, THEM 16/10/2026, yeu cau truc tiep user "TRANG THAI
        # KHONG_CHAY") - PHAN BIET theo buoc dung: < BUOC_SSH_BAT_DAU (13) la
        # chua tung gui lenh len NetAct -> KHONG_CHAY; >= 13 la DA gui/dang gui
        # SSH that (ke ca khi that bai hoan toan) -> FAILED nhu cu (xem dinh
        # nghia BUOC_SSH_BAT_DAU dau file).
        session.status = CrStatus.KHONG_CHAY if step < BUOC_SSH_BAT_DAU else CrStatus.FAILED
        # ma_loi (16/10/2026) - error_code cua DomainError gay loi (vd
        # "KHONG_CO_DU_LIEU_HO") - None cho loi ha tang ngoai du kien (khong
        # phai DomainError, khong co error_code structured de ghi) - xem
        # except Exception o run_cr_flow().
        session.ma_loi = error_code
        # oss (02/10/2026) - CHI ghi khi caller DA xac dinh duoc OSS truoc khi
        # loi xay ra (vd Import/Provision that bai SAU khi da gui SSH that -
        # xem run_cr_flow()). Mac dinh None: giu nguyen gia tri cu cua session
        # (thuong cung la None, vi session moi tao chua tung co OSS) - "CR bi
        # tu choi TRUOC khi chon OSS -> de NULL" (yeu cau user).
        if oss is not None:
            session.oss_instance_id = oss.instance_id
            session.noc = oss.noc
        await self._session_repo.update(session)
        await self._event_bus.publish(
            session.id,
            {
                "step": step,
                "step_name": step_name,
                "pct": pct,
                "status": "failed",
                "msg": error_msg,
                "detail": {},
                "done": True,
                "error": error_msg,
            },
        )
        # 22072026 - ghi DB SONG SONG voi SSE, GIONG _emit() (xem _log_step()).
        # _fail() KHONG goi qua _emit() (cau truc "done"/"error" khac nhau va
        # session.status can update TRUOC khi publish) nen goi rieng o day.
        await self._log_step(session.id, step, step_name, "failed", error_msg, pct, ma_loi=error_code)
