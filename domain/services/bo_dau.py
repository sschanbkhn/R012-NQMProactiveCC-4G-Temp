"""
Bo dau tieng Viet cho tim kiem (18/10/2026, chi tiet dashboard - yeu cau user:
tim KHONG phan biet hoa/thuong, KHONG phan biet dau).

=== VI SAO KHONG DUNG unaccent CUA POSTGRES ===
Extension unaccent CO SAN tren DB nhung CHUA cai (pg_extension chi co plpgsql).
CREATE EXTENSION la thay doi DB - ngoai pham vi "khong migration khi chua
duyet". Thay bang: (1) chuan hoa chuoi tim o Python (bo_dau()), (2) phia SQL
dung translate(lower(cot), CO_DAU, KHONG_DAU) - ham san co cua Postgres, khong
can extension, cung bang ky tu voi (1) nen 2 ve so sanh duoc voi nhau.

Chi stdlib (domain/ khong import ngoai - ARCHITECTURE.md SS9).
"""

import unicodedata

# Bang chu thuong co dau tieng Viet (67 ky tu) -> chu khong dau tuong ung.
# SQL goi lower() TRUOC translate() nen chi can bang chu thuong.
CO_DAU = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"


def _mot_ky_tu(c: str) -> str:
    if c == "đ":  # d gach khong phai dau ghep - NFD khong tach duoc
        return "d"
    return unicodedata.normalize("NFD", c)[0]


KHONG_DAU = "".join(_mot_ky_tu(c) for c in CO_DAU)


def bo_dau(chuoi: str | None) -> str:
    """Chu thuong + bo dau, CUNG ket qua voi translate(lower(x), CO_DAU, KHONG_DAU)."""
    return (chuoi or "").lower().translate(str.maketrans(CO_DAU, KHONG_DAU))
