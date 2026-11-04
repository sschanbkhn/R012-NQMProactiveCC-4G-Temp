"""
Schemas cho POST /phieu + GET /phieu (lich su phieu).
Tu: yeu cau truc tiep user (KHOI 4a/5 SaveCellClm; UI lich su phieu 11/08).
"""

from datetime import datetime

from pydantic import BaseModel


class XuatPhieuRequest(BaseModel):
    session_id: int
    cell_name: str


class XuatPhieuResponse(BaseModel):
    # trang_thai: SUCCESS/FAILED/DAT_KHONG_XUAT/"<trang_thai cu>" (da xuat truoc)
    # - xem domain/ports/inbound/use_case_ports.py::XuatPhieuResult
    trang_thai: str
    # id phieu tren TTS (ticketId) - chi co khi SUCCESS (moi hoac da xuat truoc)
    phieu_id: str | None = None
    # {isError, code, message, data, status_code} tho tu CTS - chi co khi da
    # THAT SU goi CTS lan nay (KHONG co khi DAT_KHONG_XUAT/da xuat truoc, vi
    # khong goi gateway) - FE doc field nay de hien DUNG message loi tu CTS neu
    # isError. status_code them o V3a de phan biet 4xx voi 200+isError.
    #
    # THEM key "raw_body" khi CTS TU CHOI (status>=400 hoac isError): nguyen van
    # body loi - can vi CTS tra loi dang .NET problem+json (key errors/title/
    # status) chu KHONG dung 4 key tren, nen "message" se la None va FE se
    # khong biet loi gi neu thieu raw_body. FE nen hien raw_body khi message rong.
    cts_response: dict | None = None
    # thong bao phu: ly do DAT_KHONG_XUAT, "da xuat truoc do", hoac canh bao
    # loi ghi DB sau khi POST thanh cong (BUOC 2 dac ta - KHONG duoc mat
    # phieu_id du DB ghi loi)
    message: str | None = None


class PhieuListItem(BaseModel):
    """1 dong trong bang lich su phieu (GET /phieu).

    CO LUON request_payload/response_body/error_message (khong tach endpoint
    chi tiet rieng): moi CR session chi sinh toi da vai chuc dong cr_phieu nen
    tai them 2 cot JSONB/trang la khong dang ke, DOI LAI modal "xem chi tiet"
    cua FE mo tuc thi bang data co san, khong ton them 1 round-trip. Neu sau
    nay payload phinh to hoac list bi cham thay ro -> tach GET /phieu/{id} va
    bo 3 field nay khoi list."""

    id: int
    cr_session_id: int
    cell_name: str
    # 2 truong cua CR TAT TRAM (04092026) - FE can cot "Tram tat" o tab Phieu.
    # Phieu duoc xuat cho cell LAN CAN, nhin vao cell_name khong biet no thuoc
    # CR tat tram nao.
    #
    # KHONG lay tu request_payload->>'SiteName': truong do la tram cua CHINH
    # cell duoc xuat phieu, KHAC tram bi tat. Lay bang JOIN cr_session.
    #
    # None khi session/tram bi xoa (outerjoin) - khong lam vo bang.
    tram_id: str | None = None
    tram_name: str | None = None
    # PENDING / SUCCESS / FAILED (da POST that) + KHONG_XUAT_VUOT_GIOI_HAN /
    # KHONG_XUAT_HET_LUOT_THU / KHONG_XUAT_THIEU_DU_LIEU (job CO Y khong xuat,
    # CHUA POST lan nao) - xem models/cr_phieu.py va xuat_phieu_use_case.py
    trang_thai: str
    # 17082026 - chi so nao lam cell KHONG DAT: QOS / QOE / CA_HAI.
    # NULL o cac dong tao TRUOC dot nay (luc do QoE con la mock) va o cac dong
    # KHONG_XUAT_* (chua ket luan duoc thi khong co nguon).
    nguon_khong_dat: str | None = None
    # id phieu tren TTS - chi co khi trang_thai=SUCCESS
    phieu_id: str | None = None
    # V4 (12/08) - so lan DA POST that len CTS cho cell nay. FE can de phan biet
    # "chua thu lan nao" (cell vuot tran 10, so_lan_thu=0 -> bam Xuat la duoc)
    # voi "da thu het luot van hong" (so_lan_thu>=3 -> phai sua nguyen nhan goc
    # truoc, bam Xuat lai cung the).
    so_lan_thu: int = 0
    created_at: datetime | None = None
    request_payload: dict | None = None
    response_body: dict | None = None
    error_message: str | None = None
    # B4 (02092026) - NGHIEP_VU | KY_THUAT | None. KHONG phai cot trong DB: suy
    # tu error_message ngay luc tra ve (domain/services/phan_loai_loi_cts.py).
    # Xem ly do chon cach nay thay vi them cot trong chinh file do.
    # FE dung de tach "CTS tu choi co ly, khong phai lam gi" khoi "he thong minh
    # hong, phai bao dev" - hien tai ca hai deu ra 1 dong FAILED giong het nhau.
    phan_loai_loi: str | None = None
    # vuot_2_phieu_sector (THEM 04/10/2026, quyet dinh 04/10/2026) - gan nhan
    # LUC DOC theo luat MOI (toi da 2 phieu/sector cua tram tat), KHONG sua du
    # lieu cu. True = trong cung (cr_session_id, sector), day la phieu SUCCESS
    # thu 3 tro di tinh theo thoi diem tao (created_at). None (KHONG phai
    # False) cho dong KHONG phai SUCCESS - truong nay chi co y nghia tren
    # SUCCESS, tranh nguoi doc hieu nham "da xac nhan KHONG vuot" khi thuc ra
    # la "khong ap dung". sector=NULL (khong suy duoc tu huong_id) la 1 NHOM
    # RIENG, cung chiu luat nay - xem adapters/postgres/cr_phieu_repo.py.
    vuot_2_phieu_sector: bool | None = None
    # vuot_luat_lam_tron (THEM 18/10/2026) - True = phieu SUCCESS xuat TRUOC khi
    # lam tron TB/lech 2 chu so, ma tinh lai tren snapshot theo luat hien hanh
    # thi cell KHONG con KHONG DAT (vd 32084: lech tho 0.5000000000000004). FE
    # ghi "xuat theo luat cu". None cho dong khong phai SUCCESS (giong
    # vuot_2_phieu_sector). Tinh luc doc - xem application/phieu_lam_tron.py.
    vuot_luat_lam_tron: bool | None = None
    # THEM 19/10/2026 - tinh luc doc (domain/value_objects/trang_thai_phieu.py),
    # KHONG phai cot DB. phuong_an: "He thong"/"Hien truong" tu
    # request_payload.PhuongAnXuLyDuKien, None voi dong KHONG_XUAT_* (khong co
    # payload that). nhom_trang_thai: THANH_CONG/LOI/CHO_XUAT_TAY, None = PENDING.
    phuong_an: str | None = None
    nhom_trang_thai: str | None = None


class PhieuListResponse(BaseModel):
    # {total, data} - dung y het SessionListResponse/StationListResponse (FE da
    # co san code doc dang nay cho cac bang khac), KHONG dat ten "items".
    total: int
    page: int
    size: int
    data: list[PhieuListItem]


class XoaPhieuResponse(BaseModel):
    # DELETE /phieu/{id} (20082026, yeu cau truc tiep user). id la KHOA CHINH
    # cr_phieu.id, KHONG phai phieu_id cua CTS - tra ca cell_name/trang_thai
    # de nguoi dung xac nhan da xoa DUNG dong minh dinh xoa.
    id: int
    da_xoa: bool
    cell_name: str
    trang_thai: str
    # message (THEM 04/10/2026, XOA MEM) - None o lan xoa DAU TIEN. "Phieu nay
    # da duoc xoa truoc do" neu goi DELETE lai tren dong DA xoa (idempotent,
    # KHONG phai loi - da_xoa van True vi dong HIEN TAI dang o trang thai da xoa).
    message: str | None = None
