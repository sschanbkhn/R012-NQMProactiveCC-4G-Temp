"""
Nhom trang thai phieu (cr_phieu.trang_thai) + nhan phuong an xu ly.
Tu: yeu cau truc tiep user 19/10/2026 (duyet PHAN B - Excel phieu).

=== VI SAO 1 CHO ===
Truoc day moi noi tu dinh nghia: dashboard dem cho xuat tay bang LIKE
'KHONG_XUAT_%', router /phieu liet ke Literal rieng (thieu
KHONG_XUAT_DA_CO_PHIEU_THANG -> loc gia tri nay bi 422), Excel to mau theo
chuoi go tay. Them 1 trang thai ma quen 1 noi la so tren dashboard, bo loc va
2 file Excel lech nhau. Moi noi doc tu day.

PENDING KHONG thuoc nhom nao: la trang thai tam trong luc dang goi CTS (dong
bi ket PENDING la su co, khong phai ket qua) - nhom = None, de nguoi doc thay
la bat thuong thay vi bi gop vao LOI.

=== KHONG import gi ngoai stdlib === (ARCHITECTURE.md SS9)
"""

THANH_CONG = "THANH_CONG"
LOI = "LOI"
CHO_XUAT_TAY = "CHO_XUAT_TAY"

# Thu tu nhom = thu tu hien thi (chu giai, Excel).
NHOM_TRANG_THAI: dict[str, tuple[str, ...]] = {
    THANH_CONG: ("SUCCESS",),
    LOI: ("FAILED",),
    # Job CO Y khong xuat (chua POST CTS) - nguoi van hanh phai xem va xuat tay.
    CHO_XUAT_TAY: (
        "KHONG_XUAT_THIEU_DU_LIEU",
        "KHONG_XUAT_VUOT_GIOI_HAN",
        "KHONG_XUAT_HET_LUOT_THU",
        "KHONG_XUAT_DA_CO_PHIEU_THANG",
    ),
}

TRANG_THAI_CHO_XUAT_TAY = NHOM_TRANG_THAI[CHO_XUAT_TAY]

# Gia tri hop le cho bo loc trang_thai: moi trang thai co nhom + PENDING (giu
# lai vi API /phieu da cho loc PENDING tu truoc, bo di la FE cu bi 422).
TRANG_THAI_LOC: tuple[str, ...] = ("PENDING", *(t for ds in NHOM_TRANG_THAI.values() for t in ds))

_NHOM_THEO_TRANG_THAI = {t: nhom for nhom, ds in NHOM_TRANG_THAI.items() for t in ds}

# Y nghia tung trang thai - cho sheet "Chu giai" (nguoi doc Excel khong co code).
Y_NGHIA_TRANG_THAI = {
    "SUCCESS": "Da tao phieu tren CTS (co ma phieu)",
    "FAILED": "Da goi CTS nhung bi tu choi / loi mang het luot retry",
    "KHONG_XUAT_THIEU_DU_LIEU": "Khong du ngay du lieu QoS/QoE de ket luan",
    "KHONG_XUAT_VUOT_GIOI_HAN": "Vuot tran so phieu moi sector cua tram tat - job khong xuat tu dong",
    "KHONG_XUAT_HET_LUOT_THU": "Da POST het so lan thu cho phep (XUAT_PHIEU_MAX_RETRY) van loi",
    "KHONG_XUAT_DA_CO_PHIEU_THANG": "Cell da co phieu SUCCESS trong cung thang",
    "PENDING": "Dang goi CTS (ket lau la bat thuong)",
}

# PhuongAnXuLyDuKien trong request_payload (xuat_phieu_use_case.py): "2" khi
# TB sau cua QoS hoac QoE < 3.0 (phai ra hien truong), "1" con lai.
PHUONG_AN = {"1": "He thong", "2": "Hien truong"}


def nhom_trang_thai(trang_thai: str | None) -> str | None:
    return _NHOM_THEO_TRANG_THAI.get(trang_thai)


def ten_phuong_an(ma: str | None) -> str | None:
    # Dong KHONG_XUAT_* khong co payload that -> None (de trong), khong doan.
    return PHUONG_AN.get(ma)
