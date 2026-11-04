"""
Unit test cho ma_tinh_cu_tu_ten_cell() - suy ma tinh CU tu 3 ky tu cuoi ten
cell. Tu: Giai doan 1 buoc 2 (27/09/2026, dinh tuyen OSS theo tung cell).
"""

from domain.services.oss_routing import ma_tinh_cu_tu_ten_cell


def test_ten_dung_mau_suy_dung_ma_tinh_cu():
    assert ma_tinh_cu_tu_ten_cell("4G-STY024M32-HNI") == "HNI"


def test_ten_dung_mau_tinh_khac():
    # Cell -HGG (Ha Giang, ma tinh CU) - dai dien cho nhom tinh Netact14
    # (KI-08), khac han ma_tinh MOI cot tram.ma_tinh sau sap nhap (vd TQG).
    assert ma_tinh_cu_tu_ten_cell("4G-STY007M32-HGG") == "HGG"


def test_ten_khong_dung_mau_tra_none():
    # Thieu hau to "-XXX" (3 chu hoa) - vd fixture cu "4G-CELL-A" trong cac
    # test khac cua module TriggerCrUseCase TRUOC 09/2026.
    assert ma_tinh_cu_tu_ten_cell("4G-CELL-A") is None


def test_hau_to_chu_thuong_tra_none():
    # Mau CHI chap nhan 3 CHU HOA - chu thuong khong khop, KHONG tu upper()
    # de doan mu: neu du lieu that co chu thuong day la tin hieu can dieu
    # tra, khong phai loi go nham 1-2 ky tu de tu sua.
    assert ma_tinh_cu_tu_ten_cell("4G-STY024M32-hni") is None


def test_hau_to_khong_du_3_ky_tu_tra_none():
    assert ma_tinh_cu_tu_ten_cell("4G-STY024M32-HN") is None


def test_hau_to_qua_3_ky_tu_tra_none():
    # "^...$" phai khop TRON VEN - "-HANOI" (5 chu) khong duoc cat con 3
    # chu cuoi ma phai loai HAN vi khong khop mau.
    assert ma_tinh_cu_tu_ten_cell("4G-STY024M32-HANOI") is None


def test_khong_bat_dau_4G_tra_none():
    assert ma_tinh_cu_tu_ten_cell("3G-STY024M32-HNI") is None


def test_chuoi_rong_tra_none():
    assert ma_tinh_cu_tu_ten_cell("") is None


def test_none_tra_none_khong_crash():
    assert ma_tinh_cu_tu_ten_cell(None) is None
