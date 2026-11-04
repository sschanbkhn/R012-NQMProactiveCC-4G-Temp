"""
SCRIPT TEST THỰC NGHIỆM — KHÔNG PHẢI CODE PRODUCTION
Mục đích: kiểm tra cách auth SHA-512 mà CĐS gửi có hoạt động không.
Chạy: python test_cds_neighbors.py
"""

import hashlib
import os
import uuid
from datetime import datetime

import requests  # pip install requests --break-system-packages (nếu chưa có)

# ── Thông tin CĐS đã cung cấp ──────────────────────────────
# Doc tu bien moi truong - khong viet cung key vao source (de lo khi commit)
CP_CODE = os.getenv("CDS_CP_CODE", "VNPT.NET.KTM.SOC")
SECURE_KEY = os.environ["CDS_SECURE_KEY"]
URL = "https://gw-oneoss.vnpt.vn/oss/vps/service/vpsService/cell/neighbors"

# ── Body request (giống ví dụ CĐS gửi) ─────────────────────
BODY = {
    "tramId": 110548,
    "tramName": "UL_HKM005M_HNI" ,
    "action": "search",
    "technology": "4G",
}


def build_auth_headers() -> dict:
    """
    Sinh 4 header auth theo đúng logic Postman script CĐS đã gửi.
    Why: secureCode phải tính lại mỗi lần gọi vì requestDate (theo giây)
    nằm trong chuỗi hash -> hash đổi theo thời gian thực tế lúc gọi.
    """
    request_id = str(uuid.uuid4())

    now = datetime.now()
    request_date = now.strftime("%Y%m%d%H%M%S")  # yyyyMMddHHmmss

    combined = f"{request_id}|{request_date}|{CP_CODE}|{SECURE_KEY}"
    secure_code = hashlib.sha512(combined.encode("utf-8")).hexdigest()

    return {
        "X-Request-Id": request_id,
        "X-Request-Date": request_date,
        "X-Cp-Code": CP_CODE,
        "X-Secure-Code": secure_code,
        "Content-Type": "application/json",
    }


def main():
    headers = build_auth_headers()

    # In ra để tự kiểm tra trước khi gửi (debug, giống Bước 5 hướng dẫn Postman)
    print("── Headers sẽ gửi ──")
    for k, v in headers.items():
        print(f"{k}: {v}")
    print()
    print("── Body sẽ gửi ──")
    print(BODY)
    print()

    try:
        response = requests.post(
            URL,
            json=BODY,
            headers=headers,
            timeout=30,  # theo contract: Timeout 30s
        )
    except requests.exceptions.RequestException as e:
        # Bắt lỗi network (DNS fail, connection refused, timeout...)
        print("── LỖI KẾT NỐI (không tới được server) ──")
        print(type(e).__name__, ":", e)
        return

    print(f"── Status code: {response.status_code} ──")
    print("── Response body ──")
    try:
        print(response.json())
    except ValueError:
        # Server không trả JSON (có thể trả HTML lỗi)
        print(response.text[:2000])  # cắt bớt nếu quá dài


if __name__ == "__main__":
    main()