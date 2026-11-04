"""
Unit test cho domain/services/ho_cell_selector.py::chon_cell_cr() - ham THUAN
(khong I/O, du lieu gia lap). Tu: quyet dinh 06-08/10/2026 (BO CDS, thay bang
HO + Delaunay) - xem docs/BUSINESS_RULES.md.
"""

from math import cos, radians

import pytest

from domain.services.ho_cell_selector import (
    KhongCoDuLieuHoError,
    ThongTinTramDich,
    chon_cell_cr,
)
from domain.services.ho_delaunay import L1_CUNG_SITE, TramPhanLop

X_ID = "117903"
LAT0, LON0 = 21.000, 105.800
KM_PER_DEG_LAT = 111.32

# Nhan voi MOI attempt trong test (qua _row()) - dam bao tong HO/sector VUOT
# N_MIN_HO_SECTOR (3156, xem ho_cell_selector.py) cho du cac test viet voi
# con so nho/de doc (vd tong 100) - KHONG doi % tuong doi giua cac cell (chia
# ca tu so lan mau so cho cung 1 hang so), nen cac assert ve pct_trong_sector/
# thu tu xep hang KHONG bi anh huong, CHI tong tuyet doi tang len.
_SCALE = 50


def _toa_do_cach_km(bac_km: float, dong_km: float) -> tuple[float, float]:
    lat = LAT0 + bac_km / KM_PER_DEG_LAT
    lon = LON0 + dong_km / (KM_PER_DEG_LAT * cos(radians(LAT0)))
    return lat, lon


def _row(sector, enb, lcr, attempt, sr=None, source_lncel_name="4G-SRC11-HNI"):
    return {
        "source_sector": sector, "target_enb": enb, "target_lcr": lcr,
        "ho_attempt": attempt * _SCALE, "ho_sr": sr,
        "source_lncel_name": source_lncel_name,
    }


def _tram(enb, vendor="NOKIA", tram_id=None):
    return ThongTinTramDich(
        tram_id=tram_id or str(enb), tram_name=f"4G-T{enb}M-HNI",
        ten_thiet_bi=vendor, lat=None, lon=None,
    )


def _tram_dung_chung(enb, vendor="NOKIA"):
    # Tram dich TOA_DO_DUNG_CHUNG (CRAN) - xem dac ta TRAM TOA_DO_DUNG_CHUNG/
    # CRAN dau module. CALLER (script/adapter) tu gan co nay qua
    # ho_delaunay.phan_loai_toa_do(), ham chon_cell_cr() CHI doc lai.
    return ThongTinTramDich(
        tram_id=str(enb), tram_name=f"4G-T{enb}M-HNI",
        ten_thiet_bi=vendor, lat=None, lon=None, toa_do_dung_chung=True,
    )


def _tram_ibs(enb, vendor="NOKIA"):
    # Tram dich IBS (chu cai loai "F") - THEM 12/10/2026, yeu cau truc tiep
    # user, xem dac ta "IBS KHONG CHAY CR + TRAM DICH IBS/SMALL_CELL" dau
    # module. "SIT" (3 chu cai) lam ma site THAY vi "T" (1 chu cai) nhu
    # _tram() - loai_tram_tu_ten_tram() doi ma site 2-4 chu cai (_LOAI_TU_TEN_TRAM_RE,
    # xem domain/services/loai_tram.py), "T{enb}" cua _tram()/_tram_dung_chung()
    # KHONG khop mau nay (chi 1 chu cai) nen LUON ra NHOM_KHAC - KHONG anh
    # huong cac test cu (KHAC != IBS/SMALL_CELL, van roi vao "Z" nhu truoc),
    # nhung o day CAN khop dung de ra NHOM_IBS that su.
    return ThongTinTramDich(
        tram_id=str(enb), tram_name=f"4G-SIT{enb}F-HNI",
        ten_thiet_bi=vendor, lat=None, lon=None,
    )


def _ten(enb, lcr):
    return f"4G-T{enb}M{lcr:02d}-HNI"


def test_khong_co_du_lieu_ho_raise_loi():
    with pytest.raises(KhongCoDuLieuHoError):
        chon_cell_cr(X_ID, [], [], {}, {})


def test_cung_site_0km_vao_b_voi_layer_l1():
    # Tram dich enb=200 duoc Delaunay (gia lap) xep L1 voi km=0.0 (cung site).
    rows = [_row(1, 200, 12, 53), _row(1, 201, 13, 47, sr=99.0)]
    l1_l2 = [TramPhanLop("200", "4G-T200M-HNI", 21.0, 105.8, 0.0, "L1")]
    tram_dich = {200: _tram(200), 201: _tram(201)}
    cell_ten = {(200, 12): _ten(200, 12), (201, 13): _ten(201, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    cell_200 = next(c for c in kq.b if c.target_enb == 200)
    assert cell_200.layer == "L1"
    assert cell_200.km == 0.0


def test_l1_cung_site_xu_ly_giong_het_l1_vao_b_khong_bi_chan_boi_vung_z():
    # THEM 16/10/2026 (yeu cau truc tiep user, "VONG L1 KHONG LAY TRAM CUNG
    # SITE") - layer "L1_CUNG_SITE" (tram dich CUNG SITE voi X) PHAI duoc xu
    # ly GIONG HET "L1" o day (chi khac TEN HIEN THI, KHONG doi A/B/vung Z) -
    # dung lai y tuong test_cung_site_0km_vao_b_voi_layer_l1 o tren, DOI
    # layer thanh L1_CUNG_SITE de xac nhan KHONG co regression.
    rows = [_row(1, 200, 12, 53), _row(1, 201, 13, 47, sr=99.0)]
    l1_l2 = [TramPhanLop("200", "4G-T200M-HNI", 21.0, 105.8, 0.0, L1_CUNG_SITE)]
    tram_dich = {200: _tram(200), 201: _tram(201)}
    cell_ten = {(200, 12): _ten(200, 12), (201, 13): _ten(201, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    cell_200 = next(c for c in kq.a if c.target_enb == 200)
    assert cell_200.layer == L1_CUNG_SITE
    assert cell_200.km == 0.0
    # L1_CUNG_SITE phai duoc "bo qua gating vung Z" GIONG L1 that - cell nay
    # PHAI vao B (khong roi vao bat_thuong) du KHONG co sr (sr=None o day).
    assert 200 in {c.target_enb for c in kq.b}
    assert 200 not in {c.target_enb for c in kq.bat_thuong}


def test_vung_z_25pct_sr99_vao_b_25pct_sr80_bat_thuong_10pct_sr99_bat_thuong():
    # MOI truong hop nam RIENG 1 sector, dung NHIEU item GIA TRI BANG NHAU
    # (target dua VAO TRUOC trong danh sach rows) de cum-don-80% KHONG VO TINH
    # loai target truoc khi no kip vao A (thu tu loai theo attempt giam dan,
    # tie-break GIU nguyen thu tu chen vao - xem chon_cell_cr()). Muc dich:
    # cach ly nguyen nhan loai - CHI do luat vung Z (20%+SR95%), khong phai do
    # vo tinh bi cat boi nguong 80%/tran 15.
    rows = [
        # Sector 1: target 301 (25%, SR99) + 3 filler 25% - ca 4 item bang
        # nhau, target DUNG DAU danh sach -> chac chan duoc giu lai trong A.
        _row(1, 301, 11, 25, sr=99.0), _row(1, 310, 11, 25, sr=99.0),
        _row(1, 311, 11, 25, sr=99.0), _row(1, 312, 11, 25, sr=99.0),
        # Sector 2: target 302 (25%, SR80) + 3 filler 25%.
        _row(2, 302, 12, 25, sr=80.0), _row(2, 320, 12, 25, sr=99.0),
        _row(2, 321, 12, 25, sr=99.0), _row(2, 322, 12, 25, sr=99.0),
        # Sector 3: target 303 (10%, SR99) + 9 filler 10% - cum-don toi i=8
        # (80%) moi dung, target (item dau) van nam trong 8 item duoc giu.
        _row(3, 303, 13, 10, sr=99.0),
        *[_row(3, 330 + i, 13, 10, sr=99.0) for i in range(9)],
        # Sector 4: L1 rieng (300 attempt) de ty le Z/tong_HO cua X khong
        # vuot 50% - KHONG kich hoat luat TOA_DO_NGHI_SAI cho X (test rieng
        # o test_x_60pct_ho_vao_z...).
        _row(4, 400, 11, 300, sr=99.0),
    ]
    l1_l2 = [TramPhanLop("400", "T400", 21.0, 105.8, 1.0, "L1")]
    cac_khoa = (
        [(e, 11) for e in (301, 310, 311, 312)]
        + [(e, 12) for e in (302, 320, 321, 322)]
        + [(303, 13)] + [(330 + i, 13) for i in range(9)]
        + [(400, 11)]
    )
    tram_dich = {enb: _tram(enb) for enb, _lcr in cac_khoa}
    cell_ten = {(enb, lcr): _ten(enb, lcr) for enb, lcr in cac_khoa}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.ho_di_xa_x is False
    b_enbs = {c.target_enb for c in kq.b}
    bt_enbs = {c.target_enb for c in kq.bat_thuong}
    assert 301 in b_enbs
    assert 302 in bt_enbs
    assert 303 in bt_enbs


def test_x_60pct_ho_vao_z_khong_chan_b_theo_ho_co_toa_do_nghi_sai():
    # 60% HO cua X (60/100) roi vao Z, SR THAP (50, le ra se BAT_THUONG neu ap
    # luat vung Z binh thuong) - nhung vi X nghi toa do sai nen KHONG chan,
    # van vao B thuan theo HO.
    rows = [
        _row(1, 500, 11, 60, sr=50.0),  # Z, SR thap
        _row(1, 600, 12, 40, sr=99.0),  # L1
    ]
    l1_l2 = [TramPhanLop("600", "T600", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {500: _tram(500), 600: _tram(600)}
    cell_ten = {(500, 11): _ten(500, 11), (600, 12): _ten(600, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.ho_di_xa_x is True
    assert 500 in {c.target_enb for c in kq.b}
    assert kq.bat_thuong == []
    log_500 = next(l for l in kq.log_vung_z if l["target_enb"] == 500)
    assert "ho_di_xa" in log_500["quyet_dinh"].lower()


def test_tran_15_cell_moi_sector():
    # 20 cell cung attempt (5% moi cell) - cong don toi i=15 chi dat 75% (<80%)
    # nhung TRAN 15 buoc dung lai o day, KHONG di tiep den cell thu 16 (du can
    # them 1 cell nua moi dat 80%).
    rows = [_row(1, 700 + i, 11, 5, sr=99.0) for i in range(20)]
    l1_l2 = [TramPhanLop(str(700 + i), f"T{700+i}", 21.0, 105.8, 1.0, "L1") for i in range(20)]
    tram_dich = {700 + i: _tram(700 + i) for i in range(20)}
    cell_ten = {(700 + i, 11): _ten(700 + i, 11) for i in range(20)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert len(kq.a) == 15


def test_lay_them_cell_lon_11pct_sau_cong_don_80pct():
    # THEM 10/10/2026 (yeu cau truc tiep user) - 41/30/12/11 (%): cong don
    # dung o 83% (41+30+12, 3 cell), nhung cell thu 4 (11%) VAN >= NGUONG_CELL_LON
    # (10%) -> duoc LAY THEM -> 4 cell trong A (KHONG phai 3 nhu luat cu).
    rows = [
        _row(1, 1000, 11, 41, sr=99.0), _row(1, 1001, 12, 30, sr=99.0),
        _row(1, 1002, 13, 12, sr=99.0), _row(1, 1003, 51, 11, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1000, 1001, 1002, 1003)]
    tram_dich = {e: _tram(e) for e in (1000, 1001, 1002, 1003)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1000, 11), (1001, 12), (1002, 13), (1003, 51)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert {c.target_enb for c in kq.a} == {1000, 1001, 1002, 1003}


def test_khong_lay_them_cell_9pct_duoi_nguong_cell_lon():
    # 41/30/12/9 (%): cell thu 4 (9%) < NGUONG_CELL_LON (10%) -> KHONG duoc
    # lay them -> van 3 cell (giong luat cong-don-80% cu, khong doi).
    rows = [
        _row(1, 1100, 11, 41, sr=99.0), _row(1, 1101, 12, 30, sr=99.0),
        _row(1, 1102, 13, 12, sr=99.0), _row(1, 1103, 51, 9, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1100, 1101, 1102, 1103)]
    tram_dich = {e: _tram(e) for e in (1100, 1101, 1102, 1103)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1100, 11), (1101, 12), (1102, 13), (1103, 51)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert {c.target_enb for c in kq.a} == {1100, 1101, 1102}


def test_cell_duoi_1pct_bi_bo_khoi_a():
    rows = [_row(1, 800, 11, 995, sr=99.0), _row(1, 801, 12, 5, sr=99.0)]  # 801 = 0.5% < 1%
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (800, 801)]
    tram_dich = {800: _tram(800), 801: _tram(801)}
    cell_ten = {(800, 11): _ten(800, 11), (801, 12): _ten(801, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert {c.target_enb for c in kq.a} == {800}


def test_cell_o_2_sector_bang_nhau_giu_sector_nho_hon():
    # CUNG 1 cell dich (enb=900, lcr=11) xuat hien o CA sector 1 va sector 3,
    # TY TRONG % BANG NHAU het (ca 2 sector deu chi co dung 1 ung vien nay,
    # nen pct=100% o CA hai) -> hoa, giu sector NHO HON (dac ta SUA 2026-10).
    rows = [
        _row(1, 900, 11, 100, sr=99.0),
        _row(3, 900, 11, 100, sr=99.0),
    ]
    l1_l2 = [TramPhanLop("900", "T900", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {900: _tram(900)}
    cell_ten = {(900, 11): _ten(900, 11)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    trung = [c for c in kq.a if c.target_enb == 900]
    assert len(trung) == 1
    assert trung[0].sector == 1


def test_cell_o_2_sector_khac_ty_trong_giu_sector_ty_trong_cao_hon():
    # SUA 2026-10 (yeu cau truc tiep user, phat hien tren du lieu that tram
    # 117903: BDH056-13 chiem 36,9% HO cua sector 2 - CELL CHINH cua sector
    # do - nhung bi luat cu "sector nho nhat" lam mat khoi B vi cung lot vao
    # sector 1 voi ty trong nho hon truoc do). O day: cell dich (enb=901)
    # xuat hien o sector 1 (30% HO cua sector 1) VA sector 2 (37% HO cua
    # sector 2) - PHAI gan vao sector 2 (ty trong cao hon), KHONG con la
    # "sector nho nhat" (1) nhu luat cu.
    # Dung ty trong VUA PHAI (30%/70%, 37%/63%) - KHONG dung % qua nho nhu
    # vi du that (7%) de tranh cell bi loai oan boi buoc cong-don-80% RIENG
    # (hien tuong KHAC, da co test cell_duoi_1pct/tran_15 rieng) - muc dich
    # DUY NHAT cua test nay la khoa logic chon sector THEO %, khong lap lai
    # kiem tra buoc loc 80%.
    rows = [
        _row(1, 901, 11, 30, sr=99.0), _row(1, 910, 12, 70, sr=99.0),  # sector1: 901 = 30%
        _row(2, 901, 11, 37, sr=99.0), _row(2, 920, 12, 63, sr=99.0),  # sector2: 901 = 37%
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (901, 910, 920)]
    tram_dich = {e: _tram(e) for e in (901, 910, 920)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(901, 11), (910, 12), (920, 12)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    trung = [c for c in kq.a if c.target_enb == 901]
    assert len(trung) == 1
    assert trung[0].sector == 2
    assert trung[0].pct_trong_sector == pytest.approx(0.37)


def test_vendor_khac_vao_a_khong_vao_b():
    # 55/45 (KHONG phai 80/20): neu item dau da >=80% thi cum-don DUNG NGAY,
    # item thu 2 se khong bao gio vao duoc A - phai chia de CA HAI cung song
    # sot qua buoc loc 80%/tran 15 truoc khi toi duoc luat vendor dang test.
    rows = [_row(1, 1000, 11, 55, sr=99.0), _row(1, 1001, 12, 45, sr=99.0)]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1000, 1001)]
    tram_dich = {1000: _tram(1000, vendor="HUAWEI"), 1001: _tram(1001, vendor="NOKIA")}
    # KHONG dua ten cho enb=1000 (vendor khac Nokia - khong co nguon ten that,
    # xem GD3 trong module) - chi dua ten cho 1001 (Nokia).
    cell_ten = {(1001, 12): _ten(1001, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    cell_huawei = next(c for c in kq.a if c.target_enb == 1000)
    assert cell_huawei.vendor == "HUAWEI"
    assert cell_huawei.can_ghep_ten is True
    assert cell_huawei.cell_name is None
    assert 1000 not in {c.target_enb for c in kq.b}
    assert 1001 in {c.target_enb for c in kq.b}


def test_lcr_sai_band_khong_vao_b_nhung_van_o_a():
    # lcr=41 khong khop ^[13][0-9]$ (khong phai band 1800) - loai khoi B,
    # van hien trong A (A khong loc band, chi B moi loc). 55/45 (khong phai
    # 80/20) - cung ly do voi test_vendor_khac_vao_a_khong_vao_b o tren.
    rows = [_row(1, 1100, 41, 55, sr=99.0), _row(1, 1101, 11, 45, sr=99.0)]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1100, 1101)]
    tram_dich = {1100: _tram(1100), 1101: _tram(1101)}
    cell_ten = {(1100, 41): _ten(1100, 41), (1101, 11): _ten(1101, 11)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert 1100 in {c.target_enb for c in kq.a}
    assert 1100 not in {c.target_enb for c in kq.b}
    assert 1101 in {c.target_enb for c in kq.b}


def test_toi_da_2_cell_moi_sector_trong_b_rank_rsboost_qrxlevmin():
    rows = [
        _row(1, 1200, 11, 50, sr=99.0),
        _row(1, 1201, 12, 30, sr=99.0),
        _row(1, 1202, 13, 20, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1200, 1201, 1202)]
    tram_dich = {e: _tram(e) for e in (1200, 1201, 1202)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1200, 11), (1201, 12), (1202, 13)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    b_sector1 = [c for c in kq.b if c.sector == 1]
    assert len(b_sector1) == 2
    xep = sorted(b_sector1, key=lambda c: -c.ho_attempt)
    assert xep[0].rank_b == "rsboost"
    assert xep[1].rank_b == "qrxlevmin"
    assert 1202 not in {c.target_enb for c in kq.b}  # hang 3, khong duoc chon


def test_can_ghep_ten_loai_truoc_khi_chon_b_cell_ke_tiep_len_thay():
    # SUA 09/10/2026 (yeu cau truc tiep user, bug phat hien qua xem truoc
    # tram 117713 that): cell DAU sector (attempt cao nhat) la CAN_GHEP_TEN
    # (Nokia nhung KHONG resolve duoc ten qua cell_infor, vd tram chua sync) -
    # PHAI bi loai KHOI B NGAY, de cell hang 2 (3001) len thay rank rsboost
    # VA cell hang 3 (3002) len thay rank qrxlevmin - KHONG duoc de "mat suat"
    # ca sector nhu truoc sua (B tu 12 -> 10 cell cho tram 117713 that).
    rows = [
        _row(1, 3000, 11, 60, sr=99.0),  # attempt cao nhat, CAN_GHEP_TEN
        _row(1, 3001, 12, 50, sr=99.0),
        _row(1, 3002, 13, 40, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (3000, 3001, 3002)]
    tram_dich = {e: _tram(e) for e in (3000, 3001, 3002)}
    # 3000 KHONG co trong cell_ten -> can_ghep_ten=True (du van la NOKIA, vendor
    # lay tu tram_dich, doc lap voi viec ghep ten duoc hay khong - xem GD3).
    cell_ten = {(3001, 12): _ten(3001, 12), (3002, 13): _ten(3002, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    cell_3000 = next(c for c in kq.a if c.target_enb == 3000)
    assert cell_3000.can_ghep_ten is True
    assert 3000 not in {c.target_enb for c in kq.b}  # loai KHOI B, VAN con trong A

    b_sector1 = sorted((c for c in kq.b if c.sector == 1), key=lambda c: -c.ho_attempt)
    assert {c.target_enb for c in b_sector1} == {3001, 3002}
    assert b_sector1[0].target_enb == 3001 and b_sector1[0].rank_b == "rsboost"
    assert b_sector1[1].target_enb == 3002 and b_sector1[1].rank_b == "qrxlevmin"


def test_small_cell_bi_loai_khoi_a():
    # Ten cell dang "...S11-..." (S = small cell, xem domain/services/loai_tram.py).
    # attempt 1301 CAO HON 1300 (khong con 50/50) - vi SUA 08/10/2026 loai
    # small cell TRUOC khi tinh mau so %, mau so (tong_goc) chi con tinh tren
    # 1301 sau khi 1300 bi loai - can du lon de VUOT N_MIN_HO_SECTOR MOT MINH.
    rows = [_row(1, 1300, 11, 50, sr=99.0), _row(1, 1301, 12, 100, sr=99.0)]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1300, 1301)]
    tram_dich = {1300: _tram(1300), 1301: _tram(1301)}
    cell_ten = {(1300, 11): "4G-ABC123S11-HNI", (1301, 12): _ten(1301, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert 1300 not in {c.target_enb for c in kq.a}
    assert 1301 in {c.target_enb for c in kq.a}
    # % cua 1301 PHAI la 100% (mau so da LOAI attempt cua 1300 - small cell -
    # TRUOC khi tinh %, KHONG con la 100/(100+50)=66,7% nhu neu tinh tren tap
    # CHUA loai small cell).
    cell_1301 = next(c for c in kq.a if c.target_enb == 1301)
    assert cell_1301.pct_trong_sector == pytest.approx(1.0)


def test_toa_do_tram_dich_nghi_sai_khi_cach_x_qua_3_lan_trung_vi_l1():
    # BUG THAT phat hien qua scripts/kiem_tra_thuat_toan_ho.py tren du lieu
    # that (300 tram mau, 147 cell Z co %>=20% nhung 0 cell nao duoc gan co -
    # vi km cua cell Z luon None neu chi lay tu l1_l2). Test nay khoa lai hanh
    # vi DUNG: phai TU TINH km tu toa do X (x_lat/x_lon) cho CA cell Z.
    x_lat, x_lon = LAT0, LON0
    # L1 o 1km -> trung_vi_l1_km = 1.0 -> nguong 3x = 3.0km.
    lat_l1, lon_l1 = _toa_do_cach_km(1.0, 0)
    # Cell Z "qua xa": 10% lon hon nguong (3.3km) - pct 25% (>=20%).
    lat_xa, lon_xa = _toa_do_cach_km(3.3, 0)
    # Cell Z "chap nhan duoc": trong nguong (2km) - pct 25% (>=20%) nhung
    # KHONG duoc gan co vi chua vuot 3x trung vi L1.
    lat_gan, lon_gan = _toa_do_cach_km(2.0, 0)

    rows = [
        _row(1, 2000, 11, 25, sr=50.0),  # Z, qua xa -> nghi toa do dich
        _row(1, 2001, 12, 25, sr=50.0),  # Z, chap nhan duoc -> KHONG nghi
        _row(1, 2002, 13, 50, sr=99.0),  # filler lam tong = 100
    ]
    l1_l2 = [TramPhanLop("3000", "T3000", lat_l1, lon_l1, 1.0, "L1")]
    tram_dich = {
        2000: ThongTinTramDich("2000", "T2000", "NOKIA", lat_xa, lon_xa),
        2001: ThongTinTramDich("2001", "T2001", "NOKIA", lat_gan, lon_gan),
        2002: _tram(2002),
    }
    cell_ten = {(2000, 11): _ten(2000, 11), (2001, 12): _ten(2001, 12), (2002, 13): _ten(2002, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten, x_lat=x_lat, x_lon=x_lon)

    theo_enb = {c.target_enb: c for c in kq.a}
    assert theo_enb[2000].ho_di_xa_dich is True
    assert theo_enb[2001].ho_di_xa_dich is False


def test_l1_cung_site_van_duoc_tinh_vao_trung_vi_l1_km():
    # THEM 16/10/2026 - neu L1_CUNG_SITE KHONG duoc gom vao trung_vi_l1_km
    # (xem khoang_cach_l1 o chon_cell_cr()), L1 CHI gom tram cung site (km=0.0
    # het) se lam trung_vi_l1_km = None (danh sach rong) -> luat
    # TOA_DO_TRAM_DICH_NGHI_SAI KHONG BAO GIO ap dung duoc. Test nay khoa lai:
    # L1 TOAN BO la L1_CUNG_SITE (km=0.0) -> trung_vi_l1_km = 0.0 -> MOI cell
    # Z co km > 0 va pct>=20% PHAI bi gan co ho_di_xa_dich=True.
    x_lat, x_lon = LAT0, LON0
    lat_xa, lon_xa = _toa_do_cach_km(1.0, 0)  # bat ky km > 0 = qua 3*0

    rows = [
        _row(1, 2000, 11, 25, sr=50.0),  # Z, pct=25% (>=20%)
        _row(1, 2002, 13, 75, sr=99.0),  # filler lam tong = 100
    ]
    l1_l2 = [TramPhanLop("3000", "T3000", x_lat, x_lon, 0.0, L1_CUNG_SITE)]
    tram_dich = {
        2000: ThongTinTramDich("2000", "T2000", "NOKIA", lat_xa, lon_xa),
        2002: _tram(2002),
    }
    cell_ten = {(2000, 11): _ten(2000, 11), (2002, 13): _ten(2002, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten, x_lat=x_lat, x_lon=x_lon)

    theo_enb = {c.target_enb: c for c in kq.a}
    assert theo_enb[2000].ho_di_xa_dich is True


def test_khong_truyen_toa_do_x_thi_km_cell_z_la_none_khong_crash():
    # Tuong thich nguoc: KHONG truyen x_lat/x_lon (mac dinh None) - km cua
    # cell Z la None, luat TOA_DO_TRAM_DICH_NGHI_SAI khong ap dung duoc
    # (KHONG crash, chi khong gan co duoc - giu hanh vi an toan).
    rows = [_row(1, 2100, 11, 25, sr=50.0), _row(1, 2101, 12, 75, sr=99.0)]
    l1_l2 = [TramPhanLop("2101", "T2101", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {2100: _tram(2100), 2101: _tram(2101)}
    cell_ten = {(2100, 11): _ten(2100, 11), (2101, 12): _ten(2101, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)  # KHONG truyen x_lat/x_lon

    cell_z = next(c for c in kq.a if c.target_enb == 2100)
    assert cell_z.km is None
    assert cell_z.ho_di_xa_dich is False


def test_khong_ghep_duoc_tram_dich_van_vao_a_voi_vendor_khong_ro():
    rows = [_row(1, 1400, 11, 80, sr=99.0), _row(1, 1401, 12, 20, sr=99.0)]
    l1_l2 = [TramPhanLop("1401", "T1401", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {1401: _tram(1401)}  # KHONG co 1400 trong bang tram
    cell_ten = {(1401, 12): _ten(1401, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    cell_1400 = next(c for c in kq.a if c.target_enb == 1400)
    assert cell_1400.vendor == "KHONG_RO_TRAM"
    assert cell_1400.can_ghep_ten is True
    assert cell_1400.layer == "Z"  # khong trong l1_l2 -> mac dinh Z


# === THEM 08/10/2026 (yeu cau truc tiep user, sua sau review thiet ke) ===


def test_nguon_mbf_bi_bo_phong_ve_2_lop():
    # Da loc o import_ho_neighbor.py, nhung chon_cell_cr() PHAI tu phong ve
    # (khong tin tuyet doi caller) - dong co source_lncel_name bat dau "MBF_"
    # bi loai, KHONG duoc tinh vao bat ky sector/cell nao.
    rows = [
        _row(1, 1500, 11, 100, sr=99.0, source_lncel_name="MBF_H2_TEST_1_M4BA"),
        _row(1, 1501, 12, 100, sr=99.0, source_lncel_name="4G-SRC11-HNI"),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1500, 1501)]
    tram_dich = {e: _tram(e) for e in (1500, 1501)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1500, 11), (1501, 12)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert 1500 not in {c.target_enb for c in kq.a}
    assert 1501 in {c.target_enb for c in kq.a}
    # Mau so % CHI tinh tren 1501 (dong MBF_ khong duoc tinh) -> 100%.
    cell_1501 = next(c for c in kq.a if c.target_enb == 1501)
    assert cell_1501.pct_trong_sector == pytest.approx(1.0)


def test_noi_tram_bi_bo_phong_ve_2_lop():
    # target_enb == CHINH tram X (noi tram/intra-eNB) - da loc o import, nhung
    # chon_cell_cr() PHAI tu phong ve. X_ID="117903".
    rows = [
        _row(1, int(X_ID), 11, 100, sr=99.0),  # noi tram - PHAI bi bo
        _row(1, 1600, 12, 100, sr=99.0),
    ]
    l1_l2 = [TramPhanLop("1600", "T1600", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {int(X_ID): _tram(int(X_ID)), 1600: _tram(1600)}
    cell_ten = {(int(X_ID), 11): _ten(int(X_ID), 11), (1600, 12): _ten(1600, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert int(X_ID) not in {c.target_enb for c in kq.a}
    assert 1600 in {c.target_enb for c in kq.a}


def test_quan_he_day_du_giu_ca_sector_phu_bi_dedup():
    # Cell dich (enb=1700) xuat hien o CA sector 1 (30%) va sector 2 (37%) -
    # kq.a (sau dedup) CHI con 1 ban ghi (sector 2, % cao hon - xem test rieng
    # cell_o_2_sector_khac_ty_trong...), nhung kq.quan_he_day_du PHAI giu CA
    # HAI ban ghi (de "xem lai, kiem toan" - dac ta 08/10/2026).
    rows = [
        _row(1, 1700, 11, 30, sr=99.0), _row(1, 1710, 12, 70, sr=99.0),
        _row(2, 1700, 11, 37, sr=99.0), _row(2, 1720, 12, 63, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1700, 1710, 1720)]
    tram_dich = {e: _tram(e) for e in (1700, 1710, 1720)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1700, 11), (1710, 12), (1720, 12)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert len([c for c in kq.a if c.target_enb == 1700]) == 1  # A da dedup
    quan_he_1700 = [q for q in kq.quan_he_day_du if q.target_enb == 1700]
    assert len(quan_he_1700) == 2  # quan_he_day_du GIU CA 2 (sector 1 VA sector 2)
    assert {q.sector for q in quan_he_1700} == {1, 2}
    pct_theo_sector = {q.sector: q.pct_trong_sector for q in quan_he_1700}
    assert pct_theo_sector[1] == pytest.approx(0.30)
    assert pct_theo_sector[2] == pytest.approx(0.37)


def test_80pct_tinh_truoc_dedup_xuyen_sector():
    # 1 cell (enb=1800) xuat hien o CA sector 1 (40%, SONG SOT qua cong don
    # 80% cua sector 1 vi la 1 trong 2 cell can de dat 80%) VA sector 2 (40%,
    # CUNG song sot vi ly do tuong tu). Moi sector tinh cong-don 80% HOAN TOAN
    # DOC LAP - dedup xuyen sector (buoc SAU) khong duoc anh huong nguoc lai
    # ket qua da chot cua tung sector. Dung 40%/60% (khong phai 90%/10%) de
    # CA HAI xuat hien cua 1800 cung song sot qua cong-don (90% mot minh da
    # du 80%, se "nuot" het suat truoc khi toi luot cell thu 2 - xem cac test
    # khac ve cong don).
    rows = [
        _row(1, 1800, 11, 40, sr=99.0), _row(1, 1801, 12, 60, sr=99.0),
        _row(2, 1800, 11, 40, sr=99.0), _row(2, 1810, 13, 60, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1800, 1801, 1810)]
    tram_dich = {e: _tram(e) for e in (1800, 1801, 1810)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1800, 11), (1801, 12), (1810, 13)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    # quan_he_day_du (TRUOC dedup) phai thay 1800 o CA 2 sector - CHUNG MINH
    # moi sector tu cong don 80% DOC LAP, khong bi "mat" boi dedup sang sector
    # khac (dedup la buoc RIENG, chay SAU khi ca 2 sector da chot xong).
    quan_he_1800 = {q.sector: q.pct_trong_sector for q in kq.quan_he_day_du if q.target_enb == 1800}
    assert quan_he_1800 == {1: pytest.approx(0.40), 2: pytest.approx(0.40)}
    # Sau dedup: ca 2 sector cung % (40% = 40%) -> giu sector NHO HON (GD4).
    cell_1800 = next(c for c in kq.a if c.target_enb == 1800)
    assert cell_1800.sector == 1
    # Sector 2 van co 1810 (60% cua rieng sector 2) - khong bi mat du 1800
    # "thuoc ve" sector 1 sau dedup.
    assert any(c.target_enb == 1810 and c.sector == 2 for c in kq.a)


def test_sector_duoi_n_min_van_xu_ly_nhung_duoc_ghi_nhan_it_du_lieu():
    # Sector 1: tong HO lon (vuot N_MIN). Sector 2: tong HO NHO (duoi N_MIN,
    # vd 10 truoc scale = 500 sau scale, < 3156) - VAN duoc xu ly binh thuong
    # (khong bi loai bo), chi duoc GHI NHAN vao sectors_it_du_lieu.
    rows = [
        _row(1, 1900, 11, 100, sr=99.0),  # sector 1: 100*50=5000 >= N_MIN
        _row(2, 1901, 12, 10, sr=99.0),  # sector 2: 10*50=500 < N_MIN (3156)
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (1900, 1901)]
    tram_dich = {e: _tram(e) for e in (1900, 1901)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(1900, 11), (1901, 12)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.sectors_it_du_lieu == {2}
    # Sector 2 VAN duoc xu ly - 1901 van co mat trong A (khong bi loai bo chi
    # vi it du lieu, dung dac ta "van xu ly, chi canh bao").
    assert 1901 in {c.target_enb for c in kq.a}


def _rows_10_cell_10pct_sr_cho_dich_dau(sr_dich_dau: float):
    # 10 cell CUNG 1 sector (sector 1), moi cell 10% - cong don 80% dung o
    # item thu 8 (bao gom item dau, "dich dau") - DAM BAO item dau (dang
    # test) SONG SOT qua buoc loc 80%/tran 15 MA pct van < 20%
    # (NGUONG_VUNG_Z_PCT) - de cach ly dung luat dang test (KHONG_XAC_DINH
    # chi can SR, khong can %). THEM sector 2 voi 1 cell L1 attempt RAT LON -
    # giu ty trong Z/tong_HO cua X duoi 50%, TRANH vo tinh kich hoat
    # ho_di_xa_x (se tu bo qua MOI luat cong, lam test mat y nghia).
    rows = [_row(1, 2200, 11, 10, sr=sr_dich_dau)]
    rows += [_row(1, 2200 + i, 11, 10, sr=99.0) for i in range(1, 10)]
    rows.append(_row(2, 9999, 13, 3000, sr=99.0))
    return rows


def test_tram_dich_toa_do_dung_chung_sr99_vao_b_du_pct_thap():
    # Cell dich 2200 la TOA_DO_DUNG_CHUNG, pct=10% (< 20%, KHONG du luat vung
    # Z binh thuong) nhung SR=99% (>=95%) - luat KHONG_XAC_DINH LONG HON Z,
    # CHI can SR, khong doi hoi %>=20% - PHAI vao B.
    rows = _rows_10_cell_10pct_sr_cho_dich_dau(99.0)
    cac_enb = [2200 + i for i in range(10)]
    l1_l2 = [TramPhanLop("9999", "T9999", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {2200: _tram_dung_chung(2200), 9999: _tram(9999)}
    tram_dich.update({enb: _tram(enb) for enb in cac_enb[1:]})
    cell_ten = {(enb, 11): _ten(enb, 11) for enb in cac_enb}
    cell_ten[(9999, 13)] = _ten(9999, 13)

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.ho_di_xa_x is False  # xem comment _rows_10_cell_10pct_sr_cho_dich_dau
    cell_2200 = next(c for c in kq.a if c.target_enb == 2200)
    assert cell_2200.layer == "KHONG_XAC_DINH"
    assert cell_2200.pct_trong_sector == pytest.approx(0.10)
    assert 2200 in {c.target_enb for c in kq.b}
    # Cac filler (layer "Z" THAT, pct=10% < 20%) VAN bi BAT_THUONG binh thuong
    # - chi RIENG 2200 (KHONG_XAC_DINH) duoc luat long hon (SR-only) cuu.
    assert 2200 not in {c.target_enb for c in kq.bat_thuong}


def test_tram_dich_toa_do_dung_chung_sr80_bat_thuong():
    # CUNG cau hinh nhung SR=80% (< 95%) - PHAI BAT_THUONG (luat KHONG_XAC_DINH
    # van doi hoi SR>=95%, chi BO di doi hoi %>=20% so voi luat vung Z).
    rows = _rows_10_cell_10pct_sr_cho_dich_dau(80.0)
    cac_enb = [2200 + i for i in range(10)]
    l1_l2 = [TramPhanLop("9999", "T9999", 21.0, 105.8, 1.0, "L1")]
    tram_dich = {2200: _tram_dung_chung(2200), 9999: _tram(9999)}
    tram_dich.update({enb: _tram(enb) for enb in cac_enb[1:]})
    cell_ten = {(enb, 11): _ten(enb, 11) for enb in cac_enb}
    cell_ten[(9999, 13)] = _ten(9999, 13)

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.ho_di_xa_x is False
    assert 2200 in {c.target_enb for c in kq.bat_thuong}
    assert 2200 not in {c.target_enb for c in kq.b}


def test_x_la_toa_do_dung_chung_bo_qua_gating_b_thuan_theo_ho():
    # X la TOA_DO_DUNG_CHUNG (CALLER tu xac dinh qua phan_loai_toa_do(), TRUYEN
    # vao qua x_la_toa_do_dung_chung=True) - khong tinh duoc L1/L2 (l1_l2=[]),
    # KHONG chan vung Z: 2 cell sector 1 (layer "Z", SR THAP) deu vao B DU SR
    # THAP, thuan theo HO. Them 1 cell sector 2 (RIENG, attempt lon, dich la
    # TOA_DO_DUNG_CHUNG -> layer KHONG_XAC_DINH) CHI de giu ty trong Z/tong_HO
    # duoi 50% - TRANH ho_di_xa_x (luat RIENG cua X) VO TINH cung kich hoat,
    # dam bao PHEP THU nay CO LAP DUNG nguyen nhan bo qua la x_la_toa_do_dung_chung.
    rows = [
        _row(1, 500, 11, 60, sr=50.0),  # SR thap - le ra BAT_THUONG neu ap luat vung Z binh thuong
        _row(1, 600, 12, 40, sr=99.0),
        _row(2, 700, 13, 3000, sr=99.0),
    ]
    l1_l2 = []  # BAT BUOC rong - X TOA_DO_DUNG_CHUNG khong tinh L1/L2
    tram_dich = {500: _tram(500), 600: _tram(600), 700: _tram_dung_chung(700)}
    cell_ten = {(500, 11): _ten(500, 11), (600, 12): _ten(600, 12), (700, 13): _ten(700, 13)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten, x_la_toa_do_dung_chung=True)

    assert kq.ho_di_xa_x is False  # xem comment tren - co lap dung nguyen nhan
    assert kq.x_la_toa_do_dung_chung is True
    assert kq.bat_thuong == []
    assert {500, 600, 700} == {c.target_enb for c in kq.b}
    log_500 = next(l for l in kq.log_vung_z if l["target_enb"] == 500)
    assert "toa_do_dung_chung" in log_500["quyet_dinh"].lower()


def test_x_la_toa_do_dung_chung_100pct_ho_ra_ngoai_khong_gan_ho_di_xa():
    # SUA 08/10/2026 lan 3 (yeu cau truc tiep user): X la TOA_DO_DUNG_CHUNG
    # thi KHONG duoc tinh/gan co HO_DI_XA - X khong co VI TRI dang tin nen
    # khong the noi HO dang "di xa VE DAU" (so voi cai gi?). O day CA 2 cell
    # (100% tong HO cua X) deu la layer "Z" - neu tinh theo cong thuc thuong
    # (>50% HO vao Z) se RA ho_di_xa_x=True, nhung PHAI bi chan boi dieu kien
    # x_la_toa_do_dung_chung - CHI co TOA_DO_DUNG_CHUNG, KHONG co them HO_DI_XA.
    rows = [
        _row(1, 500, 11, 60, sr=50.0),
        _row(1, 600, 12, 40, sr=99.0),
    ]
    l1_l2 = []  # X TOA_DO_DUNG_CHUNG khong tinh L1/L2
    tram_dich = {500: _tram(500), 600: _tram(600)}
    cell_ten = {(500, 11): _ten(500, 11), (600, 12): _ten(600, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten, x_la_toa_do_dung_chung=True)

    assert kq.x_la_toa_do_dung_chung is True
    assert kq.ho_di_xa_x is False  # KHONG con tu dong True du 100% HO vao Z
    # Van giu hanh vi bo qua chan vung Z - B chon thuan theo HO (SR thap van vao B).
    assert {500, 600} == {c.target_enb for c in kq.b}
    assert kq.bat_thuong == []


def test_moi_sector_deu_duoi_n_min_xu_ly_nhu_khong_co_du_lieu_ho():
    # CA 2 sector deu duoi N_MIN (10 va 20 truoc scale, <=1000 sau scale,
    # < 3156) -> toan bo X bi xu ly NHU khong co du lieu HO (raise loi),
    # KHONG chi la "it du lieu" don le.
    rows = [
        _row(1, 2000, 11, 10, sr=99.0),
        _row(2, 2001, 12, 20, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (2000, 2001)]
    tram_dich = {e: _tram(e) for e in (2000, 2001)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(2000, 11), (2001, 12)]}

    with pytest.raises(KhongCoDuLieuHoError):
        chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)


def test_cell_dau_sector_la_ibs_bi_loai_khoi_b_cell_ke_tiep_len_thay():
    # THEM 12/10/2026 (yeu cau truc tiep user, "IBS KHONG CHAY CR") - cell dau
    # sector (attempt lon nhat, le ra rank "rsboost") dich la tram IBS -> PHAI
    # bi loai khoi B, cell thu 2 len thay "rsboost", cell thu 3 len thay
    # "qrxlevmin". Tram 900 (IBS) KHONG dua vao l1_l2 (giong PIPELINE THAT -
    # phan_lop_delaunay() da loai IBS khoi tap diem TU TRUOC, xem ho_delaunay.py)
    # de dung nhanh "elif loai_tram_dich == NHOM_IBS" (KHONG bi layer_theo_enb
    # "de" mat vi uu tien L1/L2 neu lo dua vao).
    rows = [
        _row(1, 900, 11, 50, sr=99.0),  # IBS - loai khoi B
        _row(1, 901, 12, 30, sr=99.0),
        _row(1, 902, 13, 20, sr=99.0),
    ]
    l1_l2 = [TramPhanLop(str(e), f"T{e}", 21.0, 105.8, 1.0, "L1") for e in (901, 902)]
    tram_dich = {900: _tram_ibs(900), 901: _tram(901), 902: _tram(902)}
    cell_ten = {(e, l): _ten(e, l) for e, l in [(900, 11), (901, 12), (902, 13)]}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert 900 in {c.target_enb for c in kq.a}  # IBS VAN trong A
    assert 900 not in {c.target_enb for c in kq.b}  # nhung KHONG trong B
    b_theo_enb = {c.target_enb: c.rank_b for c in kq.b}
    assert b_theo_enb == {901: "rsboost", 902: "qrxlevmin"}
    cell_900 = next(c for c in kq.a if c.target_enb == 900)
    assert cell_900.layer == "IBS"


def test_tram_dich_ibs_layer_ibs_khong_bi_chan_boi_luat_vung_z_nhung_van_loai_khoi_b():
    # Tram dich IBS, SR THAP (50, le ra BAT_THUONG neu ap luat vung Z/
    # KHONG_XAC_DINH binh thuong) - PHAI KHONG bi BAT_THUONG (layer "IBS"
    # KHONG ap gating vung Z, xem dac ta VIEC 3) - nghia la VAN o lai trong A
    # (danh gia/phieu). Nhung VAN bi loai khoi B (VIEC 2 - "IBS khong chay
    # CR") - 2 luat nay DOC LAP, khong mau thuan: "khong bi chan vung Z" chi
    # noi ve tu cach vao A, khong noi ve B. X KHONG phai IBS/CRAN o day - cach
    # ly dung nguyen nhan la layer cua TRAM DICH, khong phai co bo_qua_gating cua X.
    rows = [_row(1, 900, 11, 100, sr=50.0)]
    l1_l2 = []  # 900 (IBS) khong trong l1_l2 - giong pipeline that
    tram_dich = {900: _tram_ibs(900)}
    cell_ten = {(900, 11): _ten(900, 11)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten)

    assert kq.bat_thuong == []
    assert 900 in {c.target_enb for c in kq.a}
    assert 900 not in {c.target_enb for c in kq.b}


def test_x_la_ibs_bo_qua_gating_b_thuan_theo_ho_khong_gan_ho_di_xa():
    # X la IBS (truyen x_la_ibs=True, CALLER tu xac dinh qua
    # loai_tram_tu_ten_tram() - GIONG het mau hinh x_la_toa_do_dung_chung) -
    # khong tinh duoc L1/L2 (l1_l2=[] BAT BUOC), KHONG chan vung Z: cell SR
    # THAP van vao B. ho_di_xa_x PHAI la False (EP, giong X CRAN) DU 100% HO
    # roi vao "Z" (gia tao vi l1_l2 rong) - tranh bao HO_DI_XA sai nguyen nhan,
    # da co co TRAM_IBS rieng (them o tang application, khong phai o day).
    rows = [
        _row(1, 500, 11, 60, sr=50.0),
        _row(1, 600, 12, 40, sr=99.0),
    ]
    l1_l2 = []  # X la IBS - BAT BUOC rong, giong X TOA_DO_DUNG_CHUNG
    tram_dich = {500: _tram(500), 600: _tram(600)}
    cell_ten = {(500, 11): _ten(500, 11), (600, 12): _ten(600, 12)}

    kq = chon_cell_cr(X_ID, rows, l1_l2, tram_dich, cell_ten, x_la_ibs=True)

    assert kq.ho_di_xa_x is False  # EP False, khong tu dong True du 100% vao Z
    assert kq.bat_thuong == []
    assert {500, 600} == {c.target_enb for c in kq.b}
