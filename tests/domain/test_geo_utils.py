"""
Unit test cho domain/services/geo_utils.py (sap_theo_goc, duong_bao_hinh_sao).
Tu: BUOC 4c (10/10/2026, yeu cau truc tiep user).
"""

from math import cos, radians, sin

from domain.services.geo_utils import duong_bao_hinh_sao, sap_theo_goc


def test_sap_theo_goc_4_diem_quanh_tam_ra_vong_khong_tu_cat():
    tam = (21.0, 105.0)
    # 4 diem o 4 huong (Dong/Bac/Tay/Nam) - truyen vao THU TU LON XON.
    dong = (21.0, 105.1)
    bac = (21.1, 105.0)
    tay = (21.0, 104.9)
    nam = (20.9, 105.0)
    ket_qua = sap_theo_goc([bac, nam, dong, tay], tam)

    # Vong phai lien tuc theo 1 CHIEU (CCW hoac CW), KHONG nhay qua lai -
    # kiem tra bang cach xac nhan thu tu la 1 trong 2 hoan vi vong tron hop
    # le (dong->bac->tay->nam hoac nguoc lai), bat dau tu bat ky diem nao.
    ten = {id(dong): "dong", id(bac): "bac", id(tay): "tay", id(nam): "nam"}
    thu_tu = [ten[id(d)] for d in ket_qua]
    vong_1 = ["dong", "bac", "tay", "nam"]
    vong_2 = list(reversed(vong_1))
    # Xoay thu_tu ve bat dau tu "dong" de so sanh vong tron.
    idx = thu_tu.index("dong")
    xoay = thu_tu[idx:] + thu_tu[:idx]
    assert xoay == vong_1 or xoay == vong_2


def test_sap_theo_goc_giu_nguyen_so_luong_diem():
    tam = (21.0, 105.0)
    diem_list = [(21.01, 105.01), (20.99, 105.02), (21.02, 104.98)]
    ket_qua = sap_theo_goc(diem_list, tam)
    assert sorted(ket_qua) == sorted(diem_list)


def test_sap_theo_goc_voi_key_giu_nguyen_object_goc():
    # key= dung khi muon sap 1 danh sach dict/object (giu nguyen ca object,
    # khong chi toa do) - dung cho vong L1/L2 (TramPhanLop/dict tram).
    tam = (21.0, 105.0)
    items = [
        {"ten": "bac", "lat": 21.1, "lon": 105.0},
        {"ten": "nam", "lat": 20.9, "lon": 105.0},
        {"ten": "dong", "lat": 21.0, "lon": 105.1},
    ]
    ket_qua = sap_theo_goc(items, tam, key=lambda d: (d["lat"], d["lon"]))
    assert {d["ten"] for d in ket_qua} == {"bac", "nam", "dong"}
    assert all(isinstance(d, dict) for d in ket_qua)


_X = {"tram_id": "X", "ten": "4G-XTEST-HNI", "lat": 21.0, "lon": 105.0}


def _diem_cach_x(goc_do: float, km: float = 1.0, **extra) -> dict:
    # 1 diem cach X theo GOC (do, 0=dong, tang CCW giong atan2) va khoang
    # cach (km, xap xi phang nhu geo_utils.py) - dung de dung bo test co
    # hinh hoc BIET TRUOC (goc/khoang trong) ma KHONG can toa do GPS thuc.
    rad = radians(goc_do)
    dx_deg = (km / 111.32) * cos(rad) / cos(radians(_X["lat"]))
    dy_deg = (km / 111.32) * sin(rad)
    return {"lat": _X["lat"] + dy_deg, "lon": _X["lon"] + dx_deg, **extra}


def _doan_thang_cat_nhau(p1, p2, p3, p4) -> bool:
    # Kiem tra 2 doan (p1,p2) va (p3,p4) CAT NHAU (orientation-based, chuan) -
    # dung de xac nhan polygon "khong tu cat" (TAT CA cap canh KHONG LIEN KE
    # deu KHONG cat nhau).
    def _huong(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    d1, d2 = _huong(p1, p2, p3), _huong(p1, p2, p4)
    d3, d4 = _huong(p3, p4, p1), _huong(p3, p4, p2)
    return d1 != d2 and d3 != d4


def _polygon_khong_tu_cat(dinh_list: list[tuple[float, float]]) -> bool:
    n = len(dinh_list)
    for i in range(n):
        for j in range(i + 1, n):
            # Bo qua canh LIEN KE (chung 1 dinh) - 2 canh canh nhau LUON
            # "cat" tai dinh chung, khong tinh la tu cat.
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            a1, a2 = dinh_list[i], dinh_list[(i + 1) % n]
            b1, b2 = dinh_list[j], dinh_list[(j + 1) % n]
            if _doan_thang_cat_nhau(a1, a2, b1, b2):
                return False
    return True


def _diem_trong_polygon(diem: tuple[float, float], dinh_list: list[tuple[float, float]]) -> bool:
    # Ray casting chuan (lon=x, lat=y).
    x, y = diem[1], diem[0]
    n = len(dinh_list)
    trong = False
    for i in range(n):
        x1, y1 = dinh_list[i][1], dinh_list[i][0]
        x2, y2 = dinh_list[(i + 1) % n][1], dinh_list[(i + 1) % n][0]
        if (y1 > y) != (y2 > y):
            x_cat = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cat:
                trong = not trong
    return trong


def test_hinh_sao_8_diem_bao_quanh_8_dinh_khong_tu_cat_x_ben_trong():
    diem_list = [_diem_cach_x(45 * i, tram_id=str(i)) for i in range(8)]
    ket_qua = duong_bao_hinh_sao(_X, diem_list)

    assert ket_qua["x_tren_vien"] is False
    assert ket_qua["doan"] == []
    polygon = ket_qua["polygon"]
    assert len(polygon) == 8
    dinh_toa_do = [(d["lat"], d["lon"]) for d in polygon]
    assert _polygon_khong_tu_cat(dinh_toa_do)
    assert _diem_trong_polygon((_X["lat"], _X["lon"]), dinh_toa_do)


def test_hinh_sao_3_diem_cung_phia_chen_x_lam_dinh():
    # 3 diem trong cung 1 cung 90 do (0/30/60) - khoang trong CON LAI (tu 60
    # do vong ve 0 do, qua phia doi dien) = 300 do > 180 -> chen X.
    diem_list = [_diem_cach_x(0, tram_id="a"), _diem_cach_x(30, tram_id="b"), _diem_cach_x(60, tram_id="c")]
    ket_qua = duong_bao_hinh_sao(_X, diem_list)

    assert ket_qua["x_tren_vien"] is True
    polygon = ket_qua["polygon"]
    assert len(polygon) == 4
    so_dinh_la_x = [d for d in polygon if d.get("la_x")]
    assert len(so_dinh_la_x) == 1
    assert so_dinh_la_x[0]["lat"] == _X["lat"]
    assert so_dinh_la_x[0]["lon"] == _X["lon"]


def test_hinh_sao_2_diem_chi_tra_doan_khong_polygon():
    diem_list = [_diem_cach_x(0, tram_id="a"), _diem_cach_x(90, tram_id="b")]
    ket_qua = duong_bao_hinh_sao(_X, diem_list)

    assert ket_qua["polygon"] is None
    assert ket_qua["x_tren_vien"] is False
    assert {d["tram_id"] for d in ket_qua["doan"]} == {"a", "b"}
