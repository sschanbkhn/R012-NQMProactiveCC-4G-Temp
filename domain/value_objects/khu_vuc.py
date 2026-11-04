"""
KhuVuc - KV1/KV2/KV3 cho tram, suy TU MA TINH (khong phai cot rieng trong RIMS
- RIMS KHONG co khai niem khu vuc). Quyet dinh 04/10/2026.

=== TAI SAO SUY TU MA TINH, KHONG PHAI VUNG KINH TE ===
KV1 = NOC1 (Bac), KV2 = NOC2 (Nam), KV3 = NOC3 (Trung) - day la RANH GIOI VAN
HANH cua 3 trung tam dieu hanh mang (NOC), KHONG PHAI ranh gioi 8 vung kinh te
- xa hoi chinh thuc. Vi du that: Lam Dong (sau sap nhap, gom Dak Nong + Lam
Dong + Binh Thuan cu) xep KV2 (Nam) vi CA 3 tinh cu do deu dang do NetAct 10
(thuoc NOC2) quan ly - neu xep theo vung kinh te (Tay Nguyen/Dong Nam Bo/Nam
Trung Bo) se SAI vi khong khop voi ai dang van hanh mang that.

Nguon bang anh xa: 34 tinh/thanh theo Nghi quyet 306/NQ-CP/2025 (sap nhap
tinh), DOI CHIEU VOI NetAct THAT de biet tinh nao NOC nao dang quan ly - KHONG
suy doan tu dia ly/vung kinh te.

=== TAI SAO GIU CA MA CU LAN MA MOI ===
tram.ma_tinh (models/tram.py) la VARCHAR TU DO, KHONG rang buoc - RIMS co the
con tra ma tinh CU (truoc sap nhap) cho tram chua duoc cap nhat, hoac ma MOI
cho tram da cap nhat. Giu CA 2 bang tranh tram "bien mat" khoi KV nao chi vi
RIMS chua dong bo kip theo sap nhap hanh chinh - giong tinh than chuan_hoa_vendor()
(domain/value_objects/vendor.py): KHONG doan, chi khop dung bang da xac nhan.

KHONG tu doan KV cho ma la (khac tap da liet ke) - tra None, giong UNKNOWN cua
Vendor: "co ma nhung he thong khong biet" PHAI hien ra duoc de nguoi van hanh
phat hien, khong duoc ngam dinh vao 1 KV nao.
"""

KV1 = "KV1"
KV2 = "KV2"
KV3 = "KV3"

# Bang anh xa ma_tinh -> KV (04/10/2026, xac nhan voi user). Gom CA ma MOI
# (sau Nghi quyet 306/NQ-CP/2025) VA ma CU (truoc sap nhap) cho CUNG 1 tinh
# hop nhat, vi RIMS tra ca 2 dang tuy tram da/chua dong bo.
_MA_TINH_THEO_KV: dict[str, str] = {
    # KV1 - NOC1 (Bac)
    "HNI": KV1, "HPG": KV1, "HDG": KV1, "BNH": KV1, "BGG": KV1, "QNH": KV1,
    "HYN": KV1, "TBH": KV1, "NBH": KV1, "HNM": KV1, "NDH": KV1, "TQG": KV1,
    "HGG": KV1, "CBG": KV1, "LCU": KV1, "LCI": KV1, "YBI": KV1, "TNN": KV1,
    "BKN": KV1, "DBN": KV1, "LSN": KV1, "SLA": KV1, "PTO": KV1, "HBH": KV1,
    "VPC": KV1,
    # KV2 - NOC2 (Nam)
    "HCM": KV2, "BDG": KV2, "VTU": KV2, "DNI": KV2, "BPC": KV2, "TNH": KV2,
    "LAN": KV2, "DTP": KV2, "TGG": KV2, "AGG": KV2, "KGG": KV2, "VLG": KV2,
    "BTE": KV2, "TVH": KV2, "CTO": KV2, "STG": KV2, "HUG": KV2, "CMU": KV2,
    "BLU": KV2,
    # Lam Dong (gop Dak Nong + Lam Dong + Binh Thuan cu) - xem docstring dau
    # file: xep KV2 vi NetAct 10 (NOC2) dang quan ly ca 3 tinh cu, KHONG theo
    # vung kinh te (Lam Dong/Dak Nong thuoc Tay Nguyen, Binh Thuan thuoc Nam
    # Trung Bo neu xep theo dia ly se SAI voi thuc te van hanh).
    "LDG": KV2, "DNO": KV2, "BTN": KV2,
    # KV3 - NOC3 (Trung)
    "THA": KV3, "NAN": KV3, "HTH": KV3, "QTI": KV3, "QBH": KV3, "HUE": KV3,
    "DNG": KV3, "QNM": KV3, "QNI": KV3, "KTM": KV3, "GLI": KV3, "BDH": KV3,
    "DLK": KV3, "PYN": KV3, "KHA": KV3, "NTN": KV3,
    # DLC = Dak Lak MOI (gop Dak Lak cu + Phu Yen cu) - THEM 04/10/2026, xac
    # nhan bang SQL that: SELECT right(tram_name,3) ... WHERE ma_tinh='DLC'
    # ra DUNG 2 hau to chiem da so la DLK (1.231 tram) va PYN (529 tram) - ca
    # 2 ma cu nay DA CO SAN trong bang (KV3) nen DLC xep KV3 la nhat quan,
    # khong doan - la mot KET QUA DO DUOC, khong phai suy luan dia ly.
    "DLC": KV3,
}


def ma_tinh_theo_khu_vuc(khu_vuc_list: list[str]) -> list[str]:
    """Chieu NGUOC: 1 hoac nhieu KV -> toan bo ma_tinh (CA cu lan moi) thuoc
    cac KV do. Dung cho loc GET /stations o TANG DB (ma_tinh IN (...)) - PHAI
    suy tu CUNG 1 bang _MA_TINH_THEO_KV voi khu_vuc_tu_ma_tinh() (mot nguon
    su that duy nhat), tranh truong hop 2 bang lech nhau theo thoi gian neu
    viet tay rieng 1 bang nguoc.
    """
    return [ma for ma, kv in _MA_TINH_THEO_KV.items() if kv in khu_vuc_list]


def khu_vuc_tu_ma_tinh(ma_tinh: str | None) -> str | None:
    """ma_tinh (vd "HNI") -> "KV1"/"KV2"/"KV3", hoac None neu khong xac dinh
    duoc (ma_tinh rong/None, hoac ma LA khong nam trong bang da xac nhan).

    KHONG bao gio nem loi (giong chuan_hoa_vendor()) - ham nay nam tren duong
    DOC cua GET /stations, 1 lan/dong tra ve; 1 tram co ma la KHONG duoc lam
    hong ca trang danh sach.

    KHONG tu chuan hoa (strip/upper) nhu chuan_hoa_vendor(): ma_tinh la MA
    CHUAN hoa san tu truoc (xem station_schemas.py - "doc THANG cot, KHONG
    suy tu hau to ten tram"), khac ten_thiet_bi (chuoi nguoi nhap tu do) -
    neu RIMS tra ma_tinh le (vd chu thuong) thi day la DAU HIEU can dieu tra
    rieng, KHONG nen am tham "sua ho" roi ghep nham KV.
    """
    if not ma_tinh:
        return None
    return _MA_TINH_THEO_KV.get(ma_tinh)
