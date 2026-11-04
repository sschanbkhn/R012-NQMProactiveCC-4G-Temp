"""
Global exception handler -> format chuan {error_code, message, session_id}.
Tu: ARCHITECTURE.md Section 6.3; CONTEXT.md Section 9; API_CONTRACTS.md Section 7
(ERROR CODE CHUAN); TASK_LIST.md C1.2
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from domain.errors import DomainError

logger = logging.getLogger(__name__)

# API_CONTRACTS.md SS7 - anh xa error_code -> HTTP status. QOE_INSUFFICIENT_DATA
# khong xuat hien qua duong nay (khong phai loi HTTP - EvaluateCrUseCase tu xu ly
# noi bo, khong raise ra ngoai API layer) nhung van giu mapping du phong dung doc.
_ERROR_CODE_STATUS: dict[str, int] = {
    "TRAM_NOT_FOUND": 404,
    "CR_SESSION_NOT_FOUND": 404,
    "CR_ALREADY_DONE": 409,
    "CR_ALREADY_RUNNING": 409,
    "CR_EVALUATION_IN_PROGRESS": 409,
    "CR_ROLLBACK_NO_SOURCE": 400,
    "CDS_API_ERROR": 502,
    "SSH_CONNECTION_ERROR": 502,
    "XML_BUILD_ERROR": 500,
    "QOE_INSUFFICIENT_DATA": 202,
    # POST /cr/preview (API preview) - CDS tra ve nhung khong con cell nao
    # hop le sau filter/tinh gia tri - 422 (request hop le ve mat cu phap,
    # nhung khong xu ly duoc ve mat nghiep vu), khac 404 (TRAM_NOT_FOUND).
    "CR_NO_NEIGHBOR_CELL": 422,
    # CUNG 422 voi CR_NO_NEIGHBOR_CELL nhung la ma RIENG: CDS tra 0 cell (thieu
    # du lieu NGUON) vs co du lieu nhung bi loc het - xem
    # domain/errors.py::CrCdsNoNeighborDataError. Status giong nhau vi ve mat
    # HTTP ca hai cung la "request dung cu phap, khong xu ly duoc ve nghiep vu";
    # cai KHAC nhau nam trong error_code + message, de nguoi truc biet phai goi
    # team CDS hay xem lai luat loc cua R012.
    #
    # PHAI co dong nay: dict tra theo KHOA CHUOI error_code (.get(exc.error_code)
    # ben duoi), KHONG phai isinstance - ma moi khong tu thua 422 cua ma cu qua
    # quan he class. Thieu entry -> roi vao mac dinh 500.
    "CR_CDS_NO_NEIGHBOR_DATA": 422,
    # POST /phieu (KHOI 4a/5, yeu cau truc tiep user) - loi mang/timeout khi
    # POST that SaveCellClm len TTS - 503 (dich vu ngoai tam thoi khong san
    # sang), KHONG dung 502 nhu CDS_API_ERROR (xem ly do phan biet 2 loi trong
    # domain/errors.py::SaveCellClmApiError).
    "SAVE_CELL_CLM_API_ERROR": 503,
    # API CEM (nguon QoE muc cell) loi sau 3 lan retry - 502 GIONG CDS_API_ERROR
    # (deu la API DOC tu he thong ngoai, an toan retry, khong tao gi ben kia),
    # KHAC 503 cua SaveCellClm (WRITE API co the tao phieu trung).
    "CEM_API_ERROR": 502,
    # DELETE /sessions/{id} va DELETE /phieu/{id} (20082026) - 409 CUNG NHOM
    # voi CR_ALREADY_DONE/CR_ALREADY_RUNNING: request hop le ve cu phap, nhung
    # TRANG THAI HIEN TAI cua tai nguyen khong cho phep thao tac nay. Khong
    # phai 403 (khong lien quan quyen) cung khong phai 422 (khong phai loi noi
    # dung request).
    "XOA_SESSION_KHONG_HOP_LE": 409,
    "XOA_PHIEU_KHONG_HOP_LE": 409,
    # THEM 04/10/2026 (XOA MEM phieu) - cell co phieu da bi xoa mem, tu choi
    # xuat lai. CUNG NHOM 409 voi XOA_PHIEU_KHONG_HOP_LE (trang thai hien tai
    # cua tai nguyen khong cho phep thao tac, khong phai loi cu phap request).
    "PHIEU_DA_XOA": 409,
    # Giai doan 1 buoc 2 (27/09/2026, dinh tuyen OSS theo tung cell) - cell lan
    # can roi vao > 1 OSS khac nhau, 1 CR khong the tu dong tach nhieu XML -
    # 422 CUNG NHOM voi CR_NO_NEIGHBOR_CELL (request hop le ve cu phap, khong
    # xu ly duoc ve nghiep vu vi thieu quyet dinh cua nguoi van hanh).
    "CR_NHIEU_OSS": 422,
    # BUOC 4b (08/10/2026) - thay CDS bang HO trong xem truoc/chay CR. 422
    # CUNG NHOM voi CR_NO_NEIGHBOR_CELL/CR_CDS_NO_NEIGHBOR_DATA (request hop
    # le ve cu phap, khong xu ly duoc ve nghiep vu vi thieu du lieu HO dang
    # tin cay) - xem domain/errors.py::HoNoDataError.
    "KHONG_CO_DU_LIEU_HO": 422,
    # THEM 23/10/2026 - NetAct cua tram chua cau hinh / cau hinh loi (xem
    # domain/errors.py::CauHinhNetactLoiError). Giu 422 nhu khi con gop chung
    # KHONG_CO_DU_LIEU_HO de FE/preview khong doi hanh vi HTTP.
    "CAU_HINH_NETACT_LOI": 422,
}


async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = _ERROR_CODE_STATUS.get(exc.error_code, 500)
    logger.warning(
        "DomainError xu ly boi middleware",
        # "message" la key noi bo cua LogRecord (Python logging) - dung
        # "error_message" de tranh KeyError "Attempt to overwrite 'message'"
        # (bug that phat hien qua smoke test 13072026, xem DEV_LOG.md)
        extra={"error_code": exc.error_code, "error_message": exc.message, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            # session_id chi co khi context truyen kem (VD TriggerCrUseCase da
            # tao session truoc khi loi) - phan lon DomainError (guard truoc khi
            # tao session) khong co, tra None
            "session_id": exc.context.get("session_id"),
        },
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Loi thuc su ngoai du kien (bug) - khong nuot am tham, log day du de debug,
    # tra ve format chuan voi error_code INTERNAL_ERROR (API_CONTRACTS.md dong 775)
    logger.exception("Unhandled exception", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"error_code": "INTERNAL_ERROR", "message": str(exc), "session_id": None},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
