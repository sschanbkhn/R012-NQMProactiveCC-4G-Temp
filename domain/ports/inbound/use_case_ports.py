"""
ITriggerCrUseCase, IEvaluateCrUseCase, IGetSessionsUseCase, IGetSessionDetailUseCase,
ISyncEnodebUseCase, ISyncCellParamsUseCase, IGetQosSparklineUseCase (them o C1.7,
13072026, Nhom 2).
IGetEvaluationChartUseCase + EvaluationChart DA XOA (20082026) - snapshot gio
luu PER-CELL nen 2 mang do se phinh 15 lan, va FE da khong doc tu 23/07.
Tu: ARCHITECTURE.md Section 3.4; TASK_LIST.md B2.9
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from domain.entities.cr_session import CrSession
from domain.ports.outbound.repo_ports import Page, SessionFilter


@dataclass
class CrSessionDetail:
    # Dien field o C2.4 (13072026, Nhom 2) - khop API_CONTRACTS.md GET /sessions/{id}
    # (dong 656-709). qoe_snapshots/qos_snapshots DA XOA khoi response (20082026)
    # (Nhom 4). cell_params la CellParam entity (B2.8, tai su dung) cua CHINH
    # session nay (ICellParamsRepo.get_by_cr_session_id(), moi them C2.4).
    # cr_logs SUA 22072026 (xac nhan voi user) - THAT su doc tu bang cr_log qua
    # ICrLogRepo (truoc gio LUON [] du bang da co san tu B4.4, chi thieu repo).
    session: CrSession
    cell_params: list  # list[CellParam] - khong import them de tranh vong lap, xem application/
    cr_logs: list  # [{"step","step_name","status","message","pct","created_at"}], sort created_at tang dan
    # affected_cells them 22072026 (Phuong an B, DA DUYET) - 47 cell Nhanh A
    # (ICrAffectedCellsRepo.get_by_cr_session_id(), dang [{"cell_name","tram_id",
    # "huong_id"}]) BEN CANH cell_params (12 cell Nhanh B) - KHONG thay the,
    # KHONG doi hanh vi cell_params cu (FE dang dung).
    affected_cells: list


@dataclass
class EvaluationResult:
    # Dien field o C2.2 (13072026, Nhom 2) - khop BUSINESS_RULES.md Section 8
    # (PASS|FAIL|INSUFFICIENT_DATA doc lap cho qoe_result/qos_result).
    session_id: int
    qoe_result: str
    qos_result: str
    qoe_before: float | None
    qoe_after: float | None
    qos_before: float | None
    qos_after: float | None


@dataclass
class XuatPhieuResult:
    # Them KHOI 3a/5 (XuatPhieuUseCase, yeu cau truc tiep user) - ket qua xuat
    # phieu SaveCellClm cho 1 cell.
    #
    # SUA (yeu cau truc tiep user, doi tieu chi QoS dat/khong dat) - cr_phieu_id
    # gio la int|None: None khi cell DAT tieu chi QoS moi (chenh lech TB
    # truoc-sau <= 0.2) - KHONG tao dong cr_phieu nao ca (BUOC 3: "cell duoc
    # xuat phieu = cell KHONG DAT"), khac voi truoc day (cr_phieu_id luon co
    # gia tri vi moi lan goi execute() DEU tao/tim duoc 1 dong).
    cr_phieu_id: int | None
    # PENDING (chua kip goi gateway - khong nen xay ra khi tra ve binh thuong)/
    # SUCCESS/FAILED/DAT_KHONG_XUAT (cell dat tieu chi QoS moi, KHONG xuat
    # phieu - xem application/xuat_phieu_use_case.py).
    #
    # KHONG_XUAT_VUOT_GIOI_HAN / KHONG_XUAT_HET_LUOT_THU (V4) KHONG bao gio
    # xuat hien o day: do la trang_thai cua DONG cr_phieu do JOB ghi cho cell
    # no khong dinh vao, con XuatPhieuResult luon la ket qua cua 1 lan THUC SU
    # goi execute() cho 1 cell.
    trang_thai: str
    phieu_id: str | None  # id phieu tren TTS, chi co khi trang_thai=SUCCESS
    # True neu BUOC 1 (check trung) phat hien phieu SUCCESS co san - KHONG goi
    # gateway lai, cac field con lai la cua PHIEU CU (khong phai lan goi nay).
    already_exists: bool
    # Them KHOI 4a/5 (yeu cau truc tiep user) - {isError, code, message, data,
    # status_code} tho tu CTS - router (api/routers/phieu.py) echo nguyen ra API
    # response de FE hien DUNG message loi tu CTS ("khong nuot loi"). None khi
    # chua goi toi gateway (DAT_KHONG_XUAT / already_exists).
    #
    # status_code them o V3a - thieu no thi doc lai response_body khong phan
    # biet duoc "CTS tra 400" voi "CTS tra 200 kem isError".
    cts_response: dict | None = None
    # Them KHOI 4a/5 - CHI co gia tri khi da POST that THANH CONG/CTS tra ve
    # nhung sau do ghi cr_phieu vao DB that bai (BUOC 2 dac ta) - router PHAI
    # van tra phieu_id that cho FE, kem canh bao nay (KHONG duoc lam nhu khong
    # co gi xay ra, nhung cung KHONG duoc mat ket qua POST that).
    db_save_warning: str | None = None
    # Them 04092026 - CHI co gia tri khi trang_thai=DAT_KHONG_XUAT. Cau chu neu
    # CA HAI so lam cell dat (TB sau >= muc toi thieu VA chenh lech <= 0.5).
    #
    # VI SAO dat cau o USE CASE chu khong o router: router khong biet luat, no
    # chi echo. Truoc day router hardcode "chenh lech TB truoc-sau <= 0.2" cho
    # MOI truong hop dat - sai voi cell dat nho ve thu hai (vd chenh 0.50 nhung
    # TB sau 4.33 >= 4.0), lam nguoi doc tuong he thong mau thuan.
    ly_do_dat: str | None = None


@dataclass
class SyncResult:
    # Dien field o C2.5/C2.6 (13072026, Nhom 2) - ket qua noi bo cua background
    # task (POST /jobs/sync-* tra 202 ngay, KHONG echo SyncResult ra HTTP response
    # - chi dung de log/debug trong background task, xem api/routers/jobs.py).
    total_synced: int


class ITriggerCrUseCase(ABC):
    @abstractmethod
    async def execute(self, tram_id: str, tram_name: str, action: str) -> CrSession: ...


class IEvaluateCrUseCase(ABC):
    @abstractmethod
    async def execute(self, session_id: int) -> EvaluationResult: ...


class IGetSessionsUseCase(ABC):
    # SUA 16082026 (man hinh tien trinh): tra Page[SessionTienTrinh] chu khong
    # con Page[CrSession] - moi dong gio kem 3 gia tri TINH SAN (ngay du kien
    # xuat phieu, con bao nhieu ngay, buoc hien tai) de FE khong phai biet quy
    # tac nghiep vu nao. Khong ghi kieu cu the o day vi SessionTienTrinh dinh
    # nghia trong application/ - domain/ KHONG duoc import application/
    # (ARCHITECTURE.md SS9).
    @abstractmethod
    async def execute(self, filters: SessionFilter, bay_gio: datetime | None = None) -> Page: ...


class IGetSessionDetailUseCase(ABC):
    @abstractmethod
    async def execute(self, session_id: int) -> CrSessionDetail: ...


class ISyncEnodebUseCase(ABC):
    # tram_id them o C2.5 (13072026, Nhom 2, theo yeu cau user) - None (mac
    # dinh) = sync toan bo (~58k dong, dung cho n8n job hang ngay); truyen
    # tram_id = chi sync 1 tram (test nhanh, dung y logic --tram-id cua script
    # thu cong adapters/http/sync_tram_from_enodeb.py).
    @abstractmethod
    async def execute(self, tram_id: str | None = None) -> SyncResult: ...


class ISyncCellParamsUseCase(ABC):
    # Bo sung so voi TASK_LIST.md B2.9 goc (chi liet 5 interface, thieu cai nay).
    # Ly do: API_CONTRACTS.md dong 705-708 liet ke sync-rims/sync-netact/sync-status/
    # evaluate-cr la 4 job endpoint ngang hang, cung goi qua 1 router jobs.py
    # (ARCHITECTURE.md dong 295). sync-netact = sync_cell_params_use_case
    # (BUSINESS_RULES.md SS10.2) — cung duoc router goi truc tiep giong sync-rims
    # (= sync_enodeb_use_case, da co ISyncEnodebUseCase) nen phai co port tuong tu,
    # khong co ly do ky thuat de doi xu khac nhau.
    #
    # file_path them o C2.6 (13072026, Nhom 2) - TU GIA DINH: khong co dinh
    # nghia HTTP contract nao trong docs cho input cua job nay (BUSINESS_RULES.md
    # SS10.2 chi noi "Nguon: NetAct (SSH export hoac API - can xac nhan method)",
    # KHONG noi ro co file upload qua HTTP hay khong). Chon nhan duong dan file
    # CSV da co san TREN SERVER (khong phai multipart upload) - xem chu y day du
    # trong application/sync_cell_params_use_case.py.
    @abstractmethod
    async def execute(self, file_path: str) -> SyncResult: ...


class IGetQosSparklineUseCase(ABC):
    # Bo sung o C1.7/C2 (13072026, Nhom 2, xac nhan voi user) - khong co trong
    # TASK_LIST.md B2.9 goc (chi liet 5 interface). GET /qos/{cell_name} (Widget
    # F33, BUSINESS_RULES.md Section 9) can 1 lop use case mong boc INetworkGateway.
    # get_qos_metrics() - KHONG goi thang gateway tu router (pha vo Hexagonal
    # Architecture SS9 dependency rule: "api/ KHONG import adapters/ truc tiep",
    # va ARCHITECTURE.md SS2 so do: API -> Inbound Port -> Application -> Outbound
    # Port, khong duoc bo qua Application layer).
    #
    # days them sau (21072026) - endpoint ban dau hardcode 48h chi phuc vu Widget
    # F33, nhung chart QoS 7 ngay trong preview CR can nhieu diem hon. Tai dung
    # cung use case, khong tao class moi - logic gateway giong het nhau, chi khac
    # do rong window.
    #
    # from_dt/to_dt them Gap 1 (22072026) - lay QoS quanh 1 ngay CR TRONG QUA
    # KHU (days luon neo cung to_dt=hom qua, khong lam duoc). Uu tien ca 2 neu
    # co, khong thi tinh tu days (KHONG doi hanh vi mac dinh).
    @abstractmethod
    async def execute(
        self,
        cell_name: str,
        days: int = 7,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict]: ...


class IGetQoeSparklineUseCase(ABC):
    # Them 16082026 - doi xung hoan toan voi IGetQosSparklineUseCase o tren,
    # chi khac nguon (ISocGateway.get_qoe thay vi INetworkGateway.get_qos_metrics)
    # va key gia tri ("qoe" thay vi "qos"). Tach interface RIENG chu khong dung
    # chung 1 interface cho 2 nguon: 2 gateway khac nhau, va mac dinh cua so
    # cung khac (CEM tre 2 ngay, CTS tre 1 ngay).
    @abstractmethod
    async def execute(
        self,
        cell_name: str,
        days: int = 7,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict]: ...


class IXuatPhieuUseCase(ABC):
    # Them KHOI 3a/5 (yeu cau truc tiep user) - ghep 28 field SaveCellClmPayload
    # tu nguon DA CO (tram + danh gia QoS + mac dinh) roi goi ISaveCellClmGateway
    # (KHOI 1/5).
    #
    # V2 (12/08, yeu cau truc tiep user) - da BO tham so dry_run: MOI lan goi
    # deu POST THAT len TTS. Khong con duong "chay thu" nao trong use case nay.
    @abstractmethod
    async def execute(self, cr_session_id: int, cell_name: str) -> XuatPhieuResult: ...

