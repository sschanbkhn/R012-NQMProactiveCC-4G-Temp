"""
Domain errors — TramNotFoundError, CdsApiError, SshConnectionError, XmlBuildError,
QoeDataInsufficientError, CrAlreadyDoneError, CrAlreadyRunningError, CrRollbackNoSourceError,
CrSessionNotFoundError (them o C2.4, 13072026).
Tu: CONTEXT.md Section 9; API_CONTRACTS.md Section 7 (ERROR CODE CHUAN); TASK_LIST.md B2.1
"""


class DomainError(Exception):
    # error_code hardcode trong tung subclass — khong nhan tu ben ngoai de
    # tranh gan nham code sai class (BUSINESS_RULES.md / API_CONTRACTS.md SS7)
    def __init__(self, message: str, error_code: str, **context):
        self.message = message
        self.error_code = error_code
        self.context = context
        super().__init__(message)


class TramNotFoundError(DomainError):
    # BUSINESS_RULES.md SS1 — tram_id/tram_name khong tim thay trong DB
    def __init__(self, message: str, **context):
        super().__init__(message, "TRAM_NOT_FOUND", **context)


class CrSessionNotFoundError(DomainError):
    # Bo sung o C2.4 (13072026) - GET /sessions/{id} voi id khong ton tai. Khac
    # ValueError da dung trong CrSessionRepo.update() (loi goi sai noi bo cua
    # caller) - day la loi USER-facing hop le (client goi sai id qua HTTP), can
    # error_code rieng de middleware map dung 404, cung nhom voi TramNotFoundError.
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_SESSION_NOT_FOUND", **context)


class CrAlreadyDoneError(DomainError):
    # BUSINESS_RULES.md SS1 — action shutdown/relocate nhung tram da co cr_session DONE
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_ALREADY_DONE", **context)


class CrAlreadyRunningError(DomainError):
    # BUSINESS_RULES.md SS1 — tram dang co cr_session RUNNING, tranh 2 CR song song
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_ALREADY_RUNNING", **context)


class CrEvaluationInProgressError(DomainError):
    # Bo sung o C2.2-fix (13072026, xac nhan voi user) - guard don gian tranh
    # 2 tien trinh evaluate_cr_use_case cung xu ly 1 session (n8n co the trigger
    # POST /jobs/evaluate-cr chong lan neu interval ngan hon thoi gian chay
    # thuc te - CHUA co xac nhan chac chan tu phia n8n config). session.status
    # duoc dung lam "lock" (EVALUATING) - session nao dang EVALUATING thi bi
    # loai khoi danh sach eligible (list() chi loc DONE/EVAL_PENDING) VA
    # execute() tu kiem tra lai truoc khi lam I/O cham, tranh race giua 2 lan
    # goi execute_all_pending() gan nhau.
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_EVALUATION_IN_PROGRESS", **context)


class CrRollbackNoSourceError(DomainError):
    # BUSINESS_RULES.md SS4.3 — action=cancel nhung thieu cr_session DONE truoc do
    # hoac rsboost_before_cr/qrxlevmin_before_cr = null trong cell_params
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_ROLLBACK_NO_SOURCE", **context)


class CdsApiError(DomainError):
    # WORKFLOW.md Buoc 3 — goi CDS API /cell/neighbors fail sau 3 lan retry (1s/2s/4s)
    def __init__(self, message: str, **context):
        super().__init__(message, "CDS_API_ERROR", **context)


class CrNoNeighborCellError(DomainError):
    # Them cho API preview (POST /cr/preview) - CDS goi thanh cong (khong phai
    # CdsApiError) nhung sau filter+tinh gia tri KHONG con cell nao hop le (0
    # huong hoac toan bo cell bi loai o buoc 4-10) - khac ve BAN CHAT voi
    # TRAM_NOT_FOUND (tram co ton tai, chi la khong co neighbor dat dieu kien),
    # nen can error_code rieng de FE phan biet 2 truong hop khi hien thong bao.
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_NO_NEIGHBOR_CELL", **context)


class CrCdsNoNeighborDataError(DomainError):
    # Tach ra tu CrNoNeighborCellError - CDS goi thanh cong nhung tra ve 0 cell
    # (0 huong, HOAC co huong nhung moi huong cells=[]).
    #
    # VI SAO TACH: hai tinh huong doi hoi 2 HANH DONG khac han.
    #   - CDS rong = THIEU DU LIEU NGUON. Khong co gi de loc. Nguoi dung phai
    #     di hoi team CDS (tram moi lap? chua khai bao neighbor?) - sua o he
    #     thong KHAC, khong phai o R012.
    #   - CrNoNeighborCellError = CO du lieu nhung bi loc het (prefix NB-/MBF_/
    #     VNP-, cell tram goc, cell_id phang ngoai pham vi, thieu rsboost/
    #     qrxlevmin trong cell_infor). Day la ket qua DUNG cua luat nghiep vu
    #     R012 - khong ai can lam gi ca, hoac neu can thi la xem lai luat loc.
    # Gop 1 ma thi nguoi truc doc thong bao xong van khong biet phai goi ai.
    #
    # CO Y **KHONG** ke thua CrNoNeighborCellError: ke thua thi `except
    # CrNoNeighborCellError` va `pytest.raises(CrNoNeighborCellError)` cu van
    # bat duoc ca ma moi - tuc viec tach nay se IM LANG khong co tac dung o
    # nhung cho da viet. De 2 class doc lap thi test cu PHAI do, buoc nguoi
    # sua phai nhin lai tung cho va chon CO CHU DICH.
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_CDS_NO_NEIGHBOR_DATA", **context)


class SshConnectionError(DomainError):
    # WORKFLOW.md Buoc 13/14 — SSH/SFTP toi NetAct fail (upload XML, Import, Provision)
    def __init__(self, message: str, **context):
        super().__init__(message, "SSH_CONNECTION_ERROR", **context)


class XmlBuildError(DomainError):
    # WORKFLOW.md Buoc 12 — build XML rsboost/qrxlevmin loi
    def __init__(self, message: str, **context):
        super().__init__(message, "XML_BUILD_ERROR", **context)


class SaveCellClmApiError(DomainError):
    # Them KHOI 4a/5 (yeu cau truc tiep user) - loi MANG/timeout khi POST that
    # SaveCellClm (adapters/http/save_cell_clm_adapter.py).
    # RIENG khoi CdsApiError (dung cho CDS/CTS - API DOC, an toan retry) vi day
    # la WRITE API tao phieu that tren TTS: POST lai sau loi mang co the tao
    # PHIEU TRUNG neu lan dau thuc ra da toi server thanh cong nhung response bi
    # mat tren duong ve.
    #
    # V3 (12/08): DA CHO retry, nhung o TANG USE CASE chu khong phai trong
    # adapter - va CHI cho loi mang/timeout + 5xx. Doi lai rui ro phieu trung
    # (nhin thay va xoa duoc tren TTS) de tranh mat luon co hoi xuat: theo PA A
    # moi session chi duoc quet DUNG 1 ngay. Xem
    # application/xuat_phieu_use_case.py::_goi_gateway_co_retry().
    #
    # Exception nay duoc nem KHI VA CHI KHI het luot thu ma khong lan nao toi
    # duoc CTS. Anh xa rieng 503 (api/middleware/error_handler.py) - KHAC 502 cua
    # CdsApiError, vi day la loi tam thoi ben ngoai (mang/CTS down), khong phai
    # loi request/response cu the.
    def __init__(self, message: str, **context):
        super().__init__(message, "SAVE_CELL_CLM_API_ERROR", **context)


class QoeDataInsufficientError(DomainError):
    # BUSINESS_RULES.md SS8.4 — so ngay co QoE/QoS data thuc te < 5/7 ngay.
    # Khong coi la loi that su — cr_session.status = EVAL_PENDING, n8n retry ngay hom sau.
    def __init__(self, message: str, **context):
        super().__init__(message, "QOE_INSUFFICIENT_DATA", **context)


class CemApiError(DomainError):
    # Them 16082026 - goi API CEM (nguon QoE muc cell) that bai sau 3 lan retry.
    #
    # RIENG khoi CdsApiError du cung la "API doc, an toan retry": CEM la he
    # thong KHAC HAN (api-cem.vnptmedia.vn, auth SHA-256 + "@2022" trong body),
    # khong di qua gateway gw-oneoss.vnpt.vn nhu CDS/CTS. Gop chung 1 ma loi se
    # lam nguoi truc khong biet phai goi doi ngu nao khi co canh bao.
    def __init__(self, message: str, **context):
        super().__init__(message, "CEM_API_ERROR", **context)


class XoaSessionKhongHopLeError(DomainError):
    # DELETE /sessions/{id} (20082026, yeu cau truc tiep user) - chi cho xoa
    # session FAILED.
    #
    # VI SAO CHI FAILED: session DONE va PARTIAL_SUCCESS co tram DA DOI THAM SO
    # RF THAT tren thiet bi. Dong cr_session (kem cr_log/cell_params) la BANG
    # CHUNG DUY NHAT ve viec do - xoa di thi sau nay khong ai truy duoc vi sao
    # RF cua tram lech so voi thiet ke ban dau. FAILED = 0 DN thanh cong =
    # khong tram nao doi gi -> khong co bang chung nao de mat.
    def __init__(self, message: str, **context):
        super().__init__(message, "XOA_SESSION_KHONG_HOP_LE", **context)


class CrNhieuOssError(DomainError):
    # Giai doan 1 buoc 2 (27/09/2026) - dinh tuyen OSS theo TUNG CELL (khong
    # phai theo tram tat). 1 CR hien tai CHI build 1 file XML + goi 1 lan
    # submit_cr() - neu cac cell lan can roi vao > 1 OSS khac nhau (giap ranh
    # tinh cu) thi KHONG the tu dong chia XML gui nhieu noi. Tu choi ro rang
    # (422) va liet ke ten OSS + so cell moi OSS trong message, de nguoi van
    # hanh tu quyet dinh (co the phai tach thanh nhieu CR rieng theo tung
    # vung) - thay vi am tham chon 1 OSS va bo sot cell cua OSS kia.
    def __init__(self, message: str, **context):
        super().__init__(message, "CR_NHIEU_OSS", **context)


class XoaPhieuKhongHopLeError(DomainError):
    # DELETE /phieu/{id} (20082026, yeu cau truc tiep user) - chi cho xoa dong
    # phieu CHUA len CTS.
    #
    # VI SAO CHAN SUCCESS: SUCCESS nghia la phieu DA nam ben CTS that va co
    # phieu_id. Xoa dong o DB KHONG xoa duoc phieu ben CTS - chi lam mat dau
    # vet phia minh, roi lan sau he thong tuong cell chua xuat va xuat TRUNG.
    def __init__(self, message: str, **context):
        super().__init__(message, "XOA_PHIEU_KHONG_HOP_LE", **context)


class PhieuDaXoaError(DomainError):
    # POST /phieu (THEM 04/10/2026, quyet dinh 04/10/2026 - XOA MEM, yeu cau
    # truc tiep user) - cell nay DA CO 1 dong cr_phieu bi xoa mem (deleted_at
    # khong NULL) cho (cr_session_id, cell_name) nay. Quyet dinh: phieu da xoa
    # KHONG BAO GIO duoc tao lai - chan NGAY o BUOC 1 cua XuatPhieuUseCase.execute()
    # (dong truoc khi insert/tai su dung id), KHONG de roi xuong insert() moi
    # vi se vi pham UNIQUE(cr_session_id, cell_name) (dong cu van con, chi
    # deleted_at khac NULL).
    def __init__(self, message: str, **context):
        super().__init__(message, "PHIEU_DA_XOA", **context)


class HoNoDataError(DomainError):
    # BUOC 4b (08/10/2026, yeu cau truc tiep user) - THAY CDS bang HO trong
    # xem truoc/chay CR. Dung CHUNG 1 ma loi cho CA 3 ly do (khong tach rieng
    # nhu CrNoNeighborCellError/CrCdsNoNeighborDataError cua nhanh CDS):
    #   1. Khong xac dinh duoc NetAct cua X (khong suy duoc ma tinh cu tu ten
    #      tram, hoac IOssRouter chua cau hinh route cho (ma_tinh_cu, vendor)).
    #   2. ho_neighbor khong co dong nao cho (netact, source_enb=X) - CHUA tung
    #      nap du lieu HO cua NetAct do, hoac X khong co HO qua lai thuc te.
    #   3. CO dong HO nhung domain.chon_cell_cr() tu xac dinh KHONG DU DU LIEU
    #      (moi sector duoi N_MIN_HO_SECTOR - xem KhongCoDuLieuHoError).
    # CA 3 deu la "KHONG CO DU LIEU HO DUNG TIN CAY DE CHAY THUAT TOAN" xet tu
    # goc nhin nguoi dung (khac CDS: CDS rong vs CDS co nhung bi loc het la 2
    # HANH DONG xu ly khac nhau - goi team CDS vs xem lai luat loc R012; o day
    # CA 3 tinh huong deu CHI co 1 HANH DONG: cho/nap du lieu HO, khong co gi
    # de "xem lai luat loc" vi HO chua noi vao luong that).
    def __init__(self, message: str, **context):
        super().__init__(message, "KHONG_CO_DU_LIEU_HO", **context)


class CauHinhNetactLoiError(DomainError):
    # THEM 23/10/2026 (yeu cau truc tiep user) - TACH khoi HoNoDataError ly do
    # "NetAct cua X chua cau hinh / cau hinh loi" (thieu password, route tro NA
    # khong co, chua co route). Dung KHONG_CO_DU_LIEU_HO cho truong hop nay la
    # SAI NGHIA: hanh dong xu ly khac han (sua file cau hinh NA + restart, khong
    # phai cho/nap du lieu HO) va de nham voi thieu HO that. Message chi chua
    # TEN NA (vd "NA14 cau hinh loi: thieu password"), KHONG host/IP/mat khau.
    def __init__(self, message: str, **context):
        super().__init__(message, "CAU_HINH_NETACT_LOI", **context)
