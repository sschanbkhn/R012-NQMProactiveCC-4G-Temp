"""Phan loai loi khi CTS tu choi phieu: NGHIEP_VU hay KY_THUAT (B4, 02092026).

=== VAN DE ===
Bang lich su phieu dang hien MOI loi giong nhau: mot dong FAILED. Nhung 2 loai
loi doi hoi 2 hanh dong hoan toan khac nhau:

  NGHIEP_VU - CTS tu choi CO LY, he thong hoat dong DUNG.
              vd: "Bad Cell 4G-HDG116M13-HNI dang xu ly cua thang 202608"
              -> cell da co phieu dang xu ly trong thang. Nguoi van hanh KHONG
                 phai lam gi ca. Bao dev cung khong sua duoc gi.

  KY_THUAT  - he thong CHUNG TA hong: payload sai field, CTS tra 4xx validation,
              timeout, 5xx.
              vd: {"type":"...rfc9110...","title":"One or more validation errors"}
              -> phai bao dev, khong tu het.

De lan lon 2 loai nay thi: hoac nguoi truc di truy tung dong loi nghiep vu vo
ich, hoac loi ky thuat that bi chim giua dam loi nghiep vu va khong ai bao dev.

=== VI SAO SUY RA LUC DOC, KHONG THEM COT VAO DB ===
Da can nhac 2 cach:
  (1) Them cot cr_phieu.phan_loai_loi -> phai them 1 migration, va 115 dong CU
      van NULL tru khi viet script backfill (tu no lai la mot doan doan mo).
  (2) Suy tu error_message san co ngay luc doc (ham nay).
Chon (2) vi it xam lan hon han: khong migration, khong doi ghi, va AP DUNG NGAY
CA CHO DU LIEU CU - 4 dong "Bad Cell..." dang nam trong DB duoc phan loai dung
ma khong phai dong vao chung. Danh doi: khong loc/sort duoc theo phan loai o
tang SQL. Chap nhan duoc vi so dong FAILED rat nho (5/115) va man hinh loc theo
trang_thai truoc roi moi doc loi.
Neu sau nay can loc theo phan loai o tang DB thi moi them cot - luc do ham nay
thanh nguon backfill san co, khong phai viet lai tu dau.
"""

# Cac mau chuoi cho biet CTS tu choi VI LY DO NGHIEP VU.
# Doi chieu voi du lieu THAT trong cr_phieu (02092026): 4 dong deu dang
# "Bad Cell <ten cell> dang xu ly cua thang <YYYYMM>".
#
# So khop KHONG DAU va viet thuong: message tu CTS co dau tieng Viet ("dang xu
# ly cua thang"), ma khong phai moi nguon deu giu nguyen dau khi di qua log/
# encoding. Bat theo cum khong dau "bad cell" + "thang" la du dac trung, va
# khong vo khi CTS doi cach bo dau.
_MAU_NGHIEP_VU = (
    "bad cell",
    "dang xu ly cua thang",
    "đang xử lý của tháng",
)


# 3 trang thai "job CO Y KHONG xuat" - LUON la NGHIEP_VU, khong doc
# error_message (sua 04092026).
#
# VI SAO PHAI XET TRANG THAI TRUOC: 3 trang thai nay KHONG HE POST len CTS -
# cell bi loai TRUOC buoc goi gateway. Chung khong the co loi ky thuat, vi
# khong co lan goi nao de hong. error_message cua chung la GHI CHU cua he
# thong ("Ngoai top 10 cell te nhat...", "QoS chi co 3/7 ngay...") chu khong
# phai loi tu CTS.
#
# Truoc khi sua: chung roi vao nhanh mac dinh KY_THUAT -> FE ve Tag do "Loi ky
# thuat" cho mot QUYET DINH BINH THUONG cua he thong. Nguoi truc di truy 1 loi
# khong ton tai, va lam nhoe mat cac dong KY_THUAT that.
_TRANG_THAI_LUON_NGHIEP_VU = frozenset(
    {
        "KHONG_XUAT_DA_CO_PHIEU_THANG",
        "KHONG_XUAT_VUOT_GIOI_HAN",
        "KHONG_XUAT_THIEU_DU_LIEU",
        # KHONG_XUAT_HET_LUOT_THU CO Y KHONG nam trong day: cell do da POST
        # that va that bai XUAT_PHIEU_MAX_RETRY lan, error_message cua no la
        # LOI THAT tu CTS - phai phan loai theo noi dung nhu moi loi khac.
    }
)


def phan_loai_loi_cts(error_message: str | None, trang_thai: str | None = None) -> str | None:
    """None khi khong co loi; 'NGHIEP_VU' | 'KY_THUAT' khi co.

    trang_thai (them 04092026): 3 trang thai KHONG_XUAT_* la QUYET DINH cua he
    thong, khong phai loi - xem _TRANG_THAI_LUON_NGHIEP_VU. Tham so co MAC DINH
    None nen moi cho goi cu khong phai sua theo.

    Mac dinh la KY_THUAT chu KHONG phai NGHIEP_VU: mot loi chua nhan dang duoc
    thi phai cho nguoi ta di xem. Doan nham thanh NGHIEP_VU se lam loi that bi
    im lang - dung kieu that bai da khien 8 ngay khong ai biet job hong.
    """
    if trang_thai in _TRANG_THAI_LUON_NGHIEP_VU:
        # Xet TRUOC ca "khong co error_message": 3 trang thai nay van la
        # NGHIEP_VU ke ca khi cot error_message rong, vi ban than trang thai da
        # noi day du y nghia.
        return "NGHIEP_VU"
    if not error_message:
        return None
    thap = error_message.lower()
    if any(m in thap for m in _MAU_NGHIEP_VU):
        return "NGHIEP_VU"
    return "KY_THUAT"
