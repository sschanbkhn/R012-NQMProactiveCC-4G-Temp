"""
Unit test cho domain/value_objects/ten_tinh.py. Tu: BUOC 4c (10/10/2026).
"""

from domain.value_objects.ten_tinh import TEN_TINH_THEO_MA, ten_tinh_tu_ma


def test_du_34_ma_theo_nghi_quyet_306():
    assert len(TEN_TINH_THEO_MA) == 34


def test_ten_tinh_tu_ma_dung_voi_ma_hop_le():
    assert ten_tinh_tu_ma("HNI") == "Ha Noi"
    assert ten_tinh_tu_ma("HCM") == "TP Ho Chi Minh"
    assert ten_tinh_tu_ma("CMU") == "Ca Mau"


def test_ten_tinh_tu_ma_rong_hoac_none_tra_none():
    assert ten_tinh_tu_ma(None) is None
    assert ten_tinh_tu_ma("") is None


def test_ten_tinh_tu_ma_khong_doan_ma_cu_hoac_la():
    # "HDG" la ma CU (truoc sap nhap, van con trong khu_vuc.py vi ly do khac) -
    # O DAY KHONG co ten tinh chinh thuc nao de hien, PHAI tra None.
    assert ten_tinh_tu_ma("HDG") is None
    assert ten_tinh_tu_ma("XYZ") is None
