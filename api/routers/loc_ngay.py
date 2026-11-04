"""
Quy doi NGAY LICH GMT+7 -> cap moc UTC-aware cho cac endpoint listing co loc ngay.
Tu: V3a (GET /jobs/runs, 12/08); tach ra dung chung 13/08 khi GET /phieu can
Y HET luat loc ngay.

VI SAO TACH FILE RIENG thay vi de moi router tu viet:
Luat "+1 ngay vao den_ngay" la thu rat de viet dung o lan dau roi viet sai o
lan thu hai - va sai IM LANG: quen +1 ngay thi dong tao luc 09:30 ngay cuoi bi
loai khoi ket qua (09:30 > 00:00), man hinh VAN co du lieu nen khong ai nghi la
loc sai. Hai man hinh lich su (phieu / luot chay job) phai hieu chu "tu ngay X
den ngay Y" GIONG HET nhau, neu khong nguoi van hanh doi chieu 2 man hinh se
thay so lech ma khong hieu tai sao.

KHONG ap dung quy uoc "moi file tu dinh nghia _GMT7" (xem
application/evaluate_cr_use_case.py): quy uoc do danh cho HANG SO offset don
thuan (+7h, ai viet lai cung ra the). Con o day la 1 LUAT NGHIEP VU (nua khoang
[tu, den+1) + rang buoc tu <= den) - luat thi phai co dung 1 ban.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

# started_at/created_at luu UTC that (C1.4-fix9) nhung nguoi van hanh loc theo
# NGAY LICH VN. Quy doi tuong minh +7h, KHONG dung zoneinfo (may server khong co
# goi tzdata - xem application/evaluate_cr_use_case.py).
GMT7 = timezone(timedelta(hours=7))


def dau_ngay_gmt7(ngay: date) -> datetime:
    return datetime(ngay.year, ngay.month, ngay.day, tzinfo=GMT7)


def khoang_ngay_gmt7(
    tu_ngay: date | None, den_ngay: date | None
) -> tuple[datetime | None, datetime | None]:
    """(tu_ngay, den_ngay) NGAY LICH GMT+7 -> nua khoang [tu_moc, den_moc) aware.

    den_ngay duoc CONG 1 NGAY de ngay cuoi duoc tinh TRON VEN: repo so sanh
    `< den_moc` nen dong tao luc 23:59:59.999 ngay den_ngay van lot, khong phai
    xu ly do phan giai micro-giay.

    Hai dau mut DOC LAP nhau (khac /qos from+to phai di cap): "tu 01/08 den nay"
    va "truoc 01/08" deu la cach loc tu nhien o man hinh lich su, ep truyen ca
    cap chi bat FE phai bia 1 dau mut.

    Raise HTTPException 422 khi tu_ngay > den_ngay - chan ngay o tang router
    thay vi de repo tra ve rong: khoang ngay nguoc la LOI CUA REQUEST, tra rong
    se lam nguoi dung tuong "khong co du lieu" va di tim nham cho.
    """
    if tu_ngay is not None and den_ngay is not None and tu_ngay > den_ngay:
        raise HTTPException(status_code=422, detail="'tu_ngay' phai <= 'den_ngay'")

    tu_moc = None if tu_ngay is None else dau_ngay_gmt7(tu_ngay)
    den_moc = None if den_ngay is None else dau_ngay_gmt7(den_ngay) + timedelta(days=1)
    return tu_moc, den_moc
