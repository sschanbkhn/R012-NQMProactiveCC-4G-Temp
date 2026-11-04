"""
Schemas cho GET /jobs/runs + GET /jobs/runs/{id} (lich su chay job).
Tu: yeu cau truc tiep user (V3a, 12/08) - FE can hien lich su chay job trong
tab Lich su phieu; truoc do job_run_log chi doc duoc bang SQL tay.
"""

from datetime import date, datetime

from pydantic import BaseModel


class JobRunListItem(BaseModel):
    """1 dong trong bang lich su chay job (GET /jobs/runs).

    KHONG co chi_tiet - nguoc voi PhieuListItem (cho do CO Y tra ca
    request_payload/response_body de modal FE mo tuc thi). Khac biet nam o kich
    thuoc: 1 dong cr_phieu la du lieu cua DUNG 1 cell, con chi_tiet o day gom
    TOAN BO session x cell cua ca luot chay (cell_da_xu_ly, cell_vuot_gioi_han,
    cell_da_co_phieu, cell_vuot_so_lan_thu) - dung 1 trang 20 dong se keo theo
    vai tram KB ma man hinh danh sach khong dung den. Chinh truong hop
    PhieuListItem da du lieu san: "neu sau nay payload phinh to -> tach endpoint
    chi tiet". Muon xem chi_tiet -> GET /jobs/runs/{id}.
    """

    id: int
    # "xuat_phieu_auto" (hien tai) - de ngo cho job khac dung chung bang
    job_type: str
    started_at: datetime
    # NULL = luot chay chua ket thuc (dang RUNNING) HOAC job chet giua chung -
    # xem models/job_run_log.py
    finished_at: datetime | None = None
    # RUNNING / DONE / FAILED
    trang_thai: str
    # V2 (12/08): da BO field dry_run - job khong con che do chay thu, moi luot
    # deu POST that nen khong con gi de phan biet.
    so_session_quet: int
    so_phieu_thanh_cong: int
    so_phieu_that_bai: int
    so_cell_vuot_gioi_han: int
    error_message: str | None = None


class JobRunDetail(JobRunListItem):
    """GET /jobs/runs/{id} - y het dong danh sach, THEM chi_tiet.

    Ke thua JobRunListItem chu khong khai bao lai 10 field: them 1 cot vao bang
    sau nay chi phai sua 1 cho, khong the co chuyen 2 schema lech nhau.
    """

    # Hinh dang do XuatPhieuUseCase._xu_ly_mot_session() quyet dinh (danh sach
    # session, moi session kem cac nhom cell) - KHONG rang buoc schema chat o
    # day: day la du lieu CHI DE DOC LAI khi dieu tra, khoa cung hinh dang se
    # bat job phai doi theo moi lan FE muon them 1 truong.
    chi_tiet: dict | None = None


class JobRunListResponse(BaseModel):
    # {total, page, size, data} - dung y het PhieuListResponse/
    # SessionListResponse/StationListResponse. FE tai dung code doc san, khong
    # phai hoc format moi (chinh la ly do V3a chon page/size thay vi
    # limit/offset).
    total: int
    page: int
    size: int
    data: list[JobRunListItem]


class ChayJobXuatPhieuRequest(BaseModel):
    # POST /jobs/xuat-phieu-auto va .../xem-truoc (20082026).
    # Khoang NGAY CHAY CR (theo lich GMT+7), KHONG phai ngay xuat phieu.
    tu_ngay: date
    den_ngay: date


class XemTruocCellItem(BaseModel):
    cell_name: str
    nguon: str  # QOS | QOE | CA_HAI - chi so lam cell nay KHONG DAT
    # max(do tut QoS, do tut QoE). SUA 09/2026: KHONG con la thu quyet dinh
    # thu tu uu tien - thu tu gio do khoa_uu_tien_xuat_phieu() quyet dinh
    # (nhom truoc, roi do_giam, roi avg_after - xem domain/services/
    # evaluation_service.py). do_te CHI con la SO BAO CAO de nguoi xem hieu
    # muc do te, KHONG dung de suy ra thu tu cell trong danh sach.
    do_te: float
    # avg cua chi so LAM CELL KHONG DAT (xem _dong_xem_truoc trong
    # application/xuat_phieu_use_case.py). None khi chi so do thieu du lieu.
    avg_before: float | None = None
    avg_after: float | None = None
    # nhom/do_giam (them 09/2026) - 2 thanh phan THAT SU quyet dinh thu tu
    # (khoa_uu_tien_xuat_phieu(), domain/services/evaluation_service.py).
    # Them MOI, KHONG bo do_te: nguoi xem truoc thay do_te thap hon van dung
    # truoc do_te cao hon (vd HKM022M43 do_te 0.286 dung dau trong khi
    # HKM022M13 do_te 1.405 dung sau) se khong hieu tai sao neu chi nhin
    # do_te - phai co nhom/do_giam moi giai thich duoc.
    #   nhom 0 = avg_after THAP NHAT trong 2 chi so (QoS/QoE, chi tinh chi so
    #            CO ket luan) duoi MUC_TOI_THIEU (3.0) - uu tien TUYET DOI,
    #            luon truoc nhom 1
    #   do_giam = muc giam avg (before - after) LON NHAT giua QoS va QoE
    nhom: int | None = None
    do_giam: float | None = None


class XemTruocSessionItem(BaseModel):
    cr_session_id: int
    tram_id: str
    tram_name: str | None = None
    executed_at: datetime | None = None
    so_cell_se_xuat: int
    cells: list[XemTruocCellItem] = []
    # B9 (04092026) - cell KHONG DAT nhung da co phieu SUCCESS trong CUNG THANG
    # (bat ke session nao) nen se KHONG duoc xuat. Tra ra de nguoi bam hieu vi
    # sao so phieu it hon tong cell khong dat - truoc day xem truoc bo qua dieu
    # kien nay nen bao 16 trong khi chay that ra 14.
    so_cell_da_co_phieu_thang: int = 0
    cell_da_co_phieu_thang: list[str] = []
    # Session danh gia that bai (CTS/CEM loi) - PHAI hien len, neu khong nguoi
    # bam tuong session nay "khong co cell nao can xuat".
    loi: str | None = None


class XemTruocResponse(BaseModel):
    tong_phieu_se_xuat: int
    # Tong cell bi B9 loai tren TOAN BO khoang ngay - cong don tu cac session.
    tong_cell_da_co_phieu_thang: int = 0
    sessions: list[XemTruocSessionItem] = []
