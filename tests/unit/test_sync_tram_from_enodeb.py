"""
Unit test cho adapters/http/sync_tram_from_enodeb.py::to_row() - ham thuan
(khong I/O), chi kiem tra mapping JSON API -> dict cot DB.
Tu: yeu cau truc tiep user (SUA SYNC TRAM, 04/10/2026 - OQ-11 da resolve).

SUA 04/10/2026 (lan 2): module duoi test da doi "import requests" (KHONG nam
trong requirements/venv repo) -> "import httpx" (GIONG EnodebHttpAdapter,
da co san trong venv) - BO stub sys.modules["requests"] tung can truoc day,
import thang binh thuong duoc.
"""

from adapters.http.sync_tram_from_enodeb import to_row


def test_to_row_day_du_field_bao_gom_ten_quan_ly():
    # SUA 04/10/2026 (OQ-11 da resolve) - API that tra ten_quan_ly dang
    # "SMC_VINPEARL-CUA HOI1-CLO_NAN", khac mau "4G-...-XXX" cua cell_name/
    # SiteName (day la ten don vi quan ly hanh chinh, khong phai ten cell).
    raw = {
        "stt": 1,
        "enodeb_id": 110548,
        "ten_he_thong": "4G-HKM005M-HNI",
        "ten_quan_ly": "SMC_VINPEARL-CUA HOI1-CLO_NAN",
        "ma_csht": "CSHT-HNI-999",
        "longitude": 105.8,
        "latitude": 21.0,
        "ma_tinh": "HNI",
        "ten_thiet_bi": "Nokia AirScale",
    }
    row = to_row(raw)
    assert row == {
        "tram_id": "110548",
        "tram_name": "4G-HKM005M-HNI",
        "ma_tinh": "HNI",
        "ten_thiet_bi": "Nokia AirScale",
        "longitude": 105.8,
        "latitude": 21.0,
        "ma_csht": "CSHT-HNI-999",
        "ten_quan_ly": "SMC_VINPEARL-CUA HOI1-CLO_NAN",
    }


def test_to_row_thieu_key_ten_quan_ly_tra_none_khong_loi():
    # Ban ghi THIEU han key "ten_quan_ly" (vd API tra thieu field cho 1 tram
    # rieng le, hoac fixture cu truoc 04/10 chua co field nay) - .get() tra
    # None tu nhien, KHONG duoc crash KeyError.
    raw = {"enodeb_id": 999999, "ten_he_thong": "4G-TEST-HNI"}
    row = to_row(raw)
    assert row["ten_quan_ly"] is None
    assert row["tram_id"] == "999999"


def test_to_row_ten_quan_ly_rong_hoac_khoang_trang_tra_none():
    # "" (rong) VA "   " (toan khoang trang) deu phai ra None - KHONG luu
    # nham chuoi rong/chuoi trang vao DB thay vi NULL that su.
    assert to_row({"enodeb_id": 1, "ten_quan_ly": ""})["ten_quan_ly"] is None
    assert to_row({"enodeb_id": 1, "ten_quan_ly": "   "})["ten_quan_ly"] is None
    assert to_row({"enodeb_id": 1, "ten_quan_ly": None})["ten_quan_ly"] is None


def test_to_row_ten_quan_ly_co_khoang_trang_dau_cuoi_duoc_strip():
    # Du lieu that co the dinh khoang trang thua dau/cuoi (nhap lieu RIMS) -
    # KHONG lam hong gia tri HOP LE ben trong, chi strip 2 dau.
    row = to_row({"enodeb_id": 1, "ten_quan_ly": "  SMC_VINPEARL-CUA HOI1-CLO_NAN  "})
    assert row["ten_quan_ly"] == "SMC_VINPEARL-CUA HOI1-CLO_NAN"
