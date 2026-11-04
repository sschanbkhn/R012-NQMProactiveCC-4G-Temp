"""
geo_utils.py - ham hinh hoc THUAN dung cho ban do xem truoc CR (BUOC 4c,
10/10/2026, yeu cau truc tiep user):
  - sap_theo_goc(): sap 1 danh sach diem theo GOC CUC quanh 1 tam, de ve
    thanh duong KHONG TU CAT (vd vong L1/L2 quanh tram X).
  - duong_bao_hinh_sao() (THEM 10/10/2026, yeu cau truc tiep user, THAY THE
    convex hull cho "duong bao vung bi anh huong" - xem dac ta day du o ham.
    BO convex hull (ham bao_loi() cu, da XOA) vi hull co the BO SOT diem LOM
    nam trong long hull, trong khi user muon TAT CA tram bi anh huong deu la
    1 dinh tren duong bao).

Toa do xu ly nhu MAT PHANG (lon=x, lat=y) - xap xi HOP LE cho pham vi dia ly
NHO (ban kinh 15km quanh 1 tram, CUNG gia dinh voi domain/services/
ho_delaunay.py::phan_lop_delaunay() khi chieu toa do ve km phang) - KHONG
dung cho pham vi toan cau/lien luc dia.
"""

from math import atan2, cos, pi, radians

Diem = tuple[float, float]  # (lat, lon)


def sap_theo_goc(diem_list: list, tam: Diem, key=lambda d: d):
    """Tra LAI danh sach `diem_list` (THU TU MOI, GIU NGUYEN TUNG PHAN TU -
    KHONG chi lay toa do), sap theo goc cuc (atan2) quanh `tam` - noi cac
    phan tu THEO THU TU nay se tao 1 duong KHONG TU CAT (dieu kien can de ve
    1 vong khep kin "sach" tren ban do, vd L1/L2 quanh X).

    `key`: ham rut (lat,lon) tu 1 phan tu cua diem_list - mac dinh la CHINH
    phan tu do (dung khi diem_list la mang (lat,lon) thuan, xem test). Cho
    phep sap cac object/dict GIAU toa do (vd TramPhanLop, dict tram) ma
    KHONG can convert qua lai 2 chieu.

    Chieu lon ve km phang qua cos(lat tam) (nhu ho_delaunay.py) truoc khi
    tinh goc - tranh sai lech o vi do cao (1 do kinh o VN ~ 102km, khac 1 do
    vi ~111km, bo qua se lam goc bi "meo" nhe nhung khong anh huong tinh
    KHONG-TU-CAT, chi lam cho TRON DEU hon ve mat thi giac)."""
    lat0, lon0 = tam

    def _goc(phan_tu) -> float:
        lat, lon = key(phan_tu)
        dx = (lon - lon0) * cos(radians(lat0))
        dy = lat - lat0
        return atan2(dy, dx)

    return sorted(diem_list, key=_goc)


def duong_bao_hinh_sao(x: dict, diem_list: list[dict], key=lambda d: (d["lat"], d["lon"])) -> dict:
    """Duong bao "vung bi anh huong" quanh X - DA GIAC HINH SAO (star-shaped
    polygon THEO X: moi dinh "nhin thay" X khong bi canh nao khac che), THAY
    THE bao_loi()/convex hull cho muc dich nay (THEM 10/10/2026, yeu cau truc
    tiep user - "X o trong, MOI tram bi anh huong la 1 dinh nam xung quanh,
    noi thanh 1 vong khep kin" - KHAC convex hull: convex hull co the BO SOT
    diem LOM (nam trong long hull) ma user muon THAY TAT CA tram bi anh huong
    deu la 1 dinh tren duong bao).

    diem_list: moi phan tu la 1 "diem" GIU NGUYEN (dict tram/cell bi anh
    huong, da LOC BO cell/tram KHONG ro vi tri boi caller - ham nay KHONG tu
    loc). `key` rut (lat,lon) tu phan tu - mac dinh doc truc tiep d["lat"]/
    d["lon"] (dict tram_bi_anh_huong/cell CRAN deu co san 2 field nay, xem
    application/trigger_cr_use_case.py::_xay_du_lieu_ban_do()).

    Thuat toan:
    1. < 3 diem: KHONG co polygon (can >= 3 dinh moi tao duoc 1 vung kin co
       dien tich) - tra "doan" (list cac diem, FE tu ve 1 doan thang rieng tu
       X den TUNG diem - KHONG noi cac diem voi nhau).
    2. >= 3 diem: tinh GOC CUC (atan2, CUNG quy uoc phang voi sap_theo_goc())
       cua tung diem quanh X, sap TANG DAN; TRUNG goc -> diem GAN X hon dung
       TRUOC (tie-break khoang cach, khong anh huong tinh khong-tu-cat).
    3. Khoang trong GOC (gap giua 2 diem LIEN TIEP theo thu tu tren, CA gap
       "vong" tu diem cuoi ve diem dau) LON NHAT: neu > 180 do (pi radian),
       NGHIA LA co 1 "mang" rong > nua hinh tron KHONG co diem nao bao quanh
       X huong do - chen X lam 1 DINH ngay giua khoang trong do (tao hinh
       quat huong ve X) de duong bao KHONG "cat ngang" qua X ma bam theo
       huong thuc te co du lieu. x_tren_vien=True bao caller biet X DA thanh
       1 dinh cua polygon (KHAC truong hop thuong X luon nam BEN TRONG).
    4. Nguoc lai (gap lon nhat <= 180 do): polygon gom DUNG CAC diem da sap,
       KHONG them X - X tu nhien nam ben trong (tinh chat hinh sao).
    Tra ve: {"polygon": list[diem+toa do goc, hoac None], "doan": list[diem]
    (rong neu co polygon), "x_tren_vien": bool}. Polygon KHONG tu lap dinh dau
    o cuoi (KHAC bao_loi()) - FE tu noi dinh cuoi ve dinh dau de khep vong."""
    if len(diem_list) < 3:
        return {"polygon": None, "doan": list(diem_list), "x_tren_vien": False}

    x_lat, x_lon = key(x)

    def _goc_va_khoang_cach(d) -> tuple[float, float]:
        lat, lon = key(d)
        dx = (lon - x_lon) * cos(radians(x_lat))
        dy = lat - x_lat
        return atan2(dy, dx), dx * dx + dy * dy

    da_sap = sorted(diem_list, key=_goc_va_khoang_cach)
    gocs = [_goc_va_khoang_cach(d)[0] for d in da_sap]

    n = len(da_sap)
    khoang_trong: list[tuple[float, int]] = []
    for i in range(n):
        ke = (i + 1) % n
        gap = gocs[ke] - gocs[i]
        if ke == 0:  # gap "vong" tu diem cuoi ve diem dau - cong them 1 vong tron day
            gap += 2 * pi
        khoang_trong.append((gap, i))
    gap_lon_nhat, vi_tri = max(khoang_trong)

    x_tren_vien = gap_lon_nhat > pi
    if x_tren_vien:
        polygon = da_sap[: vi_tri + 1] + [{**x, "la_x": True}] + da_sap[vi_tri + 1 :]
    else:
        polygon = list(da_sap)

    return {"polygon": polygon, "doan": [], "x_tren_vien": x_tren_vien}
