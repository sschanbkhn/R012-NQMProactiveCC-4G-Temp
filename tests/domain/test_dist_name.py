"""
Unit test cho extract_lnbts() — helper dung chung RsboostCalculator/
QrxlevminCalculator, doi tu MRBTS sang LNBTS lam nguon tram_id (21072026, xac
nhan voi user sau khi verify DB that: bang tram khoa theo LNBTS, MRBTS co the
khac LNBTS gay FK violation neu dung nham).
Tu: docs/DEV_LOG.md muc "sua gom/join tram MRBTS -> LNBTS".
"""

import pytest

from domain.services.dist_name import extract_lnbts


def test_mrbts_bang_lnbts_ra_dung_gia_tri():
    dn = "PLMN-PLMN/MRBTS-111139/LNBTS-111139/LNCEL-41"
    assert extract_lnbts(dn) == "111139"


def test_mrbts_khac_lnbts_lay_dung_lnbts_khong_phai_mrbts():
    # Mo phong dung 1 trong 12 nhom lech that da verify tren cell_infor (57
    # dong) - MRBTS thua 1 chu so dau so voi LNBTS. PHAI lay LNBTS, KHONG duoc
    # lay MRBTS (se ra tram_id khong ton tai trong bang tram -> FK violation
    # neu ghi that vao cell_params).
    dn = "PLMN-PLMN/MRBTS-1100105/LNBTS-110105/LNCEL-11"
    assert extract_lnbts(dn) == "110105"


def test_khong_co_lnbts_trong_dist_name_raise_value_error():
    with pytest.raises(ValueError):
        extract_lnbts("dist-name-khong-hop-le")
