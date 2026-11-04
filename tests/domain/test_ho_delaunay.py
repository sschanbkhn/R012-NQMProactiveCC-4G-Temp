"""
Unit test cho domain/services/ho_delaunay.py::phan_lop_delaunay() +
phan_loai_toa_do(). Tu: quyet dinh 06-08/10/2026 + SUA 08/10/2026 lan 1 (gop
cum site theo ma_csht, moc loc canh theo X, fallback khi X khong co canh) +
SUA 08/10/2026 lan 2 (XU LY TRAM TOA_DO_DUNG_CHUNG/CRAN - THAY gop cum theo
ma_csht bang gop cum theo SO SITE tach tu ten, loai tram TOA_DO_DUNG_CHUNG
khoi tap diem).

Chien luoc test: Delaunay/alpha-shape la thuat toan hinh hoc - kho DOAN TAY
chinh xac tung canh cua tam giac hoa cho 1 cau hinh diem bat ky. Thay vi
doan, test tap trung vao CAC BAT BIEN da xac nhan DUNG qua thiet ke.
"""

import itertools
from math import cos, radians

from domain.services.ho_delaunay import (
    L1_CUNG_SITE,
    TIN_CAY,
    TOA_DO_DUNG_CHUNG,
    TramDiem,
    _so_site,
    phan_loai_toa_do,
    phan_lop_delaunay,
)

LAT0, LON0 = 21.000, 105.800
KM_PER_DEG_LAT = 111.32

# Dam bao MOI diem mac dinh (khong chi dinh tram_name) co SO SITE RIENG,
# KHONG VO TINH trung voi diem khac trong CUNG 1 test (tranh gop cum ngoai y
# muon) - cac test CAN gop cum/xung dot site PHAI tu chi dinh tram_name.
_counter = itertools.count()


def _site_rieng() -> str:
    n = next(_counter)
    return f"4G-SIT{n:03d}A-HNI"


def _diem_cach_x_km(tram_id: str, bac_km: float, dong_km: float, tram_name: str | None = None) -> TramDiem:
    lat = LAT0 + bac_km / KM_PER_DEG_LAT
    lon = LON0 + dong_km / (KM_PER_DEG_LAT * cos(radians(LAT0)))
    return TramDiem(tram_id=tram_id, tram_name=tram_name or _site_rieng(), lat=lat, lon=lon)


def _diem_huong_km(tram_id: str, huong_do: float, km: float, tram_name: str | None = None) -> TramDiem:
    # Dat diem theo HUONG (do, 0=bac, 90=dong, nhu la ban) + khoang cach (km) -
    # tien hon _diem_cach_x_km() cho cac test can dieu khien CHINH XAC huong
    # (vd tam giac "manh" gan nhu thang hang qua 1 huong cu the).
    from math import sin
    bac_km = km * cos(radians(huong_do))
    dong_km = km * sin(radians(huong_do))
    return _diem_cach_x_km(tram_id, bac_km, dong_km, tram_name)


def _x(tram_name: str | None = None) -> TramDiem:
    return TramDiem(tram_id="X", tram_name=tram_name or _site_rieng(), lat=LAT0, lon=LON0)


def _phan_loai(*nhom_diem: list[TramDiem]) -> dict[str, str]:
    tat_ca = [d for nhom in nhom_diem for d in nhom]
    return phan_loai_toa_do(tat_ca)


# === phan_loai_toa_do() ===


def test_phan_loai_tram_don_khong_trung_toa_do_ai_la_tin_cay():
    a = TramDiem("A", "4G-SIT001A-HNI", LAT0, LON0)
    assert phan_loai_toa_do([a]) == {"A": TIN_CAY}


def test_phan_loai_trung_toa_do_cung_so_site_la_tin_cay():
    # 2 tram CUNG site vat ly (vd nhieu thiet bi), CUNG toa do, so site "SIT001"
    # GIONG NHAU (chu suffix M/B khac) - TIN_CAY ca 2.
    a = TramDiem("A", "4G-SIT001M-HNI", LAT0, LON0)
    b = TramDiem("B", "4G-SIT001B-HNI", LAT0, LON0)
    assert phan_loai_toa_do([a, b]) == {"A": TIN_CAY, "B": TIN_CAY}


def test_phan_loai_trung_toa_do_khac_so_site_la_dung_chung_ca_hai():
    # 2 tram KHAC site, CUNG toa do - CA HAI bi coi la TOA_DO_DUNG_CHUNG (toa
    # do nay khong con rieng cho 1 site, bang chung CRAN - xem dac ta module).
    a = TramDiem("A", "4G-SIT001M-HNI", LAT0, LON0)
    b = TramDiem("B", "4G-SIT002M-HNI", LAT0, LON0)
    assert phan_loai_toa_do([a, b]) == {"A": TOA_DO_DUNG_CHUNG, "B": TOA_DO_DUNG_CHUNG}


def test_phan_loai_ten_khong_tach_duoc_so_site_trong_nhom_trung_la_dung_chung():
    # B co ten KHONG khop regex (khong tach duoc so site) nhung nam trong
    # nhom trung toa do (>=2 tram) - PHAI coi CHINH B la TOA_DO_DUNG_CHUNG
    # (than trong, dac ta 08/10/2026 lan 2 - khong the xac minh quan he cua
    # B). A KHONG bi anh huong - so site cua A TU NHAT QUAN voi MOI tram
    # KHAC co xac dinh duoc site trong nhom (o day khong co tram nao khac co
    # site xac dinh ngoai A) -> A van TIN_CAY.
    a = TramDiem("A", "4G-SIT001M-HNI", LAT0, LON0)
    b = TramDiem("B", "KHONGTACHDUOCSOSITE", LAT0, LON0)
    ket_qua = phan_loai_toa_do([a, b])
    assert ket_qua["B"] == TOA_DO_DUNG_CHUNG
    assert ket_qua["A"] == TIN_CAY


def test_phan_loai_tram_toa_do_rong_khong_co_trong_ket_qua():
    a = TramDiem("A", "4G-SIT001M-HNI", 0.0, 0.0)
    assert phan_loai_toa_do([a]) == {}


# === _SITE_RE / phan_loai_toa_do() - ma khu vuc co SO (Q01/Q08, HCM) ===
# THEM 15/10/2026 (yeu cau truc tiep user, "SUA TIEP _SITE_RE") - _SITE_RE
# truoc day doi khu vuc la [A-Z]{2,4} (CHU THUAN), nen tram HCM dang
# "Q01219M-HCM" (khu vuc "Q01" = chu + so, ma quan) KHONG tach duoc so site
# -> neu trung toa do voi tram khac se BI OAN thanh TOA_DO_DUNG_CHUNG (CRAN).
# SUA dung chung _MA_KHU_VUC voi domain/services/loai_tram.py.


def test_so_site_ma_khu_vuc_co_so_q01_tach_dung():
    assert _so_site("4G-Q01219M-HCM") == "Q01219"
    assert _so_site("4G-Q08096B-HCM") == "Q08096"
    assert _so_site("4G-BDH288M-HNI") == "BDH288"  # ma khu vuc CHU THUAN van dung nhu cu


def test_phan_loai_q01_cung_site_khac_chu_loai_cung_toa_do_la_tin_cay():
    # 4G-Q01219M-HCM va 4G-Q01219B-HCM - CUNG site (Q01219), chi khac chu
    # loai (M/B) - CUNG toa do PHAI la TIN_CAY (khong phai CRAN).
    a = TramDiem("A", "4G-Q01219M-HCM", LAT0, LON0)
    b = TramDiem("B", "4G-Q01219B-HCM", LAT0, LON0)
    assert phan_loai_toa_do([a, b]) == {"A": TIN_CAY, "B": TIN_CAY}


def test_phan_loai_q01_khac_site_cung_toa_do_la_dung_chung():
    # 4G-Q01219M-HCM va 4G-Q01225M-HCM - KHAC site (219 vs 225) - CUNG toa do
    # PHAI la TOA_DO_DUNG_CHUNG (CRAN that).
    a = TramDiem("A", "4G-Q01219M-HCM", LAT0, LON0)
    b = TramDiem("B", "4G-Q01225M-HCM", LAT0, LON0)
    assert phan_loai_toa_do([a, b]) == {"A": TOA_DO_DUNG_CHUNG, "B": TOA_DO_DUNG_CHUNG}


# === phan_lop_delaunay() - gop cum theo SO SITE (SUA 08/10/2026 lan 2) ===


def test_cung_so_site_luon_l1_bat_ke_delaunay():
    # SUA 16/10/2026 (yeu cau truc tiep user, "VONG L1 KHONG LAY TRAM CUNG
    # SITE") - tram CUNG SITE voi X gio mang layer rieng "L1_CUNG_SITE" (van
    # la L1 ve thuat toan chon cell - domain/services/ho_cell_selector.py da
    # xu ly GIONG HET "L1", xem test rieng o tests/domain/test_ho_cell_selector.py),
    # CHI khac TEN de application/trigger_cr_use_case.py loai no khoi
    # duong_bao_hinh_sao() (vong ve tren ban do).
    x = _x("4G-SIT001M-HNI")
    cung_cum = TramDiem(tram_id="A", tram_name="4G-SIT001B-HNI", lat=LAT0, lon=LON0)
    phan_loai = _phan_loai([x], [cung_cum])
    ket_qua = phan_lop_delaunay(x, [cung_cum], phan_loai)
    assert len(ket_qua) == 1
    assert ket_qua[0].tram_id == "A"
    assert ket_qua[0].layer == L1_CUNG_SITE
    assert ket_qua[0].km == 0.0


def test_khac_so_site_cung_toa_do_bi_loai_hoan_toan_khoi_tap_diem():
    # P va Q trung toa do VOI NHAU (khac site) - O DAU KHAC X, khong lien
    # quan gi den X ve mat dia ly - nhung CA HAI bi phan loai TOA_DO_DUNG_CHUNG
    # (xung dot voi nhau) va PHAI bi loai khoi tap diem Delaunay cua X, dung
    # khi P o gan X hon MOI ung vien khac (se la L1 neu KHONG bi loai).
    x = _x()
    p = _diem_cach_x_km("P", 0.05, 0, tram_name="4G-SIT010M-HNI")  # 50m - gan nhat
    q = TramDiem("Q", "4G-SIT011M-HNI", p.lat, p.lon)  # trung toa do voi P, khac site
    filler = [_diem_cach_x_km(f"F{i}", 1.0 * (i + 1), 0.5 * (i + 1)) for i in range(4)]

    phan_loai = _phan_loai([x], [p, q], filler)
    ket_qua = phan_lop_delaunay(x, [p, q, *filler], phan_loai)

    theo_id = {t.tram_id for t in ket_qua}
    assert "P" not in theo_id
    assert "Q" not in theo_id
    # Cac filler (TIN_CAY, khong xung dot) van duoc xu ly binh thuong.
    assert theo_id.issubset({f"F{i}" for i in range(4)})


def test_x_la_toa_do_dung_chung_tra_rong_ngay():
    # X xung dot toa do voi 1 tram khac site - X tro thanh TOA_DO_DUNG_CHUNG
    # -> KHONG tinh L1/L2 (tra [] NGAY), DU co ung vien hop le gan ben.
    x = _x("4G-SIT001M-HNI")
    doi_thu = TramDiem("DT", "4G-SIT002M-HNI", LAT0, LON0)  # trung toa do, khac site -> X thanh DUNG_CHUNG
    gan = _diem_cach_x_km("GAN", 0.1, 0)

    phan_loai = _phan_loai([x], [doi_thu], [gan])
    ket_qua = phan_lop_delaunay(x, [doi_thu, gan], phan_loai)

    assert ket_qua == []


def test_khong_trung_toa_do_ai_khong_tu_dong_l1():
    # 2 tram KHAC site, KHAC toa do (khong trung ai, cach 10m - DU xa de khong
    # bi lam tron trung 6 so le) - CA HAI la TIN_CAY (luat phan loai: khong
    # trung toa do -> TIN_CAY), nhung KHONG CUNG cum (khac site) - fallback vi
    # qua it diem (2 < 4), van la L1 vi la cum gan nhat.
    x = _x()
    khac_site = _diem_cach_x_km("B", 0.01, 0)  # 10m ve phia bac, site rieng (mac dinh)
    phan_loai = _phan_loai([x], [khac_site])
    ket_qua = phan_lop_delaunay(x, [khac_site], phan_loai)
    assert len(ket_qua) == 1
    assert ket_qua[0].layer == "L1"  # qua fallback (chi 1 ung vien, < 4 diem)


def test_tram_ibs_bi_loai_khoi_tap_diem_khong_bao_gio_la_l1():
    # THEM 12/10/2026 (yeu cau truc tiep user, "L1/L2 CHI TINH VOI TRAM MACRO")
    # - tram chu cai loai "F" (IBS) RAT GAN X (10m, le ra la L1 chac chan qua
    # fallback nhu test_khong_trung_toa_do_ai_khong_tu_dong_l1) nhung PHAI bi
    # loai HOAN TOAN khoi ket qua - IBS khong duoc lam moc hinh hoc.
    x = _x()
    ibs_gan = _diem_cach_x_km("IBS1", 0.01, 0, tram_name="4G-SIT099F-HNI")
    phan_loai = _phan_loai([x], [ibs_gan])
    ket_qua = phan_lop_delaunay(x, [ibs_gan], phan_loai)
    assert ket_qua == []


def test_tram_small_cell_bi_loai_khoi_tap_diem():
    x = _x()
    small_gan = _diem_cach_x_km("SC1", 0.01, 0, tram_name="4G-SIT099S-HNI")
    phan_loai = _phan_loai([x], [small_gan])
    ket_qua = phan_lop_delaunay(x, [small_gan], phan_loai)
    assert ket_qua == []


def test_tram_khac_chu_cai_la_van_duoc_giu_lam_diem():
    # "KHAC" (vd chu cai "A", _site_rieng() mac dinh) VAN duoc giu - da xac
    # nhan qua khao sat la DA SO macro ten khong chuan, loai se mat qua nhieu
    # diem that su la macro (xem dac ta o dau ho_delaunay.py).
    x = _x()
    khac = _diem_cach_x_km("KHAC1", 0.01, 0)  # mac dinh "4G-SITxxxA-HNI" -> KHAC
    phan_loai = _phan_loai([x], [khac])
    ket_qua = phan_lop_delaunay(x, [khac], phan_loai)
    assert len(ket_qua) == 1


def test_x_la_ibs_tra_rong_giong_x_toa_do_dung_chung():
    x = _x(tram_name="4G-SIT001F-HNI")
    macro_gan = _diem_cach_x_km("M1", 0.01, 0, tram_name="4G-SIT002M-HNI")
    phan_loai = _phan_loai([x], [macro_gan])
    ket_qua = phan_lop_delaunay(x, [macro_gan], phan_loai)
    assert ket_qua == []


def test_ngoai_ban_kinh_15km_khong_bao_gio_xuat_hien():
    xa = _diem_cach_x_km("XA", 20, 0)
    phan_loai = _phan_loai([_x()], [xa])
    ket_qua = phan_lop_delaunay(_x(), [xa], phan_loai)
    assert ket_qua == []


def test_qua_it_cum_dung_fallback_6_l1_12_l2():
    # 20 diem PHAN BIET (moi site rieng, mac dinh qua _site_rieng()) cach deu
    # nhau tang dan 0.1km, 0.2km... - vi chi co 1 huong (bac) nen Delaunay/
    # qhull se bao loi diem THANG HANG (suy bien), kich hoat nhanh fallback.
    # 6 cum GAN NHAT -> L1, 12 cum tiep theo -> L2, con lai (2 cum xa nhat
    # trong 20) khong xuat hien (ngoai 6+12=18).
    x = _x()
    cac_diem = [_diem_cach_x_km(f"T{i}", 0.1 * (i + 1), 0) for i in range(20)]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai)
    l1 = sorted([t for t in ket_qua if t.layer == "L1"], key=lambda t: t.km)
    l2 = sorted([t for t in ket_qua if t.layer == "L2"], key=lambda t: t.km)
    assert len(l1) == 6
    assert len(l2) == 12
    assert [t.tram_id for t in l1] == [f"T{i}" for i in range(6)]
    assert [t.tram_id for t in l2] == [f"T{i}" for i in range(6, 18)]
    # 2 cum xa nhat (T18, T19) KHONG xuat hien trong ket qua.
    assert "T18" not in {t.tram_id for t in ket_qua}
    assert "T19" not in {t.tram_id for t in ket_qua}


def test_lang_gieng_gan_nhat_trong_cum_dong_luon_la_l1():
    x = _x()
    cac_diem = [
        _diem_cach_x_km("N", 1.0, 0.3),
        _diem_cach_x_km("E", 0.3, 1.5),
        _diem_cach_x_km("S", -1.8, -0.2),
        _diem_cach_x_km("W", -0.4, -2.0),
        _diem_cach_x_km("NE", 2.2, 2.3),
        _diem_cach_x_km("SW", -2.5, -2.4),
    ]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai)
    theo_id = {t.tram_id: t for t in ket_qua}
    gan_nhat = min(cac_diem, key=lambda d: abs(d.lat - LAT0) + abs(d.lon - LON0))
    assert gan_nhat.tram_id in theo_id
    assert theo_id[gan_nhat.tram_id].layer == "L1"


def test_cum_30m_va_hang_xom_500m_hang_xom_thanh_l1():
    # Dac ta 08/10/2026: moc loc canh = ALPHA x TRUNG VI do dai CAC CANH NOI
    # VOI X (khong phai trung vi toan bubble). Mo phong: X co 1 cum RAT GAN
    # (30m, CUNG so site -> gop 1 dinh DAI DIEN cach X ~30m) VA 1 "hang xom"
    # cach 500m (site khac) - neu trung vi CHI tinh tren 1 canh gan (30m) thi
    # nguong se qua hep va loai oan hang xom 500m; neu trung vi tinh dung
    # tren CA cac canh cua X (gom ca canh toi hang xom) thi hang xom van song
    # sot. Them vai diem khac de du >=4 cum (tranh fallback) VA tranh suy
    # bien thang hang.
    x = _x()
    cum_gan = [
        _diem_cach_x_km("GAN1", 0.015, 0.01, tram_name="4G-GAN001A-HNI"),
        _diem_cach_x_km("GAN2", 0.02, 0.015, tram_name="4G-GAN001B-HNI"),  # CUNG site voi GAN1 -> gop 1 cum
    ]
    hang_xom = _diem_cach_x_km("HANGXOM", 0.5, 0)
    filler = [
        _diem_cach_x_km("F1", -0.3, 0.6),
        _diem_cach_x_km("F2", 0.6, -0.4),
        _diem_cach_x_km("F3", -0.5, -0.5),
    ]
    tat_ca_ung_vien = [*cum_gan, hang_xom, *filler]
    phan_loai = _phan_loai([x], tat_ca_ung_vien)
    ket_qua = phan_lop_delaunay(x, tat_ca_ung_vien, phan_loai)
    theo_id = {t.tram_id: t for t in ket_qua}
    assert "HANGXOM" in theo_id
    assert theo_id["HANGXOM"].layer in ("L1", "L2")  # song sot (khong bi loai het khoi ket qua)


def test_alpha_rat_nho_xoa_het_canh_SAU_khi_tam_giac_hoa_thanh_cong_tra_rong():
    # PHAN BIET 2 tinh huong (quan trong, de code KHONG nham lan):
    #   - "X khong co canh" (dac ta fallback) nghia la X CO LAP VE MAT HINH
    #     HOC TRUOC khi loc (vd qua it diem/tam giac hoa that bai) - da test
    #     rieng o test_qua_it_cum_dung_fallback_6_l1_12_l2 (qhull that bai vi
    #     diem thang hang).
    #   - ALPHA cuc nho chi xoa canh SAU KHI da tam giac hoa THANH CONG (X CO
    #     canh that trong do thi goc) - day la NGUOI DUNG CHU DONG chon
    #     nguong qua chat, KHONG PHAI loi hinh hoc -> KHONG duoc fallback,
    #     phai tra rong dung nhu nguoi dung yeu cau (alpha qua nho = "khong
    #     tin tram nao ca").
    x = _x()
    cac_diem = [
        _diem_cach_x_km("N", 1.0, 0.3),
        _diem_cach_x_km("E", 0.3, 1.5),
        _diem_cach_x_km("S", -1.8, -0.2),
        _diem_cach_x_km("W", -0.4, -2.0),
    ]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai, alpha=0.001)
    assert ket_qua == []


def test_khoang_cach_km_tra_ve_dung_haversine():
    x = _x()
    diem = _diem_cach_x_km("A", 5.0, 0)
    cac_diem = [diem, _diem_cach_x_km("B", 1, 1), _diem_cach_x_km("C", -1, 1), _diem_cach_x_km("D", 1, -1)]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai)
    theo_id = {t.tram_id: t for t in ket_qua}
    if "A" in theo_id:
        assert 4.8 < theo_id["A"].km < 5.2


def test_x_khong_co_toa_do_tra_rong():
    x_khong_toa_do = TramDiem(tram_id="X", tram_name="X", lat=0.0, lon=0.0)
    diem = _diem_cach_x_km("A", 1, 1)
    assert phan_lop_delaunay(x_khong_toa_do, [diem], {}) == []


def test_ung_vien_toa_do_0_0_bi_loai():
    x = _x()
    null_island = TramDiem(tram_id="NULL", tram_name="NULL", lat=0.0, lon=0.0)
    diem_hop_le = [
        _diem_cach_x_km("N", 1, 0), _diem_cach_x_km("E", 0, 1),
        _diem_cach_x_km("S", -1, 0), _diem_cach_x_km("W", 0, -1),
    ]
    phan_loai = _phan_loai([x], [null_island], diem_hop_le)
    ket_qua = phan_lop_delaunay(x, [null_island, *diem_hop_le], phan_loai)
    assert "NULL" not in {t.tram_id for t in ket_qua}


def test_tu_trung_tram_id_voi_x_bi_loai():
    x = _x()
    trung_id = TramDiem(tram_id="X", tram_name="Khac ten nhung trung id", lat=LAT0 + 0.01, lon=LON0)
    diem_hop_le = [
        _diem_cach_x_km("N", 1, 0), _diem_cach_x_km("E", 0, 1),
        _diem_cach_x_km("S", -1, 0), _diem_cach_x_km("W", 0, -1),
    ]
    phan_loai = _phan_loai([x], [trung_id], diem_hop_le)
    ket_qua = phan_lop_delaunay(x, [trung_id, *diem_hop_le], phan_loai)
    assert all(t.tram_id != "X" for t in ket_qua)


def test_vung_thua_x_co_hang_xom_sieu_gan_khong_cat_oan_hang_xom_that_o_xa_hon():
    # SUA 14/10/2026 (yeu cau truc tiep user, bug that tram 240091/4G-TUN009M-
    # LCU, NA14, vung nui doc QL12) - X co 4 "hang xom" SIEU GAN (0,55-1,78km,
    # mo phong tram xep day dac doc thung lung/QL) khien TRUNG VI CANH RIENG
    # CUA X (luat CU) rat nho -> moc cu = 3 x trung_vi_x se CAT OAN 1 hang xom
    # THAT o xa hon (D, 3,18km, huong RIENG - mo phong huong "thua tram" cua
    # vung) dù van nam trong mat do BINH THUONG cua CA KHU VUC. Luat MOI (trung
    # vi tren TOAN BO canh trong vung, KHONG rieng X) + loc theo tam giac
    # (alpha shape) PHAI giu duoc D la L1 (khong bi day ra L2/Z).
    x = _x("4G-SIT000A-HNI")
    a = _diem_huong_km("A", 15.7, 0.55, "4G-SIT001A-HNI")
    b = _diem_huong_km("B", 105.8, 0.74, "4G-SIT002A-HNI")
    c = _diem_huong_km("C", 119.8, 0.79, "4G-SIT003A-HNI")
    e = _diem_huong_km("E", 136.2, 1.78, "4G-SIT004A-HNI")
    d = _diem_huong_km("D", 250.7, 3.18, "4G-SIT005A-HNI")  # "hang xom that" o huong thua

    cac_diem = [a, b, c, e, d]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai)

    theo_id = {t.tram_id: t.layer for t in ket_qua}
    assert theo_id.get("D") == "L1"


def test_canh_noi_qua_vung_trong_rat_lon_van_bi_cat_du_co_diem_dem_o_giua():
    # SUA 14/10/2026 (yeu cau truc tiep user) - alpha shape THEO TAM GIAC
    # (khong theo tung canh rieng le): P1/P2/P3 la mat do BINH THUONG quanh X
    # (~2km). Y (7km) la 1 diem "dem" GAN NHU CUNG HUONG voi F (14km, sat ria
    # bubble 15km, mo phong vi tri "qua bien/qua vung trong lon") - tam giac
    # (X,Y,F) GAN NHU THANG HANG (huong Y=90.00do, F=90.01do) nen RAT "MANH"
    # (ban kinh ngoai tiep RAT LON) DU 2 canh X-Y/Y-F CO THE tung canh rieng
    # deu ngan hon nguong - PHAI bi loai CA tam giac, F khong duoc xuat hien
    # trong ket qua (khong duoc "bac cau" qua Y de vao L2).
    x = _x("4G-SIT000A-HNI")
    p1 = _diem_huong_km("P1", 0, 2.0, "4G-SIT001A-HNI")
    p2 = _diem_huong_km("P2", 120, 2.2, "4G-SIT002A-HNI")
    p3 = _diem_huong_km("P3", 240, 1.8, "4G-SIT003A-HNI")
    y = _diem_huong_km("Y", 90, 7.0, "4G-SIT004A-HNI")
    f = _diem_huong_km("F", 90.01, 14.0, "4G-SIT005A-HNI")

    cac_diem = [p1, p2, p3, y, f]
    phan_loai = _phan_loai([x], cac_diem)
    ket_qua = phan_lop_delaunay(x, cac_diem, phan_loai)

    assert "F" not in {t.tram_id for t in ket_qua}
