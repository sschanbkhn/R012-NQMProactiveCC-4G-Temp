"""
Test cho build_sha512_headers() — dung credentials that tu .env.
Tu: API_CONTRACTS.md SS1; TASK_LIST.md B6.1
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from adapters.http.sha512_auth import build_sha512_headers

load_dotenv()


def test_headers_dung_du_5_field_va_cp_code_that():
    headers = build_sha512_headers(os.getenv("CDS_CP_CODE"), os.getenv("CDS_SECURE_KEY"))
    assert set(headers) == {"X-Request-Id", "X-Request-Date", "X-Cp-Code", "X-Secure-Code", "Content-Type"}
    assert headers["X-Cp-Code"] == os.getenv("CDS_CP_CODE")
    assert headers["Content-Type"] == "application/json"


def test_request_id_la_uuid4_hop_le():
    headers = build_sha512_headers(os.getenv("CDS_CP_CODE"), os.getenv("CDS_SECURE_KEY"))
    # raise ValueError neu khong phai UUID hop le
    parsed = uuid.UUID(headers["X-Request-Id"])
    assert str(parsed) == headers["X-Request-Id"]


def test_request_date_dung_format_yyyymmddhhmmss_gmt7():
    # BUG THAT B6.2 (xem chu y trong adapters/http/sha512_auth.py): format that
    # server yeu cau la "yyyyMMddHHmmss" gio GMT+7, KHONG PHAI ISO UTC nhu doc cu.
    before = datetime.now(timezone(timedelta(hours=7))).replace(microsecond=0, tzinfo=None)
    headers = build_sha512_headers(os.getenv("CDS_CP_CODE"), os.getenv("CDS_SECURE_KEY"))
    after = datetime.now(timezone(timedelta(hours=7))).replace(microsecond=0, tzinfo=None)

    assert len(headers["X-Request-Date"]) == 14
    assert headers["X-Request-Date"].isdigit()
    parsed = datetime.strptime(headers["X-Request-Date"], "%Y%m%d%H%M%S")
    # header duoc sinh giua before/after (ca 2 da lam tron xuong giay) - dung tolerance
    # 1s cho before de tranh truong hop header sinh dung luc chuyen giay (truncate down)
    assert before - timedelta(seconds=1) <= parsed <= after


def test_secure_code_dung_cong_thuc_pipe_va_co_cp_code():
    # BUG THAT B6.2: cong thuc dung phai co dau "|" phan cach VA co ca cp_code
    # trong chuoi hash - doc cu (API_CONTRACTS.md SS1) thieu ca 2, gay HTTP 500
    # khi goi that (da fix + verify lai bang goi CDS that, xem TASK_LIST.md B6.2).
    cp_code = os.getenv("CDS_CP_CODE")
    secure_key = os.getenv("CDS_SECURE_KEY")
    headers = build_sha512_headers(cp_code, secure_key)

    raw = f"{headers['X-Request-Id']}|{headers['X-Request-Date']}|{cp_code}|{secure_key}"
    expected = hashlib.sha512(raw.encode()).hexdigest()
    assert headers["X-Secure-Code"] == expected


def test_2_lan_goi_lien_tiep_cho_request_id_khac_nhau():
    h1 = build_sha512_headers(os.getenv("CDS_CP_CODE"), os.getenv("CDS_SECURE_KEY"))
    h2 = build_sha512_headers(os.getenv("CDS_CP_CODE"), os.getenv("CDS_SECURE_KEY"))
    assert h1["X-Request-Id"] != h2["X-Request-Id"]
    assert h1["X-Secure-Code"] != h2["X-Secure-Code"]
