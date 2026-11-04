"""
Unit test cho infrastructure/logger.py - FileHandler + utf-8 (VIEC 3).
Tu: su co PHIEU MO COI 11/08/2026 - logger cu CHI co StreamHandler(stdout) nen
khi console crash (UnicodeEncodeError cp1252 do log tieng Viet co dau) thi MAT
SACH log, mat luon ID phieu da tao that tren TTS.
"""

import importlib
import logging

import pytest

# Chuoi tieng Viet CO DAU - dung chinh loai ky tu da lam crash script chan doan
# that (ky tu "ạ"/"ế" khong encode duoc bang cp1252).
_TIENG_VIET = "Thiếu trường bắt buộc - phiếu đã tạo trên hệ thống"


@pytest.fixture
def logger_module(tmp_path, monkeypatch):
    # Ghi log vao tmp_path (pytest tu don) - KHONG dung file log that cua repo.
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "test_r012.log"))
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    import infrastructure.logger as lg

    # reload de module doc lai LOG_FILE/LOG_LEVEL vua monkeypatch (2 bien nay
    # doc o cap module luc import, khong doc lai moi lan goi setup_logger()).
    importlib.reload(lg)
    yield lg
    # tra logging ve trang thai sach cho cac test khac (basicConfig(force=True)
    # cua test nay da thay toan bo handler goc).
    for h in logging.root.handlers[:]:
        h.close()
        logging.root.removeHandler(h)
    importlib.reload(lg)


def test_tao_file_log_va_ghi_duoc(logger_module, tmp_path):
    logger_module.setup_logger()
    logging.getLogger("test").info("dong log thu nghiem")

    for h in logging.root.handlers:
        h.flush()

    log_file = tmp_path / "logs" / "test_r012.log"
    assert log_file.exists(), "PHAI tao duoc file log (truoc day chi co stdout)"
    assert "dong log thu nghiem" in log_file.read_text(encoding="utf-8")


def test_log_tieng_viet_co_dau_KHONG_crash_va_doc_lai_dung(logger_module, tmp_path):
    # Day la ca quan trong nhat: truoc day chinh ky tu nay lam chet tien trinh.
    logger_module.setup_logger()
    logging.getLogger("test").warning(_TIENG_VIET)  # KHONG duoc raise

    for h in logging.root.handlers:
        h.flush()

    noi_dung = (tmp_path / "logs" / "test_r012.log").read_text(encoding="utf-8")
    assert _TIENG_VIET in noi_dung, "log tieng Viet phai doc lai dung, khong hong ma"


def test_phieu_id_van_vao_file_log_khi_log_kem_extra(logger_module, tmp_path):
    # Mo phong dung cach XuatPhieuUseCase log phieu_id sau khi POST thanh cong -
    # muc dich: du console chet thi ID phieu VAN con trong file, khong mat.
    logger_module.setup_logger()
    logging.getLogger("test").info(
        "SaveCellClm TAO PHIEU THANH CONG tren TTS",
        extra={"phieu_id": "19177", "cell_name": "4G-SSN104M12-HNI"},
    )

    for h in logging.root.handlers:
        h.flush()

    noi_dung = (tmp_path / "logs" / "test_r012.log").read_text(encoding="utf-8")
    assert "phieu_id=19177" in noi_dung
    assert "4G-SSN104M12-HNI" in noi_dung


def test_van_giu_StreamHandler_console(logger_module):
    # KHONG duoc bo log console khi them file - phai co CA HAI.
    logger_module.setup_logger()
    loai = [type(h) for h in logging.root.handlers]
    assert logging.StreamHandler in loai
    assert logging.handlers.RotatingFileHandler in loai


def test_loi_tao_file_log_KHONG_lam_chet_app(logger_module, monkeypatch):
    # Log la co che phu tro - khong co quyen ghi file thi van phai chay tiep
    # bang console, TUYET DOI khong duoc chan app khoi dong.
    def _mkdir_loi(*args, **kwargs):
        raise OSError("khong co quyen ghi")

    monkeypatch.setattr("pathlib.Path.mkdir", _mkdir_loi)

    logger_module.setup_logger()  # KHONG duoc raise

    loai = [type(h) for h in logging.root.handlers]
    assert logging.StreamHandler in loai  # van con console
    assert logging.handlers.RotatingFileHandler not in loai  # file thi khong tao duoc
