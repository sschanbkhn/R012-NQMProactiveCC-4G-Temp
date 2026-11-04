"""
ICrSessionRepo, ICellParamsRepo, IEnodebRepo.
Tu: ARCHITECTURE.md Section 3.4; TASK_LIST.md B2.8
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, TypeVar

from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrSession
from domain.entities.tram import Tram


from domain.value_objects.rsboost_level import RsboostLevel
from domain.value_objects.qrxlevmin import Qrxlevmin

T = TypeVar("T")


@dataclass
class SessionFilter:
    # Bo sung field o C2.3 (13072026, Nhom 2) - khop API_CONTRACTS.md GET /sessions
    # query params (dong 623-631): q/status/from/to/page/size.
    q: str | None = None  # tim tram_id HOAC tram_name (ILIKE, join tram)
    status: str | None = None  # 1 gia tri CrStatus - doc KHONG mo ta multi-status
    date_from: datetime | None = None  # loc created_at >= date_from
    date_to: datetime | None = None  # loc created_at <= date_to
    # page/size = None -> KHONG phan trang (fetch tat ca) - dung cho
    # EvaluateCrUseCase.execute_all_pending() (C2.6) can quet toan bo session
    # DONE/EVAL_PENDING, khac muc dich UI list co phan trang that (GET /sessions
    # dat page=1/size=20 mac dinh o tang router, khong phai o day).
    page: int | None = None
    size: int | None = None
    # sort_by/order them 22072026 (sort server-side, xac nhan voi user) - FE
    # truoc gio sort client-side CHI tren trang hien tai (sai pham vi, gay
    # hieu nham vd "10 session moi nhat" thuc ra chi la 10 session moi nhat
    # CUA TRANG 1 da fetch). sort_by=None -> giu nguyen thu tu mac dinh
    # created_at desc (KHONG regression). Whitelist da validate o router
    # (Literal type, FastAPI tu tra 422) - du lieu toi day la DA hop le, repo
    # van tu whitelist lai lan nua (an toan 2 lop, xem
    # CrSessionRepo._session_sort_column()).
    sort_by: str | None = None
    order: str = "desc"

    # Them 16082026 (man hinh theo doi tien trinh). CA HAI phai loc TRONG SQL
    # chu khong phai loc list sau khi fetch: total va phan trang se sai neu loc
    # o tang Python (total dem ca ban ghi da bi loai).
    #
    # buoc: 1|2|4 - khop buoc_hien_tai (xem tinh_buoc_hien_tai() trong
    # application/get_sessions_use_case.py). KHONG co buoc 3.
    buoc: int | None = None
    # qua_han: chua xuat phieu VA da qua ngay du kien xuat.
    #
    # VI SAO CAN RIENG 1 BO LOC: PA A (application/xuat_phieu_use_case.py
    # _lay_session_du_dieu_kien) quet DUNG 1 ngay - dieu kien la
    # "ngay CR == hom nay - XUAT_PHIEU_AFTER_DAYS", KHONG phai "<=". Job lo 1
    # ngay (may chet, misfire qua 30 phut) thi session cua ngay do KHONG BAO GIO
    # duoc quet lai - mat vinh vien, khong co co che tu phuc hoi nao. Day la cho
    # DUY NHAT trong toan he thong phat hien ra truong hop do de nguoi van hanh
    # xuat tay.
    #
    # 2 FIELD cho 1 y dinh, CO CHU DICH:
    #   qua_han            - Y DINH tu API (router dien tu query param).
    #   qua_han_truoc_ngay - NGAY MOC da tinh san, do GetSessionsUseCase dien.
    # Repo CHI doc field thu 2. Tach nhu vay vi hang so XUAT_PHIEU_AFTER_DAYS va
    # phep quy doi GMT+7 la nghiep vu, khong duoc nam trong adapters/
    # (ARCHITECTURE.md SS9: adapters KHONG import application).
    qua_han: bool = False
    qua_han_truoc_ngay: date | None = None


@dataclass
class Page(Generic[T]):
    # Placeholder toi gian — ARCHITECTURE.md dong 163/191 tham chieu Page[CrSession]
    # nhung khong dinh nghia field cu the. Gia dinh hop ly toi thieu cho pagination
    # (items + total), CHUA xac nhan voi user co can page/size tren response khong.
    # TODO: xac nhan lai cau truc khi lam Part D (Dashboard), IGetSessionsUseCase.
    items: list[T]
    total: int


class ICrSessionRepo(ABC):
    @abstractmethod
    async def create(self, session: CrSession) -> CrSession: ...

    @abstractmethod
    async def update(self, session: CrSession) -> CrSession: ...

    @abstractmethod
    async def get_by_id(self, id: int) -> CrSession | None: ...

    @abstractmethod
    async def get_by_tram_id(self, tram_id: str) -> list[CrSession]: ...

    @abstractmethod
    async def list(self, filters: SessionFilter) -> Page[CrSession]: ...

    @abstractmethod
    async def ghi_ket_qua_xuat_phieu(
        self, id: int, xuat_phieu_at: datetime, xuat_phieu_ket_qua: str
    ) -> None:
        """Ghi 2 cot theo doi tien trinh sau khi job quet XONG 1 session (14/08).

        VI SAO METHOD RIENG, KHONG dung update(): update() nhan ca 1 domain
        entity CrSession va ghi de ~13 cot. Nhung 2 cot nay KHONG co trong domain
        entity (domain/entities/cr_session.py) - chung la du lieu VAN HANH cua
        job, khong phai khai niem nghiep vu cua CR. Nhoi chung vao entity chi de
        dung lai update() se buoc moi caller khac (TriggerCrUseCase,
        EvaluateCrUseCase) phai mang theo 2 field khong lien quan, va rui ro ghi
        de nham gia tri cua nhau khi 2 use case cung cham 1 session.

        Cung ly do da chon danh_dau_khong_xuat() cho ICrPhieuRepo (V4): sua DUNG
        thu can sua, khong dong vao cot khac.

        xuat_phieu_ket_qua: DA_XUAT / KHONG_CAN_XUAT / LOI - xem hang so
        KET_QUA_* trong application/xuat_phieu_use_case.py."""
        ...


    @abstractmethod
    async def xoa_cascade(self, id: int) -> dict:
        """Xoa 1 session + moi dong con. Tra {ten_bang: so_dong}. Them 20082026.

        Repo KHONG kiem status - luat "chi xoa duoc FAILED" nam o
        XoaSessionUseCase. Xem adapters/postgres/cr_session_repo.py ve ly do
        gom ca cascade vao 1 method (1 transaction)."""
        ...

    @abstractmethod
    async def dem_session_rollback_tu(self, id: int) -> int:
        """So session KHAC dang tro rollback_of_id -> session nay (them 20082026)."""
        ...

class ICellParamsRepo(ABC):
    @abstractmethod
    async def upsert(self, params: list[CellParam]) -> None: ...

    @abstractmethod
    async def get_by_tram_id(self, tram_id: str) -> list[CellParam]: ...

    # Dung cho dashboard xem cell_params theo 1 tram vat ly cu the (Part D,
    # chua lam) — GIU NGUYEN nghia nay, KHONG doi (xac nhan voi user 12072026).

    @abstractmethod
    async def get_by_cell_names(self, cell_names: list[str]) -> list[CellParam]: ...

    # Bo sung o C2.1 (12072026, xac nhan voi user, sau khi phat hien bug that
    # trong TriggerCrUseCase buoc 7/9): cell lan gieng cua 1 CR thuoc NHIEU
    # tram_id VAT LY khac nhau (VD tram 110548 bi shutdown nhung cell lan gieng
    # thuoc MRBTS 115750/114820/114848...) — get_by_tram_id(tram_id_cua_CR) LUON
    # tra ve rong cho cac cell nay, khong bao gio dung duoc cho flow trigger CR.
    # get_by_cell_names() loc THANG theo danh sach cell_name (khong loc theo
    # tram_id) — dung cho TriggerCrUseCase, KHONG lien quan/thay the
    # get_by_tram_id() (dashboard).

    @abstractmethod
    async def get_by_cr_session_id(self, session_id: int) -> list[CellParam]: ...

    # Bo sung o C2.4/C2.6 (13072026, Nhom 2) - GET /sessions/{id} (cell_params cua
    # CHINH session do) va EvaluateCrUseCase (can danh sach cell_name de goi SOC/CTS)
    # deu can loc theo cr_session_id truc tiep tren cot cell_params.cr_session_id -
    # KHAC get_by_tram_id() (dashboard, tram vat ly) va get_by_cell_names() (dung
    # trong TriggerCrUseCase khi CHUA co session_id de loc, C2.1) - khong lien quan.

    @abstractmethod
    async def snapshot_before_cr(self, session_id: int) -> None: ...

    # WORKFLOW.md buoc 7 dong 129 — copy rsboost_current/qrxlevmin_current sang
    # *_before_cr truc tiep trong SQL (adapter B5.3), khong can truyen CellParam
    # object. Business rule TASK_LIST.md B5.3 dong 148: sync-netact KHONG ghi de
    # *_before_cr neu cr_session_id da co — adapter tu doc field nay tren DB row.


class IEnodebRepo(ABC):
    @abstractmethod
    async def upsert_many(self, records: list[dict]) -> int: ...

    # input van la list[dict] (raw), khong phai list[Tram] — nhat quan voi B2.7:
    # nhan thang output tu INetworkGateway.get_enodeb_list() (cung list[dict]),
    # can du field DB (ma_tinh, ma_csht, ten_thiet_bi...) ma Tram domain entity
    # (5 field, B2.4) khong co cho chua.

    @abstractmethod
    async def find(self, q: str) -> list[Tram]: ...

    @abstractmethod
    async def get_by_tram_ids(self, tram_ids: list[str]) -> list[Tram]: ...

    # Them cho API preview (POST /cr/preview, 21072026) - can join CHINH XAC
    # tram_goc + toan bo tram lan can (MRBTS parse tu dist_name cell) lay
    # toa do trong 1 lan goi. KHAC find(q) (ILIKE, 1 tu khoa, dung cho search
    # UI) - o day can EXACT match nhieu tram_id CUNG LUC (IN clause), ILIKE
    # tren tung tram_id rieng le vua sai ngu nghia (co the khop nham chuoi
    # con) vua cham (N query rieng). tram_id khong ton tai don gian KHONG co
    # trong list tra ve (KHONG raise loi) - caller (PreviewCrUseCase) tu quyet
    # dinh dien null cho tram khong join duoc, dung yeu cau edge case xac
    # nhan tu du lieu that (0.4% MRBTS khong khop bang tram).

    @abstractmethod
    async def get_ma_tinh(self, tram_id: str) -> str: ...

    @abstractmethod
    async def find_stations(
        self,
        q: str | None,
        status: str | None,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        order: str = "desc",
        vendor: list[str] | None = None,
        khu_vuc: list[str] | None = None,
    ) -> list[dict]: ...
    # sort_by/order them 22072026 (sort server-side) - GIONG SessionFilter,
    # sort_by=None giu nguyen thu tu mac dinh cu (TramModel.tram_id tang dan,
    # xem EnodebRepo.find_stations()).
    # vendor (THEM 04/10/2026) - loc theo UPPER(TRIM(ten_thiet_bi)) IN (...).
    # list rong/None -> KHONG loc (GIU NGUYEN hanh vi cu). Gia tri hop le da
    # duoc router Literal-whitelist TRUOC khi toi day (chi NOKIA/ERICSSON/
    # HUAWEI/ZTE - xem api/routers/stations.py), repo KHONG validate lai.
    # khu_vuc (THEM 04/10/2026) - loc theo ma_tinh IN (...), tap ma_tinh suy
    # tu domain/value_objects/khu_vuc.py::ma_tinh_theo_khu_vuc(). list rong/
    # None -> KHONG loc. Gia tri hop le da duoc router Literal-whitelist
    # (chi KV1/KV2/KV3), repo KHONG validate lai.

    # Bo sung o C1.3 (13072026, xac nhan voi user) - GET /stations (API_CONTRACTS.md
    # dong 578-611) can ten_quan_ly/ma_csht (KHONG co trong Tram domain entity - B2.4
    # CO CHU Y chi giu 5 field business, xem domain/entities/tram.py) + cr_status/
    # cr_session_id (join cr_session, KHONG phai business concept cua Tram) + phan
    # trang THAT o tang DB (find() hien co tra ve TOAN BO ban ghi khop q, khong the
    # dung cho listing 58k+ dong). Tra list[dict] (giong upsert_many, khong phai
    # domain Tram) vi day la read-model rieng cho 1 API display, khong phai domain
    # logic - KHONG doi/xoa find() (van dung cho TriggerCrUseCase resolve tram_name).
    # dict fields: tram_id, tram_name, ten_quan_ly, ma_csht, longitude, latitude,
    # trang_thai, cr_status (str|None), cr_session_id (int|None).

    @abstractmethod
    async def count_stations(
        self,
        q: str | None,
        status: str | None,
        vendor: list[str] | None = None,
        khu_vuc: list[str] | None = None,
    ) -> int: ...

    # Them KHOI 3a/5 (XuatPhieuUseCase, yeu cau truc tiep user) - can 1 lan lay
    # DU tram_name/ma_tinh/ma_csht/ten_thiet_bi/ten_quan_ly cho DUNG 1 tram_id
    # de ghep SaveCellClmPayload (SiteName/ProvinceCode/BuildingCode/Vendor/
    # BuildingName). get_by_tram_ids() (co san) tra ve list[Tram] domain entity
    # (chi 5 field, THIEU 4/5 field can) - khong dung duoc. find_stations() tra
    # du field nhung la ILIKE search + phan trang, sai muc dich cho 1 lookup
    # EXACT 1 tram_id. Tra None neu tram_id khong ton tai trong bang tram (0.4%
    # MRBTS chua sync RIMS, da gap truoc o PreviewCrResponse) - XuatPhieuUseCase
    # tu quyet dinh dien "" thay vi raise loi (khong chan xuat phieu).
    @abstractmethod
    async def get_by_tram_id(self, tram_id: str) -> dict | None: ...
    # dict fields: tram_name, ma_tinh, ma_csht, ten_thiet_bi, ten_quan_ly.

    # BUOC 4b (08/10/2026, yeu cau truc tiep user) - thay CDS bang HO trong
    # xem truoc/chay CR: domain/services/ho_delaunay.py::phan_lop_delaunay()/
    # phan_loai_toa_do() can TOAN BO tram CO TOA DO (lam tap diem Delaunay +
    # phat hien TOA_DO_DUNG_CHUNG qua trung toa do) - KHONG the loc theo 1
    # tram_id le nhu get_by_tram_id(). CHI loc o DB nhung tram CO toa do (gia
    # tri rong khong dung lam diem hinh hoc duoc, loai som tai nguon re hon
    # loc lai o Python).
    @abstractmethod
    async def get_all_with_coords(self) -> list[dict]: ...
    # dict fields: tram_id, tram_name, longitude, latitude, ten_thiet_bi,
    # ma_tinh (THEM BUOC 4c, 10/10/2026 - GET /stations/map?ma_tinh=... can
    # loc theo tinh tren TAP DA tai san co toa do, khong truy van rieng lan 2).

    # Dung chung dieu kien loc voi find_stations() de tra tong so ban ghi KHOP
    # filter (khong phai tong so tren 1 trang) - can cho StationListResponse.total.

    # Bo sung o C2.1 (TriggerCrUseCase, 12072026, xac nhan voi user) - NetAct la
    # multi-vung, key theo ma_tinh (NETACT_SERVERS trong .env, KI-08), can truoc
    # khi goi INetActGateway.submit_cr(..., ma_tinh). Tach RIENG khoi find()/Tram
    # domain entity co tinh - ma_tinh la infrastructure concern (chon NetAct
    # server nao), KHONG phai business concept cua Tram (B2.4 da quyet dinh Tram
    # entity chi giu 5 field nghiep vu thuan, khong dung field DB tho). Neu
    # tram_id khong ton tai hoac ma_tinh la NULL trong DB - raise
    # TramNotFoundError (adapter tu quyet dinh, khong tra "" im lang).


class ICellInforRepo(ABC):
    @abstractmethod
    async def get_rsboost_by_neighbor_dns(
        self, neighbor_dns: list[str]
    ) -> dict[str, RsboostLevel]:
        """Key = dn cua neighbor (dist_name goc, KHONG co /LNCEL_FDD-0).
        Match bang LIKE tren dn_fdd: dn_fdd LIKE '{neighbor_dn}/LNCEL_FDD%'."""
        ...

    @abstractmethod
    async def get_qrxlevmin_by_neighbor_dns(
        self, neighbor_dns: list[str]
    ) -> dict[str, Qrxlevmin]:
        """Key = dn cua neighbor. Match bang LIKE tren dn_sib:
        dn_sib LIKE '{neighbor_dn}/SIB%'."""
        ...

    # BUOC 4b (08/10/2026, yeu cau truc tiep user) - thay CDS bang HO: tra cuu
    # cell dich tu (enb, lcr) giai ma tu ho_neighbor.target_eci (xem
    # adapters/netact/import_ho_neighbor.py) sang (dn_lncel, cell_name) THAT
    # cua cell_infor - CAN ca 2 gia tri: cell_name cho domain.chon_cell_cr()
    # (loc small cell), dn_lncel de dung LAM dist_name khi tao Cell entity
    # (RsboostCalculator/QrxlevminCalculator/XmlBuilder deu doc Cell.dist_name).
    # (enb, lcr) giai ma tu dn_lncel qua CUNG quy uoc voi import_ho_neighbor.py
    # (regex LNBTS-(\\d+)/LNCEL-(\\d+), enb=nhom LNBTS - SUA 10/10/2026, TRUOC
    # la MRBTS, SAI - xem domain/services/dist_name.py::LNBTS_LNCEL_RE va
    # docs/DEV_LOG.md ve chung minh toan hoc + du lieu that).
    @abstractmethod
    async def get_dn_map_theo_enb_lcr(self) -> dict[tuple[int, int], dict]: ...
    # Tra {(enb,lcr): {"dn_lncel": str, "cell_name": str}} cho TOAN BO
    # cell_infor (dn_lncel parse duoc qua regex LNBTS/LNCEL - dong khong parse
    # duoc bi bo qua, KHONG raise).

    @abstractmethod
    async def upsert_from_csv(self, file_path: str) -> int:
        """Boc lai logic adapters/netact/import_4G_cell_infor.py (script da chay
        that, 27763 dong) - doc CSV export Admin CLI + upsert vao cell_infor,
        tra ve so dong da upsert. Them o C2.6 (13072026, Nhom 2) - parsing file
        + SQL upsert nam TRON VEN trong adapter (adapters/postgres/
        cell_infor_repo.py), application/ KHONG duoc import adapters/netact/
        truc tiep (ARCHITECTURE.md SS9 dependency rule)."""
        ...


class IAlertRepo(ABC):
    # Them o C2.7 (13072026, Nhom 2) - ghi alert_log. Tu: DB_SCHEMA.md Section 7;
    # BUSINESS_RULES.md Section 8.3 (QOE/QOS_DEGRADED), Section 8.4 + SS13
    # (EVAL_PENDING_TOO_LONG).
    @abstractmethod
    async def create(
        self,
        cr_session_id: int,
        alert_type: str,
        severity: str,
        message: str,
        detail: dict | None = None,
    ) -> None: ...

    @abstractmethod
    async def exists_unacknowledged(self, cr_session_id: int, alert_type: str) -> bool: ...

    # Them o C2.7-fix (13072026, xac nhan voi user) - dedupe alert
    # EVAL_PENDING_TOO_LONG (job chay hang ngay, session van con qua han se
    # tao alert MOI moi ngay neu khong check). Dung LAI field is_acknowledged
    # da co san (DB_SCHEMA.md Section 7, KHONG them cot moi) - "chua xu ly" =
    # is_acknowledged=False. True = da co it nhat 1 alert CUNG loai + CUNG
    # session dang cho xu ly -> KHONG tao them ban trung.


class IQoeSnapshotRepo(ABC):
    # Them o Nhom 4 (13072026) - GET /sessions/{id} Zone E chart (BUSINESS_RULES.md
    # SS8.5: 10 diem T-2,T-1,T+0(CR),T+1..T+7). Model SQLModel da co san (B4.5,
    # models/qoe_snapshot.py) - port nay CHUA tung co (KI da ghi nhan tu C2.1/C2.2).
    #
    # SUA HAN 20082026 (yeu cau truc tiep user): luu PER-CELL, 1 dong = 1 cell
    # 1 ngay, dung nhu thiet ke goc cua bang (UNIQUE(cr_session_id, cell_name,
    # snapshot_date, period), cell_name NOT NULL).
    #
    # BAN CU (13072026 - 20082026) ghi cell_name la HANG SO sentinel
    # "__ALL_CELLS__" voi diem da trung binh CHEO cell theo ngay. Cach do CHE
    # MAT cell hong: 4 cell [5, 5, 1, 5] ra 4.0 (dat muc tot) trong khi 1 cell
    # chi duoc 1 diem (session 553 ngay 17/07, do that). 10 dong sentinel con
    # sot da bi xoa cung dot.
    #
    # period nhan 3 gia tri: "before" (T-7..T-1), "cr_day" (dung ngay T),
    # "after" (T+1..T+7).
    @abstractmethod
    async def upsert_many(self, cr_session_id: int, points: list[dict]) -> int:
        """points: [{"cell_name": str, "snapshot_date": date, "qoe_score": float,
        "period": "before"|"cr_day"|"after"}].

        cell_name BAT BUOC truyen tu ngoai (truoc 20082026 la hang so noi bo
        cua adapter). Upsert theo UNIQUE(cr_session_id, cell_name,
        snapshot_date, period): ghi de chi cap nhat cot DIEM, giu created_at."""
        ...

    @abstractmethod
    async def get_by_session_id(self, cr_session_id: int) -> list[dict]:
        """Tra ve TOAN BO diem da luu cho session nay, sort theo snapshot_date
        tang dan: [{"cell_name": str, "snapshot_date": date, "qoe_score": float,
        "period": str}].

        Neu 1 ngay khong co du lieu thi don gian KHONG co trong list nay (bo
        qua, KHONG tra None/0) - qoe_score la NOT NULL trong DB nen khong the
        luu "diem rong". (Truoc 20082026 co ghi chu "T+0 LUON khong co" - da
        het dung: cua so FETCH cua nhanh after gio bat dau tu ngay T nen T+0
        CO du lieu, luu voi period="cr_day".)"""
        ...


    @abstractmethod
    async def dem_ngay_theo_cell(self, cr_session_id: int) -> dict:
        """{(cell_name, period): so_ngay} - dem so NGAY da luu, cho lazy cache.

        Them 20082026. DEM thay vi dua vao created_at: upsert
        (on_conflict_do_update) chi cap nhat cot diem, GIU NGUYEN created_at
        nen no la "thoi diem chup LAN DAU", khong phai lan ghi gan nhat."""
        ...

class IQosSnapshotRepo(ABC):
    # Tuong tu IQoeSnapshotRepo (xem chu y day du o do) - source="cts" thay "soc".
    # Cung chuyen sang PER-CELL 20082026.
    @abstractmethod
    async def upsert_many(self, cr_session_id: int, points: list[dict]) -> int:
        """points: [{"cell_name": str, "snapshot_date": date, "qos_score": float,
        "period": "before"|"cr_day"|"after"}]. cell_name BAT BUOC truyen tu ngoai."""
        ...

    @abstractmethod
    async def get_by_session_id(self, cr_session_id: int) -> list[dict]:
        """[{"cell_name": str, "snapshot_date": date, "qos_score": float,
        "period": str}], sort theo ngay."""
        ...


    @abstractmethod
    async def dem_ngay_theo_cell(self, cr_session_id: int) -> dict:
        """{(cell_name, period): so_ngay} - dem so NGAY da luu, cho lazy cache.

        Them 20082026. DEM thay vi dua vao created_at: upsert
        (on_conflict_do_update) chi cap nhat cot diem, GIU NGUYEN created_at
        nen no la "thoi diem chup LAN DAU", khong phai lan ghi gan nhat."""
        ...

class ICrAffectedCellsRepo(ABC):
    # Them 22072026 (Phuong an B, DA DUYET thiet ke voi user) - luu 47 cell
    # "bi anh huong" (NeighborCellFilter.filter_affected(), Nhanh A) rieng
    # khoi cell_params (12 cell "chay CR", Nhanh B, ICellParamsRepo) - de sau
    # nay danh gia chat luong tren dung pham vi RF bi anh huong, khong chi 12
    # cell duoc dieu chinh tham so. Khoa theo (cr_session_id, cell_name) -
    # GIONG IQoeSnapshotRepo/IQosSnapshotRepo (KHONG dung UNIQUE(tram_id,
    # cell_name) nhu cell_params, vi 1 cell co the la affected cua NHIEU CR
    # session khac nhau theo thoi gian, cell_params chi giu duoc 1 session tai
    # 1 thoi diem - se mat lich su neu dung chung).
    @abstractmethod
    async def bulk_insert(self, cr_session_id: int, cells: list[dict]) -> int:
        """cells: [{"cell_name": str, "tram_id": str|None, "huong_id": str|None,
        "dist_name": str|None, "sector": int|None}]. "sector" them 04/10/2026
        (luat xuat phieu toi da 2/sector cua tram tat). Insert 1 lan, ON
        CONFLICT DO NOTHING (idempotent neu goi lai cung session_id - khong
        nen xay ra binh thuong, nhung an toan hon de crash)."""
        ...

    @abstractmethod
    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        """[{"cell_name": str, "tram_id": str|None, "huong_id": str|None,
        "sector": int|None, "dist_name": str|None}] ("dist_name" tra ve THEM
        04/10/2026 - cot da co san tu truoc, chi moi doc o day), KHONG sort
        theo thu tu cu the (FE tu sort neu can)."""
        ...


class ICrLogRepo(ABC):
    # Them 22072026 (xac nhan voi user) - persist tung buoc CR vao DB, SONG
    # SONG voi SSE (KHONG thay the) - SSE chi real-time, dong tab la mat het
    # lich su, GET /sessions/{id} truoc gio cr_logs[] LUON RONG vi chua co
    # port/repo nao cho bang cr_log (da ton tai san trong DB tu B4.4, chi
    # thieu tang repo). Bang cr_log DA DU cot can (step/step_name/status/
    # message/pct/created_at) - KHONG can migration.
    @abstractmethod
    async def insert(
        self,
        cr_session_id: int,
        step: int,
        step_name: str,
        status: str,
        message: str | None,
        pct: int | None,
        ma_loi: str | None = None,
    ) -> None:
        """1 dong/lan goi (khop cach _emit()/_fail() goi tuan tu tung buoc,
        KHONG bulk nhu cr_affected_cells vi khong co danh sach san co 1 lan).
        KHONG ghi heartbeat (_emit_heartbeat_loop() co cau truc event khac
        han, khong phai 1 buoc CR that su).

        ma_loi (THEM 16/10/2026, yeu cau truc tiep user) - error_code cua
        DomainError (vd "KHONG_CO_DU_LIEU_HO") - CHI co gia tri o dong
        status="failed" gay FAILED/KHONG_CHAY cho cr_session, None o moi dong
        khac (running/success)."""
        ...

    @abstractmethod
    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        """[{"step": int, "step_name": str, "status": str, "message": str|None,
        "pct": int|None, "ma_loi": str|None, "created_at": datetime}], sort
        theo created_at TANG DAN (buoc dau -> buoc cuoi - dung thu tu THOI
        GIAN THAT xay ra, khong phai sort theo "step" vi 1 step co the emit 2
        lan - vd buoc 3 running roi success, cung so step nhung khac thoi
        diem). ma_loi THEM 16/10/2026 - xem insert() o tren ve dieu kien co
        gia tri."""
        ...


class ICrPhieuRepo(ABC):
    # Them KHOI 2/5 (yeu cau truc tiep user) - luu phieu da xuat qua
    # SaveCellClm (KHOI 1/5, adapters/http/save_cell_clm_adapter.py) de audit
    # + chong trung. Khoa (cr_session_id, cell_name) - GIONG ICrAffectedCellsRepo/
    # IQoeSnapshotRepo (1 cell chi giu 1 phieu / 1 CR session). Dict I/O (khong
    # phai domain entity) - cung pattern voi ICrAffectedCellsRepo/ICrLogRepo,
    # day la bang audit/log thuan, khong phai khai niem nghiep vu domain.
    @abstractmethod
    async def get_by_session_cell(self, cr_session_id: int, cell_name: str) -> dict | None:
        """Check trung TRUOC khi goi SaveCellClm - None neu cell nay chua co
        phieu trong session nay.

        VAN tra ve dong DA XOA MEM (deleted_at khong NULL, THEM 04/10/2026) -
        XuatPhieuUseCase.execute() dung dieu nay de chan tao lai phieu cho
        cell da bi xoa (xem domain/errors.py::PhieuDaXoaError)."""
        ...

    @abstractmethod
    async def get_success_cung_thang(self, cell_name: str, nam: int, thang: int) -> dict | None:
        """Phieu SUCCESS cua cell trong cung Nam/Thang, moi session (B9 - CTS
        chong trung theo CELL + THANG chu khong theo session)."""
        ...

    @abstractmethod
    async def ghi_lan_thu(
        self,
        cr_phieu_id: int,
        nguoi_thuc_hien: str,
        ket_qua: str,
        phieu_id: str | None = None,
        error_message: str | None = None,
        request_payload: dict | None = None,
        response_body: dict | None = None,
    ) -> None:
        """Ghi them 1 dong lich su lan POST (A5) - khong ghi de."""
        ...

    @abstractmethod
    async def lay_lan_thu(self, cr_phieu_id: int) -> list[dict]:
        """Lich su cac lan POST cua 1 phieu, cu -> moi."""
        ...

    @abstractmethod
    async def insert(self, phieu: dict) -> dict:
        """phieu: {"cr_session_id": int, "cell_name": str, "trang_thai": str,
        "request_payload": dict, "response_body": dict|None, "phieu_id": str|None,
        "error_message": str|None}. Tra ve dict day du (kem id/created_at DB
        sinh ra) - dung ngay sau khi goi CTS de update_result() bang id nay."""
        ...

    @abstractmethod
    async def update_result(
        self,
        id: int,
        trang_thai: str,
        response_body: dict | None,
        phieu_id: str | None,
        error_message: str | None,
        request_payload: dict | None = None,
        so_lan_thu_them: int = 0,
    ) -> None:
        """Cap nhat KET QUA sau khi goi SaveCellClm - insert() luon chay
        TRUOC (trang_thai=PENDING, response_body/phieu_id/error_message=None),
        update_result() chay SAU khi co response tu CTS (hoac loi mang).

        so_lan_thu_them (V3, 12/08 - thay cho co bool tang_so_lan_thu cu): CONG
        THEM vao cot so_lan_thu. Phai la SO chu khong phai bool vi 1 lan goi
        execute() gio co the POST toi XUAT_PHIEU_MAX_RETRY lan (retry trong
        luot) - cong +1 se noi doi ve "so lan da lam phien CTS". CALLER quyet
        dinh, repo KHONG tu suy tu trang_thai.

        request_payload (them 11/08, BUG THAT phat hien khi test ghep full):
        khi XUAT LAI cho 1 cell da co dong cu (PENDING/FAILED/KHONG_XUAT_*), use case
        TAI DUNG dong do va truoc day KHONG cap nhat lai cot request_payload ->
        cot audit giu nguyen payload cua lan xuat DAU TIEN, KHONG khop thu that
        su vua gui di (vd lan dau SoChiTieuVP=1 kieu int, lan sau da sua thanh
        "1" kieu str nhung cot van hien int) -> audit NOI DOI, debug se lac
        huong. Truyen payload moi vao day de cot luon khop lan gui gan nhat.
        None (mac dinh) = KHONG dung toi cot nay (giu tuong thich caller cu)."""
        ...

    @abstractmethod
    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        """Toan bo phieu cua 1 session, KHONG sort theo thu tu cu the.

        VAN tra ve dong DA XOA MEM (deleted_at khong NULL, THEM 04/10/2026) -
        KHAC list_phieu()/count_phieu() (BAT BUOC loc, dung cho hien thi).
        XuatPhieuUseCase._xem_truoc_mot_session()/_xu_ly_mot_session() dung
        dieu nay de loai cell co phieu da xoa khoi ung vien."""
        ...

    @abstractmethod
    async def danh_dau_khong_xuat(self, id: int, trang_thai: str) -> None:
        """V4 (12/08) - doi DUY NHAT cot trang_thai sang KHONG_XUAT_*.

        VI SAO KHONG dung update_result(): ham do ghi de ca response_body/
        phieu_id/error_message. Cell "het luot thu" LUON da co san 1 dong FAILED
        kem ly do CTS tu choi - do chinh la thu nguoi van hanh can doc de sua
        nguyen nhan goc, ghi de se xoa mat. so_lan_thu cung phai giu nguyen
        (khong POST lan nao thi khong duoc cong them)."""
        ...

    # Them 11/08 (UI lich su phieu, yeu cau truc tiep user) - man hinh lich su
    # dung CHUNG 1 endpoint cho ca 2 ngu canh: tab rieng (tat ca phieu) va
    # trong 1 session (loc session_id). get_by_cr_session_id() o tren KHONG
    # dung duoc: bat buoc phai co session_id, khong phan trang, khong sort,
    # khong dem total - se phai keo ve toan bo bang roi cat trang o Python khi
    # cr_phieu lon dan. Tach doi list_phieu()/count_phieu() (KHONG gop thanh
    # Page nhu ICrSessionRepo.list()) - dong nhat voi IEnodebRepo.find_stations()
    # /count_stations(), la endpoint listing dict-read-model gan nhat va cung
    # duoc router goi truc tiep.
    @abstractmethod
    async def list_phieu(
        self,
        session_id: int | None,
        trang_thai: str | None,
        page: int,
        size: int,
        sort_by: str | None = None,
        order: str = "desc",
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        # 17082026 - loc theo QOS/QOE/CA_HAI. Dat CUOI + co default de
        # moi cho goi theo vi tri (router, test cu) KHONG phai sua theo.
        nguon: str | None = None,
        # 19/10/2026 - theo TRAM CUA CELL (cr_affected_cells.tram_id), CUNG
        # dieu kien voi dong_excel(). None = khong loc, [] = 0 dong.
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> list[dict]:
        """1 trang phieu, moi dict co DU field nhu get_by_session_cell() (ke ca
        request_payload/response_body/error_message - xem ly do trong
        api/routers/phieu.py::list_phieu). session_id=None -> khong loc theo
        session.

        trang_thai=None = LAY TAT CA (V2 da bo luat an dong DRY_RUN mac dinh -
        khong con trang_thai nao bi giau: PENDING/SUCCESS/FAILED va 2 gia tri
        KHONG_XUAT_* cua V4 deu phai hien, do la muc dich cua V4).

        LUON loai dong DA XOA MEM (deleted_at khong NULL, THEM 04/10/2026,
        KHONG co tham so bat/tat) - count_phieu() cung dong CHUNG dieu kien nay
        qua _filter_conditions(), nen GET /phieu?trang_thai=FAILED (nguon dem
        song cho canh bao "Co N phieu xuat loi" o FE) tu dong het loi do.

        q (13/08): tim GAN DUNG (ILIKE) tren cell_name HOAC phieu_id - 1 o tim
        chung, nguoi dung khong phai chon truoc la tim theo gi. Chuoi rong/None
        = khong loc.

        tu_ngay/den_ngay (13/08): loc created_at, nua khoang [tu_ngay, den_ngay).
        Caller (router) tu quy doi NGAY LICH GMT+7 -> moc UTC va cong 1 ngay vao
        den_ngay - repo CHI nhan datetime da chuan, KHONG tu doi mui gio. Y HET
        hop dong cua IJobRunLogRepo.list_job_runs(), dung chung
        api/routers/loc_ngay.py.

        3 tham so nay dat o CUOI + co default de moi cho dang goi theo VI TRI
        khong phai sua theo.

        sort_by=None -> created_at DESC (phieu moi nhat truoc). Whitelist sort_by
        da validate o router (Literal, 422 tu dong) nhung adapter van tu
        whitelist LAI - an toan 2 lop, giong CrSessionRepo.list().

        vuot_2_phieu_sector (THEM 04/10/2026) - co trong moi dict tra ve:
        bool | None, tinh theo luat MOI (toi da 2 phieu/sector), CHI co y
        nghia voi dong trang_thai=SUCCESS (None o cac dong khac). Xem
        adapters/postgres/cr_phieu_repo.py ve cach tinh (window function)."""
        ...

    @abstractmethod
    async def count_phieu(
        self,
        session_id: int | None,
        trang_thai: str | None,
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        # 17082026 - loc theo QOS/QOE/CA_HAI. Dat CUOI + co default de
        # moi cho goi theo vi tri (router, test cu) KHONG phai sua theo.
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> int:
        """Tong so phieu KHOP filter (KHONG phai so dong tren 1 trang) - FE can
        de tinh so trang. PHAI nhan DU bo tham so loc giong list_phieu() va dung
        CHUNG dieu kien, neu khong "total" se dem ca dong ma "data" khong tra ve,
        FE tinh du so trang nhung trang cuoi rong."""
        ...

    @abstractmethod
    async def dong_excel(
        self,
        session_ids: list[int] | None = None,
        trang_thai: str | None = None,
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> list[dict]:
        """TOAN BO phieu khop loc (khong phan trang) cho Excel phieu + sheet
        "Phieu" cua Excel hau kiem (19/10/2026). 1 ham cho ca 2 file de so lieu
        2 file luon khop.

        Tinh/vendor theo TRAM CUA CELL (cr_affected_cells.tram_id), KHONG theo
        tram tat. None = khong loc; list rong = khong dong nao khop (vd giao
        khu_vuc x ma_tinh rong). LUON loai dong da xoa mem nhu list_phieu()."""
        ...

    @abstractmethod
    async def get_by_id(self, id: int) -> dict | None:
        """1 dong cr_phieu theo khoa chinh (them 20082026, cho DELETE /phieu/{id}).

        VAN tra ve dong DA XOA MEM (deleted_at khong NULL, THEM 04/10/2026) -
        caller (XuatPhieuUseCase/XoaPhieuUseCase) can THAY duoc trang thai do
        de chan tao lai / bao "da xoa truoc do"."""
        ...

    @abstractmethod
    async def xoa(self, id: int) -> int:
        """XOA MEM (SUA 04/10/2026, quyet dinh 04/10/2026) - set deleted_at=now()
        THAY VI DELETE that. Tra so dong CAP NHAT lan nay (0 = khong tim thay
        HOAC da xoa tu truoc - KHONG ghi de lai thoi diem xoa goc).

        Repo KHONG kiem trang_thai - luat "khong xoa phieu da len CTS" nam o
        XoaPhieuUseCase."""
        ...

class IJobRunLogRepo(ABC):
    # Them 11/08 (JOB TU DONG buoc 1/4, yeu cau truc tiep user) - luu lich su
    # MOI LAN job/scheduler chay. Dict I/O (khong phai domain entity) - cung
    # pattern ICrLogRepo/ICrPhieuRepo/ICrAffectedCellsRepo: day la bang audit/
    # log thuan, khong phai khai niem nghiep vu domain.
    #
    # KHONG khoa theo cr_session_id (khac ICrLogRepo/ICrPhieuRepo): 1 dong = 1
    # LUOT chay job quet NHIEU session, khong gan duoc vao 1 session cu the.
    @abstractmethod
    async def insert(self, log: dict) -> dict:
        """log: {"job_type": str, "trang_thai": str}. Goi luc
        job BAT DAU (trang_thai="RUNNING") - PHAI ghi dong nay TRUOC khi chay
        viec that, neu khong job chet giua chung se khong de lai dau vet nao
        (bai hoc session #197 ket vinh vien RUNNING, C1.4-fix2 - luc do khong
        co dong nao ghi lai da chay den dau).

        started_at do adapter tu set (datetime.now(timezone.utc)) - caller
        KHONG truyen, tranh moi noi goi tu tinh gio moi kieu. 4 cot so +
        finished_at/error_message/chi_tiet de mac dinh (0/NULL), se duoc dien o
        update_result(). Tra ve dict day du (kem id/started_at DB sinh ra) -
        dung id nay de goi update_result() khi job xong."""
        ...

    @abstractmethod
    async def update_result(
        self,
        id: int,
        trang_thai: str,
        finished_at: datetime,
        so_session_quet: int = 0,
        so_phieu_thanh_cong: int = 0,
        so_phieu_that_bai: int = 0,
        so_cell_vuot_gioi_han: int = 0,
        error_message: str | None = None,
        chi_tiet: dict | None = None,
    ) -> None:
        """Cap nhat KET QUA khi job ket thuc (DONE hoac FAILED) - insert() luon
        chay TRUOC. finished_at BAT BUOC truyen tu caller (khong tu set trong
        adapter nhu started_at): job co the ket thuc o nhieu nhanh khac nhau
        (xong binh thuong / except / timeout), caller moi biet CHINH XAC moc
        ket thuc nao dung cho nhanh cua no.

        4 cot so mac dinh 0 de nhanh FAILED som (chua quet duoc gi) khong phai
        truyen day du tham so chi de dien so 0."""
        ...

    @abstractmethod
    async def list_job_runs(
        self,
        job_type: str | None,
        page: int,
        size: int,
        sort_by: str | None = None,
        order: str = "desc",
        trang_thai: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
    ) -> list[dict]:
        """1 trang lich su chay job. job_type=None -> khong loc (tat ca loai
        job). sort_by=None -> started_at DESC (luot moi nhat truoc - dung index
        idx_job_run_log_started).

        KHONG tra cot chi_tiet (V3a, 12/08) - dung get_by_id() neu can. chi_tiet
        gom TOAN BO session x cell cua 1 luot chay nen 1 trang 20 dong se keo
        theo vai tram KB JSONB ma man hinh danh sach khong dung den. Bo han khoi
        cau SELECT (khong phai loc sau khi doc) - du lieu do khong bao gio roi
        khoi Postgres.

        tu_ngay/den_ngay loc theo started_at, nua khoang [tu_ngay, den_ngay):
        caller (router) tu quy doi NGAY LICH GMT+7 -> moc UTC, repo chi nhan
        datetime da chuan. Nua khoang chu khong <= : den_ngay la dau ngay HOM
        SAU nen tron ven ngay cuoi ke ca dong luc 23:59:59.999, khong phai xu ly
        do phan giai micro-giay.

        Tai dung y nguyen pattern ICrPhieuRepo.list_phieu()/count_phieu() (tach
        doi list + count, whitelist sort 2 lop) - KHONG co luat "an ngam" nao:
        moi luot chay job deu phai hien de nguoi van hanh biet job con song."""
        ...

    @abstractmethod
    async def count_job_runs(
        self,
        job_type: str | None,
        trang_thai: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
    ) -> int:
        """Tong so luot chay KHOP filter (KHONG phai so dong tren 1 trang).
        Dung CHUNG dieu kien loc voi list_job_runs() - 3 tham so loc PHAI giong
        het, neu lech thi total se khong khop so dong FE nhan duoc."""
        ...

    @abstractmethod
    async def get_by_id(self, id: int) -> dict | None:
        """1 luot chay DAY DU, CO kem chi_tiet - phuc vu GET /jobs/runs/{id}.

        Tach khoi list_job_runs() (khong dung 1 tham so include_chi_tiet) de
        hinh dang tra ve CO DINH: FE chi phai khai bao 1 kieu cho danh sach va 1
        kieu cho chi tiet, khong phai kieu "co the co hoac khong" tuy query
        param. Tra None khi khong ton tai - router doi thanh 404 (repo khong
        biet ve HTTP)."""
        ...


class IHoNeighborRepo(ABC):
    # Them 06-08/10/2026 (quyet dinh BO CDS, yeu cau truc tiep user) - doc du
    # lieu HO (handover) THAT da nap san tu NetAct (bang ho_neighbor, xem
    # models/ho_neighbor.py) de domain/services/ho_cell_selector.py chon cell
    # CR thay cho CDS /cell/neighbors. BUOC 4b (08/10/2026) - DA NOI vao
    # application/trigger_cr_use_case.py::_lay_du_lieu_goc_ho() (xem muc 12
    # dau file do), dieu kien qua cong tac .env NEIGHBOR_SOURCE=HO.
    @abstractmethod
    async def get_by_source_enb(self, netact: str, source_enb: int) -> list[dict]:
        """Toan bo dong HO (da giai ma) cua 1 tram nguon, KHONG sort/loc them -
        domain/services/ho_cell_selector.py tu nhom theo sector/xep hang.

        Tra ve [] neu tram khong co dong nao (TRUONG HOP "KHONG_CO_DU_LIEU_HO"
        - repo khong tu raise loi, de domain quyet dinh y nghia cua danh sach
        rong, giong tinh than cac repo khac trong project).

        dict fields: source_lncel_name, source_sector, target_enb, target_lcr,
        target_eci, ho_attempt, ho_sr (float|None)."""
        ...

    # THEM 15/10/2026 (yeu cau truc tiep user, "SUA THONG BAO KHI THIEU HO") -
    # phan biet 3 nguyen nhan KHONG_CO_DU_LIEU_HO (xem application/
    # trigger_cr_use_case.py::_lay_du_lieu_goc_ho()): can biet X co NHAN duoc
    # HO tu tram khac khong (chieu NGUOC lai voi get_by_source_enb) de phan
    # biet "chua khai bao neighbor/it UE" (CO nhan) voi "khong phat song"
    # (KHONG ca 2 chieu).
    @abstractmethod
    async def get_by_target_enb(self, netact: str, target_enb: int) -> list[dict]:
        """Toan bo dong HO ma `target_enb` la TRAM DICH (tram khac HO SANG no) -
        CHIEU NGUOC voi get_by_source_enb(). CHI dung de BAO CAO ly do thieu
        du lieu (dem so luot/so tram nguon phan biet), KHONG dung cho thuat
        toan chon cell (thuat toan CHI quan tam HO DI RA tu X).

        Tra [] neu khong co dong nao. dict fields: source_enb, ho_attempt
        (toi thieu can cho bao cao - KHONG can day du nhu get_by_source_enb)."""
        ...

    @abstractmethod
    async def co_du_lieu_netact(self, netact: str) -> bool:
        """True neu NetAct nay CO it nhat 1 dong du lieu HO (bat ky tram nao)
        trong bang ho_neighbor - phan biet "NetAct chua tung nap du lieu"
        (loi CU, giu nguyen thong bao) voi "NetAct co du lieu nhung RIENG
        tram X thi khong" (loi MOI, xem _lay_du_lieu_goc_ho())."""
        ...


class ICellViTriUocLuongRepo(ABC):
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - luu vi tri UOC LUONG
    # (CHI DE HIEN THI) cua cell nguon thuoc tram TOA_DO_DUNG_CHUNG (CRAN) -
    # xem models/cell_vi_tri_uoc_luong.py va domain/services/
    # cran_vi_tri_estimator.py.
    @abstractmethod
    async def xoa_va_ghi(self, netact: str, ngay_du_lieu, rows: list[dict]) -> int:
        """XOA SACH dong cu CUNG netact TRUOC khi ghi (GIONG ho_neighbor -
        tinh lai TOAN BO moi lan nap, khong phai upsert tung dong). rows:
        [{"enb":int,"lcr":int,"lat":float,"lon":float,"ty_le_ho_tin_cay":float,
        "so_tram_dich":int}] (tu domain/services/cran_vi_tri_estimator.py::
        uoc_luong_vi_tri_cran()). Tra so dong da ghi."""
        ...

    @abstractmethod
    async def get_by_netact(self, netact: str) -> dict[tuple[int, int], dict]:
        """Tra {(enb,lcr): {"lat":float,"lon":float,"ty_le_ho_tin_cay":float,
        "so_tram_dich":int,"ngay_du_lieu":date}} cho TOAN BO 1 netact - dung
        cho API xem truoc/ban do tra cuu vi tri uoc luong cua 1 cell/tram cu
        the (dict nho, tai het 1 lan re hon N truy van rieng)."""
        ...


@dataclass
class BoLocDashboard:
    """Bo loc chung cua dashboard (DOT 2, 18/10/2026). list None/rong = khong loc.

    ma_tinh: tinh cua TRAM TAT (session). vendor: AP 2 CACH (yeu cau user) -
    chi so CR (so session/tram/cell CR, can xu ly) theo vendor TRAM TAT; chi so
    hau kiem + phieu theo vendor CUA CELL (tram cua cell, tram.ten_thiet_bi
    chuan hoa UPPER(TRIM)). 1 session co the dong gop cell cho nhieu vendor."""

    tu_ngay: date
    den_ngay: date
    ma_tinh: list[str] | None = None
    vendor: list[str] | None = None


# Cot cho phep sap xep o chi tiet dashboard theo tung loai card (18/10/2026).
# Dat o PORT vi CA 2 phia dung: application kiem tham so (sai -> 422) va adapter
# ghep ten cot vao ORDER BY - whitelist la thu DUY NHAT chan SQL injection o
# day, 2 ban sao rieng se troi nhau. Ten = ten khoa trong dong tra ve.
# ten_tinh/khu_vuc cua cr (THEM 19/10/2026): JOIN danh muc tinh dung tu hang so
# Python ngay trong SQL nen sap xep duoc o SQL (xem dashboard_repo._danh_muc_tinh()).
COT_SAP_XEP_DASHBOARD: dict[str, tuple[str, ...]] = {
    "cr": ("ngay_cr", "session_id", "tram_id", "tram_name", "ma_tinh", "ten_tinh", "khu_vuc",
           "vendor_tram", "status", "so_cell_cr", "so_cell_anh_huong", "ma_loi"),
    "qos": ("ngay_cr", "session_id", "tram_name", "cell_name", "vendor_cell", "tb_truoc",
            "tb_sau", "lech", "ket_qua", "so_ngay_co_du_lieu", "ma_phieu"),
    "phieu": ("ngay_xuat", "ma_phieu", "session_id", "cell_name", "vendor_cell",
              "phuong_an", "trang_thai"),
    "can_xu_ly": ("ngay", "loai", "session_id", "tram_id", "tram_name", "status", "ma_loi"),
}
COT_SAP_XEP_DASHBOARD["qoe"] = COT_SAP_XEP_DASHBOARD["qos"]


class IDashboardRepo(ABC):
    # GET /dashboard/* (18/10/2026, yeu cau truc tiep user) - SO LIEU TONG HOP
    # tinh BANG SQL (khong lap tung session trong Python), chi doc. Nguong danh
    # gia TRUYEN VAO tu caller (application/) - adapter KHONG import
    # application/ (ARCHITECTURE.md SS9) va khong tu dat so 3.0/0.5.
    @abstractmethod
    async def tong_hop(self, loc: BoLocDashboard, nguong: dict, don_vi: str) -> list[dict]:
        """1 dong / nhom theo GROUPING SETS ((), (ma_tinh), (vendor), (moc)).
        "nhom" = "tong"|"ma_tinh"|"vendor"|"moc"; don_vi = "day"|"week" (moc
        thoi gian). nguong: {"min_ngay","muc_toi_thieu","lech_qos","lech_qoe"}."""
        ...

    @abstractmethod
    async def can_xu_ly(self, loc: BoLocDashboard, qua_han_truoc_ngay: date) -> dict:
        """{"qua_han": [...], "khong_chay": [...]} - qua han GIONG
        CrSessionRepo.list() qua_han; vendor = vendor tram tat."""
        ...

    @abstractmethod
    async def chi_tiet(
        self, loai: str, loc: BoLocDashboard, nguong: dict, loc_con: dict,
        qua_han_truoc_ngay: date, offset: int, limit: int | None,
        tim: dict | None = None, sap_xep: str | None = None, chieu: str = "desc",
    ) -> tuple[list[dict], int]:
        """(dong, tong so dong SAU loc + tim) cho 1 card. loai: cr|qos|qoe|phieu|
        can_xu_ly. Dung CUNG CTE voi tong_hop() nen tong khong loc = so tren card.
        tim: {"q": chuoi DA bo dau, "ma_tinh": [ma tinh co ten khop q]} | None.
        sap_xep: 1 cot trong COT_SAP_XEP_DASHBOARD[loai] (caller da kiem);
        None = cot ngay cua loai do."""
        ...

    @abstractmethod
    async def bo_loc(self) -> dict:
        """{"ma_tinh": [..], "vendor": [..]} DISTINCT tu bang tram."""
        ...

    @abstractmethod
    async def loc_session(
        self,
        tu_ngay: date,
        den_ngay: date,
        ma_tinh: list[str] | None,
        trang_thai: list[str] | None,
    ) -> list[dict]:
        """Session DA CHAY CR (executed_at co gia tri) theo CUNG bo loc ngay/
        ma_tinh voi dashboard (THEM 18/10/2026 cho xuat Excel hau kiem) - 1 cho
        dinh nghia "session trong khoang", Excel va dashboard khong lech nhau.
        dict: id, tram_id, tram_name, executed_at, status. Xep theo executed_at."""
        ...
