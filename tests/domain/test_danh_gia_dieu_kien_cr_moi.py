"""
Unit test cho domain/services/danh_gia_dieu_kien_cr_moi.py - ham THUAN (khong
I/O). 2 kich ban DU LIEU THAT (session 3641/1811) da kiem rieng o
tests/integration/test_danh_gia_dieu_kien_cr_moi_integration.py - file nay
kiem CAC NHANH LOGIC bang du lieu gia lap, don gian hon de doc.
"""

from dataclasses import dataclass

from domain.services.danh_gia_dieu_kien_cr_moi import (
    LY_DO_BAND_KHONG_PHAI_1800,
    LY_DO_KHONG_XAC_DINH_BAND,
    LY_DO_VUOT_2_CELL_SECTOR,
    gan_nhan_ngoai_dieu_kien_moi,
)


@dataclass
class _Cell:
    # Gia lap toi thieu CellParam - chi can 3 truong ham dang test dung toi.
    cell_name: str
    huong_id: str | None
    priority: int | None


def test_dat_du_dieu_kien_moi_list_rong():
    cells = [_Cell("A", "11", 1), _Cell("B", "11", 2)]
    dist_name = {"A": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "B": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-13"}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan == {"A": [], "B": []}


def test_khong_tim_thay_dist_name_nhan_khong_xac_dinh_band():
    cells = [_Cell("A", "11", 1)]
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, {})  # khong co dist_name nao
    assert nhan["A"] == [LY_DO_KHONG_XAC_DINH_BAND]


def test_lncel_4x_5x_nhan_band_khong_phai_1800():
    cells = [_Cell("A", "11", 1), _Cell("B", "11", 2)]
    dist_name = {
        "A": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-41",
        "B": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-53",
    }
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan["A"] == [LY_DO_BAND_KHONG_PHAI_1800]
    assert nhan["B"] == [LY_DO_BAND_KHONG_PHAI_1800]


def test_lncel_112_khong_khop_2_chu_so_nhan_band_khong_phai_1800():
    # Du lieu that tung phat hien (khao sat 110548) - 3 chu so, KHONG phai 2.
    cells = [_Cell("A", "11", 1)]
    dist_name = {"A": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-112"}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan["A"] == [LY_DO_BAND_KHONG_PHAI_1800]


def test_dung_2_cell_1_sector_khong_vuot():
    cells = [_Cell("A", "11", 1), _Cell("B", "51", 2)]  # cung sector 1 (11%10=1, 51%10=1)
    dist_name = {c.cell_name: "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11" for c in cells}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan == {"A": [], "B": []}


def test_3_cell_1_sector_cell_thu_3_theo_priority_vuot():
    # sector 2: huong_id 12 (X=1,Y=2) va 52 (X=5,Y=2) deu %10=2.
    cells = [_Cell("A", "12", 1), _Cell("B", "52", 2), _Cell("C", "12", 3)]
    dist_name = {c.cell_name: "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11" for c in cells}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan["A"] == []
    assert nhan["B"] == []
    assert nhan["C"] == [LY_DO_VUOT_2_CELL_SECTOR]


def test_huong_id_none_gom_vao_sector_none_rieng_cung_chiu_tran():
    cells = [_Cell("A", None, 1), _Cell("B", None, 2), _Cell("C", None, 3)]
    dist_name = {c.cell_name: "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11" for c in cells}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan["A"] == []
    assert nhan["B"] == []
    assert nhan["C"] == [LY_DO_VUOT_2_CELL_SECTOR]


def test_cell_co_ca_2_ly_do_cung_luc():
    # Sector 1 co 3 cell, cell thu 3 (theo priority) LAI mang LNCEL sai band -
    # phai nhan CA 2 ly do, khong phai chi 1.
    cells = [_Cell("A", "11", 1), _Cell("B", "51", 2), _Cell("C", "31", 3)]
    dist_name = {
        "A": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11",
        "B": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-13",
        "C": "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-42",
    }
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    assert nhan["A"] == []
    assert nhan["B"] == []
    assert set(nhan["C"]) == {LY_DO_BAND_KHONG_PHAI_1800, LY_DO_VUOT_2_CELL_SECTOR}


def test_priority_none_xep_cuoi_khong_crash():
    cells = [_Cell("A", "11", None), _Cell("B", "11", 1), _Cell("C", "11", 2)]
    dist_name = {c.cell_name: "PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11" for c in cells}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cells, dist_name)
    # B, C (co priority) duoc giu; A (priority None, xep cuoi) la cell vuot.
    assert nhan["B"] == []
    assert nhan["C"] == []
    assert nhan["A"] == [LY_DO_VUOT_2_CELL_SECTOR]
