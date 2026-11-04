"""bo_dau() - chuan hoa chuoi tim kiem, PHAI cung ket qua translate() o SQL."""

from domain.services.bo_dau import CO_DAU, KHONG_DAU, bo_dau


def test_bo_dau_chu_thuong_va_d_gach():
    assert bo_dau("Hà Nội") == "ha noi"
    assert bo_dau("ĐÀ NẴNG") == "da nang"
    assert bo_dau("4G-TXN250M-HNI") == "4g-txn250m-hni"
    assert bo_dau(None) == ""


def test_bang_ky_tu_1_1():
    assert len(CO_DAU) == len(KHONG_DAU) == 67
    assert set(KHONG_DAU) <= set("aeiouyd")
