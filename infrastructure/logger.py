"""
setup_logger() - cau hinh logging chuan cho toan bo backend.
Tu: ARCHITECTURE.md Section 7.3; CONTEXT.md Section 8 (Logging Strategy); TASK_LIST.md B1.7

Level doc tu LOG_LEVEL env (CONTEXT.md Section 4), khac voi hard-code trong
ARCHITECTURE.md Section 7.3 minh hoa - vi .env da dinh nghia bien nay, dung no
de co tac dung thuc. Fallback "INFO" neu LOG_LEVEL khong co trong .env (khop
gia tri mau ARCHITECTURE.md lam default an toan).

Dung custom Formatter (KeyValueFormatter) thay vi format string tinh cua
ARCHITECTURE.md Section 7.3 - vi logging.basicConfig(format=...) chi render duoc
field co ten co dinh, khong tu in duoc cac field trong extra={} (session_id,
tram_id, cell_name, ...) vi ten field thay doi tuy lan goi. Can Formatter tu
duyet extra field moi log ra dung "key=value key=value" theo CONTEXT.md Section 8
- quan trong de filter log theo tram_id/cr_session_id khi trace CR flow (Part C).
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# TODO: 3 noi goi load_dotenv() hien tai (infrastructure/db.py, infrastructure/logger.py,
# va alembic/env.py tu B1.9). Goi lai o day vi logger.py co the duoc import doc lap,
# khong dam bao db.py da chay truoc. Chua co config.py/settings tap trung trong docs
# (xem TODO trong db.py) - don ve 1 cho neu sau nay du an them file do.
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# THEM (11/08, sau su co PHIEU MO COI): truoc day logger CHI co StreamHandler
# (stdout) - khi console crash thi MAT SACH log. Su co that: script chan doan
# POST that thanh cong (tao phieu tren TTS) nhung crash ngay luc in response
# (UnicodeEncodeError cp1252 do response CTS co tieng Viet CO DAU) -> mat luon
# ID phieu, khong truy lai duoc vi khong co file log va SaveCellClm khong co
# API GET. Ghi them ra FILE de du console chet van con dau vet.
LOG_FILE = os.getenv("LOG_FILE", "logs/r012.log")
# Rotate de file khong phinh vo han tren server chay dai ngay: 10MB x 5 file
# (~50MB tran) - du de truy nguoc vai ngay ma khong an het dia.
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

# Field chuan co san tren moi LogRecord - dung de tach rieng cac field "extra"
# nguoi goi tu them vao (vd. extra={"session_id": ..., "tram_id": ...}).
_STANDARD_RECORD_FIELDS = set(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"message", "asctime"}


class KeyValueFormatter(logging.Formatter):
    """Format: [LEVEL] [timestamp] [module] key=value key=value - message"""

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record)
        prefix = f"[{record.levelname}] {record.asctime} [{record.name}]"
        extra_fields = {
            k: v for k, v in record.__dict__.items() if k not in _STANDARD_RECORD_FIELDS
        }
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if extra_fields:
            kv = " ".join(f"{k}={v}" for k, v in extra_fields.items())
            return f"{prefix} {kv} - {message}"
        return f"{prefix} - {message}"


def _build_file_handler() -> logging.Handler | None:
    # encoding="utf-8" BAT BUOC: mac dinh FileHandler dung locale he thong
    # (cp1252 tren may Windows VN) -> log tieng Viet co dau se crash
    # UnicodeEncodeError, dung chinh loi da lam mat ID phieu.
    #
    # Loi tao file (khong co quyen ghi, dia day, duong dan sai) KHONG duoc lam
    # chet app - log ra console roi chay tiep voi StreamHandler. Log la co che
    # phu tro, khong duoc phep chan service khoi dong.
    try:
        path = Path(LOG_FILE)
        if path.parent and str(path.parent) not in (".", ""):
            path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(KeyValueFormatter())
        return handler
    except OSError as exc:
        print(f"[WARN] Khong tao duoc file log {LOG_FILE}: {exc} - chi log ra console", file=sys.stderr)
        return None


def setup_logger():
    # stdout tren Windows mac dinh cp1252 - in chuoi tieng Viet co dau se raise
    # UnicodeEncodeError va lam CHET tien trinh dang chay (da xay ra that, mat
    # ID phieu). Ep utf-8 + errors="replace": ky tu nao khong encode duoc thi
    # thay bang "?" chu TUYET DOI khong duoc nem exception tu tang log.
    # reconfigure() co tu Python 3.7; bao try/except phong truong hop stdout da
    # bi thay the (vd pytest capture) khong ho tro method nay.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    handlers: list[logging.Handler] = [handler]

    file_handler = _build_file_handler()
    if file_handler is not None:
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        handlers=handlers,
        # force=True: setup_logger() co the duoc goi lai (vd test, hoac import
        # lai module) - khong co force thi basicConfig() lan 2 bi BO QUA im
        # lang va handler moi (file) khong duoc gan.
        force=True,
    )
