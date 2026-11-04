"""
Schemas cho /sessions/* endpoints.
Tu: TASK_LIST.md C1.1; API_CONTRACTS.md Section 6 (GET /sessions, GET /sessions/{id})

GHI CHU (cap nhat 20082026): ghi chu cu noi cr_logs/qoe_snapshots/qos_snapshots
LUON tra [] vi chua co repo. Ca 3 deu da giai quyet: cr_logs doc that tu cr_log
tu 22/07; qoe_snapshots/qos_snapshots DA BI XOA khoi response 20/08 (snapshot
luu per-cell nen 2 mang phinh 15 lan, va FE thoi doc tu 23/07).
"""

from datetime import date, datetime

from pydantic import BaseModel


class SessionListItem(BaseModel):
    id: int
    tram_id: str
    tram_name: str | None = None
    action: str
    status: str
    qoe_result: str | None = None
    qos_result: str | None = None
    executed_at: datetime | None = None
    evaluated_at: datetime | None = None
    created_at: datetime | None = None

    # === 6 truong TIEN TRINH (them 16082026, yeu cau truc tiep user) ===
    # Man hinh theo doi tien trinh 4 buoc cua FE. TAT CA deu do BE tinh san -
    # FE KHONG can biet quy tac nghiep vu nao (khong biet XUAT_PHIEU_AFTER_DAYS,
    # khong tu tru ngay, khong tu suy buoc tu status). Ly do: hien khong co
    # endpoint nao expose config, FE doan bua se lech voi job thuc te.
    so_cell_anh_huong: int = 0
    so_phieu_da_xuat: int = 0
    so_cell_cho_xuat_tay: int = 0

    # Ngay job du kien quet de xuat phieu. NULL khi chua chay CR.
    ngay_du_kien_xuat_phieu: date | None = None
    # Con bao nhieu ngay toi ngay tren. AM = DA QUA HAN (vd -3 la qua 3 ngay).
    # NULL khi chua co ngay du kien - KHONG phai 0 (0 nghia la "dung hom nay").
    con_bao_nhieu_ngay: int | None = None
    # 1 = CR (dang chay/loi) | 2 = cho thu thap KPI | 4 = da xuat phieu xong.
    # KHONG BAO GIO tra ve 3 - xem tinh_buoc_hien_tai() trong
    # application/get_sessions_use_case.py.
    buoc_hien_tai: int = 1

    # Ty le DN provision thanh cong (19082026) - "3/4 tram". 2 cot NAM NGAY
    # TREN cr_session nen chi SELECT them, KHONG phat sinh query phu (khac 3 con
    # so dem o tren - nhung cai do phai subquery sang bang khac).
    # NULL o session cu (chay truoc dot nay) va khi provision chua chay xong -
    # KHAC 0/0 ("da dem, khong DN nao thanh cong").
    so_cell_thanh_cong: int | None = None
    so_cell_tong: int | None = None

    # OSS/NOC session nay DA THUC SU gui CR len (02/10/2026) - de tra lich su.
    # NULL o session cu (backfill RIENG qua migration, xem alembic/versions/)
    # VA o session bi tu choi TRUOC khi chon duoc OSS (xem
    # trigger_cr_use_case.py::_fail()).
    oss_instance_id: str | None = None
    noc: str | None = None

    # ma_loi (THEM 16/10/2026, yeu cau truc tiep user) - error_code cua
    # DomainError gay FAILED/KHONG_CHAY (vd "KHONG_CO_DU_LIEU_HO", xem
    # domain/errors.py). NULL o session DONE/PARTIAL_SUCCESS va o session cu
    # (chay truoc migration nay, KHONG backfill).
    ma_loi: str | None = None

    # THEM 04/10/2026 (quyet dinh 04/10/2026, CHI DOC - KHONG sua CR cu) - so
    # cell CHAY CR cua session nay dang "ngoai dieu kien moi" (band/sector
    # chot 03-04/10/2026). 0 cho session chua chay CR hoac dat du dieu kien.
    # Chi tiet TUNG cell + ly do: xem GET /sessions/{id} (CellParamDetailItem.
    # ngoai_dieu_kien_moi).
    so_cell_ngoai_dieu_kien_moi: int = 0


class SessionListResponse(BaseModel):
    total: int
    data: list[SessionListItem]


class CellParamDetailItem(BaseModel):
    cell_name: str
    huong_id: str | None = None
    priority: int | None = None
    action_type: str | None = None
    rsboost_before_cr: float | None = None
    rsboost_new: float | None = None
    qrxlevmin_before_cr: int | None = None
    qrxlevmin_new: int | None = None
    # ngoai_dieu_kien_moi (THEM 04/10/2026, quyet dinh 04/10/2026) - gan nhan
    # LUC DOC theo luat band/sector MOI (chot 03-04/10/2026), KHONG sua du
    # lieu cu. List RONG = dat du dieu kien moi. Xem
    # domain/services/danh_gia_dieu_kien_cr_moi.py cho 3 ma ly do co the co:
    # BAND_KHONG_PHAI_1800 / KHONG_XAC_DINH_BAND / VUOT_2_CELL_SECTOR.
    ngoai_dieu_kien_moi: list[str] = []


class AffectedCellItem(BaseModel):
    # 22072026 (Phuong an B, DA DUYET) - 47 cell Nhanh A (danh gia RF, khong
    # co gia tri rsboost/qrxlevmin), BEN CANH cell_params (12 cell Nhanh B da
    # co san o duoi) - cung hinh dang voi AffectedCellItem trong cr_schemas.py
    # (preview) nhung dinh nghia rieng - 2 router khac nhau, khong ep coupling.
    cell_name: str
    tram_id: str | None = None
    huong_id: str | None = None


class CrLogItem(BaseModel):
    step: int
    step_name: str
    status: str
    message: str | None = None
    pct: int | None = None
    # ma_loi (THEM 16/10/2026) - CHI co gia tri o dong status="failed" gay
    # FAILED/KHONG_CHAY - xem models/cr_log.py.
    ma_loi: str | None = None
    created_at: datetime | None = None


class QoeSnapshotItem(BaseModel):
    snapshot_date: str
    qoe_score: float
    period: str


class QosSnapshotItem(BaseModel):
    snapshot_date: str
    qos_score: float
    period: str


class SessionDetailResponse(BaseModel):
    id: int
    tram_id: str
    tram_name: str | None = None
    action: str
    status: str
    plan_name: str | None = None
    qoe_result: str | None = None
    qos_result: str | None = None
    qoe_before: float | None = None
    qoe_after: float | None = None
    qos_before: float | None = None
    qos_after: float | None = None
    executed_at: datetime | None = None
    evaluated_at: datetime | None = None
    # Duong dan file log NetAct cua luot chay CR nay (04092026). Cot da co
    # trong DB tu b3f7d21ac504 nhung chua lo ra API.
    #
    # Dang TUONG DOI so voi thu muc goc du an (vd
    # "docs/logs/netact_runs/3625_20260821.log") - KHONG phai duong dan tuyet
    # doi, de khong vo khi doi may/doi thu muc trien khai.
    #
    # Muc dich hien tai: dung bang curl khi can doc log
    # (GET /sessions/{id}/log-netact). FE se BO nut xem log nen khong can them
    # gi khac. None voi session chay TRUOC khi co co che luu log.
    duong_dan_log: str | None = None
    # OSS/NOC session nay DA THUC SU gui CR len (02/10/2026) - xem chu y day
    # du trong SessionListItem o tren (cung y nghia, cung dieu kien NULL).
    oss_instance_id: str | None = None
    noc: str | None = None
    # ma_loi (THEM 16/10/2026) - xem chu y day du trong SessionListItem o tren.
    ma_loi: str | None = None
    cell_params: list[CellParamDetailItem] = []
    affected_cells: list[AffectedCellItem] = []
    cr_logs: list[CrLogItem] = []
    # BO 20082026 - qoe_snapshots/qos_snapshots DA XOA khoi response.
    # FE da xoa component doc 2 mang nay tu 23/07 (EvaluationDetail.tsx dong
    # 7-11: "XOA QoeQosCharts... da co chart 15 ngay tinh truc tiep tu
    # /qos/{cell}?from=&to=, KHONG phu thuoc job 21 ngay").
    # Va tu khi snapshot luu PER-CELL (20082026), giu lai se lam response
    # PHINH 15 LAN: 15 ngay x 9 cell = 135 diem thay vi 9, cho du lieu KHONG
    # AI DOC. Can lai sau nay thi lam endpoint RIENG
    # GET /sessions/{id}/snapshots co phan trang, khong nhoi vao day.


class XoaSessionResponse(BaseModel):
    # DELETE /sessions/{id} (20082026, yeu cau truc tiep user).
    #
    # so_dong_da_xoa la dict {ten_bang: so_dong} chu khong phai 1 tong: nguoi
    # van hanh can DOI CHIEU duoc voi cai ho thay tren UI truoc khi xoa
    # ("session nay co 9 cell va 4 phieu" -> phai thay dung 9 va 4). Mot con
    # so tong khong kiem chung duoc gi.
    id: int
    da_xoa: bool
    so_dong_da_xoa: dict[str, int]
