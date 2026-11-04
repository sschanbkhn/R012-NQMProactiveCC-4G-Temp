"""
Unit test cho domain/services/cran_vi_tri_estimator.py::uoc_luong_vi_tri_cran().
Tu: BUOC 4c (10/10/2026, yeu cau truc tiep user).
"""

import pytest

from domain.services.cran_vi_tri_estimator import (
    NGUONG_SO_TRAM_DICH_TOI_THIEU,
    NGUONG_TY_LE_HO_TIN_CAY,
    uoc_luong_vi_tri_cran,
)
from domain.services.ho_delaunay import TIN_CAY, TOA_DO_DUNG_CHUNG


def _row(source_enb, source_sector, target_enb, ho_attempt):
    return {"source_enb": source_enb, "source_sector": source_sector, "target_enb": target_enb, "ho_attempt": ho_attempt}


def test_du_dieu_kien_tinh_trung_tam_co_trong_so():
    # enb=100 (CRAN) sector=1, HO toi 3 tram dich TIN_CAY (du NGUONG_SO_TRAM_
    # DICH_TOI_THIEU=3), 100% HO vao tram TIN_CAY (du 50%).
    rows = [
        _row(100, 1, 200, 60),
        _row(100, 1, 201, 30),
        _row(100, 1, 202, 10),
    ]
    phan_loai = {"100": TOA_DO_DUNG_CHUNG, "200": TIN_CAY, "201": TIN_CAY, "202": TIN_CAY}
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1), 202: (21.2, 105.2)}

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert len(ket_qua) == 1
    kq = ket_qua[0]
    assert kq["enb"] == 100
    assert kq["lcr"] == 1
    assert kq["ty_le_ho_tin_cay"] == pytest.approx(1.0)
    assert kq["so_tram_dich"] == 3
    lat_mong_doi = (21.0 * 60 + 21.1 * 30 + 21.2 * 10) / 100
    lon_mong_doi = (105.0 * 60 + 105.1 * 30 + 105.2 * 10) / 100
    assert kq["lat"] == pytest.approx(lat_mong_doi)
    assert kq["lon"] == pytest.approx(lon_mong_doi)


def test_thieu_so_tram_dich_khong_ghi():
    # Chi 2 tram dich TIN_CAY (< NGUONG_SO_TRAM_DICH_TOI_THIEU=3) - 100% HO
    # vao tram TIN_CAY (du ty le) nhung THIEU so luong -> KHONG ghi.
    rows = [_row(100, 1, 200, 60), _row(100, 1, 201, 40)]
    phan_loai = {"100": TOA_DO_DUNG_CHUNG, "200": TIN_CAY, "201": TIN_CAY}
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1)}

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert ket_qua == []


def test_thieu_ty_le_ho_tin_cay_khong_ghi():
    # Du 3 tram dich TIN_CAY nhung chi 40% HO (< NGUONG_TY_LE_HO_TIN_CAY=0.5)
    # vao nhom TIN_CAY - phan lon HO (60%) di vao 1 tram KHAC (CRAN/khong
    # TIN_CAY) -> KHONG ghi.
    rows = [
        _row(100, 1, 200, 20), _row(100, 1, 201, 10), _row(100, 1, 202, 10),
        _row(100, 1, 999, 60),  # tram dich CRAN (khong TIN_CAY)
    ]
    phan_loai = {
        "100": TOA_DO_DUNG_CHUNG, "200": TIN_CAY, "201": TIN_CAY, "202": TIN_CAY,
        "999": TOA_DO_DUNG_CHUNG,
    }
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1), 202: (21.2, 105.2)}

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert ket_qua == []


def test_tram_nguon_tin_cay_khong_uoc_luong():
    # enb=100 la TIN_CAY (da co toa do that) - KHONG can uoc luong, du dieu
    # kien HO van du (chi de kiem tra dieu kien loc DAU TIEN la kiem tra
    # tram nguon CO phai CRAN khong).
    rows = [_row(100, 1, 200, 60), _row(100, 1, 201, 30), _row(100, 1, 202, 10)]
    phan_loai = {"100": TIN_CAY, "200": TIN_CAY, "201": TIN_CAY, "202": TIN_CAY}
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1), 202: (21.2, 105.2)}

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert ket_qua == []


def test_tram_dich_khong_co_toa_do_bi_loai_khoi_tin_cay():
    # target_enb=203 duoc phan loai TIN_CAY nhung KHONG co trong tram_coords
    # (gia su chua sync RIMS) - PHAI bi loai khoi nhom "tin cay dung duoc",
    # KHONG crash KeyError.
    rows = [
        _row(100, 1, 200, 40), _row(100, 1, 201, 30), _row(100, 1, 202, 20),
        _row(100, 1, 203, 10),
    ]
    phan_loai = {
        "100": TOA_DO_DUNG_CHUNG, "200": TIN_CAY, "201": TIN_CAY, "202": TIN_CAY,
        "203": TIN_CAY,
    }
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1), 202: (21.2, 105.2)}  # 203 THIEU

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert len(ket_qua) == 1
    assert ket_qua[0]["so_tram_dich"] == 3  # KHONG tinh 203
    assert ket_qua[0]["ty_le_ho_tin_cay"] == pytest.approx(0.9)  # 90/100, bo 10 cua 203


def test_nguong_la_hang_so_co_ten():
    assert NGUONG_TY_LE_HO_TIN_CAY == 0.5
    assert NGUONG_SO_TRAM_DICH_TOI_THIEU == 3


def test_gop_theo_tram_dich_cong_don_nhieu_target_lcr():
    # 2 dong CUNG target_enb (khac target_lcr trong du lieu goc, nhung ham
    # nay CHI nhan source_enb/source_sector/target_enb/ho_attempt - khong
    # phan biet target_lcr) - PHAI cong don thanh 1 tram dich, khong tach
    # thanh 2 "tram dich" gia.
    rows = [
        _row(100, 1, 200, 30), _row(100, 1, 200, 30),  # cung target_enb=200, cong don = 60
        _row(100, 1, 201, 30), _row(100, 1, 202, 10),
    ]
    phan_loai = {"100": TOA_DO_DUNG_CHUNG, "200": TIN_CAY, "201": TIN_CAY, "202": TIN_CAY}
    tram_coords = {200: (21.0, 105.0), 201: (21.1, 105.1), 202: (21.2, 105.2)}

    ket_qua = uoc_luong_vi_tri_cran(rows, phan_loai, tram_coords)

    assert len(ket_qua) == 1
    assert ket_qua[0]["so_tram_dich"] == 3  # 200/201/202 - KHONG phai 4
