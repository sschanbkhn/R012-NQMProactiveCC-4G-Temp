"""
build_sha512_headers() — 4 headers dung chung CDS + CTS.
Tu: ARCHITECTURE.md Section 5.1; CONTEXT.md Section 5.1; TASK_LIST.md B6.1
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

# BUG THAT phat hien khi test B6.2 (11072026): cong thuc API_CONTRACTS.md SS1
# dong 20-38 ("da test that" theo doc) THUC RA SAI - goi that vao gateway that
# tra ve HTTP 500 lien tuc. Doi chieu voi script thuc nghiem cua team
# (D:\Python_Project\Script\Test_api_CDS\test_cds_neighbors.py, phan anh dung
# Postman script CDS cung cap) va verify lai bang goi that: cong thuc dung la:
#   - X-Request-Date format "yyyyMMddHHmmss" (KHONG PHAI ISO UTC "...T...Z")
#   - Gio la GMT+7 (Vietnam), KHONG PHAI UTC nhu CONTEXT.md SS5.6 ghi
#   - X-Secure-Code = SHA512(request_id + "|" + request_date + "|" + cp_code + "|" + secure_key)
#     (co dau "|" phan cach VA co ca cp_code trong chuoi hash - doc cu thieu ca 2)
# Da verify that: 200 OK, tra du lieu that (368 cells) voi tram_id that "110548".
# Dung timezone(timedelta(hours=7)) tinh tuong minh, KHONG dung datetime.now() OS
# local - vi server production (CONTEXT.md SS3) co the khong dat timezone he
# thong la GMT+7, se sai gio neu dua vao OS clock.
_GMT7 = timezone(timedelta(hours=7))


def build_sha512_headers(cp_code: str, secure_key: str) -> dict:
    request_id = str(uuid.uuid4())
    request_date = datetime.now(_GMT7).strftime("%Y%m%d%H%M%S")
    raw = f"{request_id}|{request_date}|{cp_code}|{secure_key}"
    secure_code = hashlib.sha512(raw.encode()).hexdigest()
    return {
        "X-Request-Id": request_id,
        "X-Request-Date": request_date,
        "X-Cp-Code": cp_code,
        "X-Secure-Code": secure_code,
        "Content-Type": "application/json",
    }


# SaveCellClm (TTS/ApiCTS, cpCode RNOC1.TTS) can THEM 2 header ngoai 4 header
# SHA-512 chuan tren - CDS/CTS QoS (cpCode VNPT.NET.KTM.SOC) KHONG dung header nay.
#
# QUAN TRONG (xac nhan tu script da POST THAT thanh cong, tao phieu id=19177):
# secure_key truyen vao ham nay la KEY CUA USER, KHAC HOAN TOAN key cua cpCode
# dung cho build_sha512_headers() o tren. Ly do: X-Access-Key dinh danh USER
# (userName="CTS") - khong doi khi doi cpCode; con X-Secure-Code ky theo CPCODE.
# Dung NHAM 1 key cho ca 2 header -> 1 trong 2 header invalid (bug that da gap:
# ban dau R012 dung chung 1 key cho ca 2, X-Secure-Code bi ky sai key).
def build_access_key(user_name: str, secure_key: str) -> str:
    raw = f"{user_name}|{secure_key}"
    return hashlib.sha256(raw.encode()).hexdigest().upper()
