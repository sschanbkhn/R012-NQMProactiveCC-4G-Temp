"""
ten_tinh_tu_ma() - ma tinh MOI (sau sap nhap, Nghi quyet 306/NQ-CP/2025, 34
tinh/thanh) -> ten tinh day du. BUOC 4c (10/10/2026, yeu cau truc tiep user) -
dung hien thi ten tinh tren ban do (API /stations/map, xem truoc CR).

TAI SAO RIENG VOI khu_vuc.py: khu_vuc.py anh xa ma_tinh (CA cu lan moi) ->
KV1/KV2/KV3 (ranh gioi VAN HANH NOC, khong phai ranh gioi hanh chinh). File
nay CHI anh xa ma MOI (34 ma CHINH THUC sau sap nhap) -> TEN TINH DAY DU (y
nghia HANH CHINH, khong lien quan NOC/van hanh) - 2 khai niem khac nhau, 2
bang khac nhau, KHONG gop chung de tranh 1 thay doi lam sai ca 2.

KHONG goi ma CU (vd "HDG", "BGG" truoc sap nhap) - khac khu_vuc.py (co ly do
rieng giu ca 2 de KHONG tram nao "bien mat" khoi loc KV). O day MUC DICH la
HIEN THI TEN TINH - ma cu khong con ten tinh "chinh thuc" nao de hien (da sap
nhap vao tinh khac) nen KHONG dua vao bang, tra None giong triet ly UNKNOWN
cua chuan_hoa_vendor()/khu_vuc_tu_ma_tinh(): "co ma nhung khong co trong bang
da xac nhan" PHAI hien ra de nguoi van hanh biet, KHONG doan/ngam dinh.
"""

# 34 tinh/thanh theo Nghi quyet 306/NQ-CP/2025 (yeu cau truc tiep user, danh
# sach day du - KHONG tu bo sung/doan them tinh nao ngoai danh sach nay).
TEN_TINH_THEO_MA: dict[str, str] = {
    "HNI": "Ha Noi",
    "HPG": "Hai Phong",
    "BNH": "Bac Ninh",
    "QNH": "Quang Ninh",
    "HYN": "Hung Yen",
    "NBH": "Ninh Binh",
    "TQG": "Tuyen Quang",
    "CBG": "Cao Bang",
    "LCU": "Lai Chau",
    "LCI": "Lao Cai",
    "TNN": "Thai Nguyen",
    "DBN": "Dien Bien",
    "LSN": "Lang Son",
    "SLA": "Son La",
    "PTO": "Phu Tho",
    "THA": "Thanh Hoa",
    "NAN": "Nghe An",
    "HTH": "Ha Tinh",
    "QTI": "Quang Tri",
    "HUE": "Hue",
    "DNG": "Da Nang",
    "QNI": "Quang Ngai",
    "GLI": "Gia Lai",
    "DLC": "Dak Lak",
    "KHA": "Khanh Hoa",
    "LDG": "Lam Dong",
    "DNI": "Dong Nai",
    "TNH": "Tay Ninh",
    "HCM": "TP Ho Chi Minh",
    "DTP": "Dong Thap",
    "AGG": "An Giang",
    "VLG": "Vinh Long",
    "CTO": "Can Tho",
    "CMU": "Ca Mau",
}


def ten_tinh_tu_ma(ma_tinh: str | None) -> str | None:
    """ma_tinh (vd "HNI") -> ten tinh day du, hoac None neu rong/None/ma
    KHONG nam trong 34 ma chinh thuc (vd ma CU chua sap nhap, hoac ma la).

    KHONG bao gio nem loi (cung triet ly voi chuan_hoa_vendor()/
    khu_vuc_tu_ma_tinh()) - dung tren duong doc danh sach/preview, 1 tram co
    ma la KHONG duoc lam hong ca response.
    """
    if not ma_tinh:
        return None
    return TEN_TINH_THEO_MA.get(ma_tinh)
