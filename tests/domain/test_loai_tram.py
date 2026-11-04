"""
Test loai_tram_tu_ten_cell() - domain/services/loai_tram.py.
Tu: quyet dinh 02/10/2026 (KHONG chay CR cho small cell).

THEM 11-12/10/2026 (yeu cau truc tiep user, "PHAN LOAI TRAM + DO ANH HUONG"):
nhom_loai_tram()/loai_tram_tu_ten_tram() - xem dac ta trong loai_tram.py.
"""

import pytest

from domain.services.loai_tram import (
    LOAI_TRAM_SMALL_CELL,
    NHOM_IBS,
    NHOM_KHAC,
    NHOM_MACRO,
    NHOM_SMALL_CELL,
    loai_tram_tu_ten_cell,
    loai_tram_tu_ten_tram,
    nhom_loai_tram,
)


class TestDungMau:
    @pytest.mark.parametrize(
        "cell_name,mong_doi",
        [
            ("4G-TPO065S11-TQG", "S"),  # vi du goc tu de bai
            ("4G-DDA155M12-HNI", "M"),  # macro, du lieu that 110548
            ("4G-STY008W12-HNI", "W"),
            ("4G-CGY002F11-HNI", "F"),
            ("4G-ABC001E11-HNI", "E"),
            ("4G-ABC001X11-HNI", "X"),
            ("4G-ABC001R11-HNI", "R"),
            ("4G-ABC001P11-HNI", "P"),
        ],
    )
    def test_tach_dung_loai_tram(self, cell_name, mong_doi):
        assert loai_tram_tu_ten_cell(cell_name) == mong_doi


class TestSmallCell:
    def test_S_la_small_cell(self):
        assert "S" in LOAI_TRAM_SMALL_CELL

    def test_P_la_small_cell(self):
        assert "P" in LOAI_TRAM_SMALL_CELL

    @pytest.mark.parametrize("loai", ["M", "W", "F", "E", "X", "R"])
    def test_cac_loai_khac_KHONG_phai_small_cell(self, loai):
        assert loai not in LOAI_TRAM_SMALL_CELL

    def test_dung_dung_2_gia_tri_khong_nhieu_hon(self):
        # CHOT 02/10/2026 tu du lieu that - khong tu suy doan them loai nao
        # khac ngoai S/P (xem docstring dau file loai_tram.py).
        assert LOAI_TRAM_SMALL_CELL == {"S", "P"}


class TestTenSaiMau:
    @pytest.mark.parametrize(
        "cell_name",
        [
            None,
            "",
            "4G-X-HNI",  # thieu loai tram + so cell giua ma site va tinh
            "4G-TPO065-TQG",  # thieu loai tram (chi co so site, khong co ky tu loai)
            "TPO065S11-TQG",  # thieu prefix "4G-"
            "4G-tpo065s11-TQG",  # chu thuong, khong khop [A-Z]
            "4G-TPO065S11-TQ",  # tinh chi 2 ky tu (khong du 3 [A-Z]{3})
        ],
    )
    def test_ten_sai_mau_tra_None(self, cell_name):
        assert loai_tram_tu_ten_cell(cell_name) is None


class TestNhomLoaiTram:
    @pytest.mark.parametrize("chu_cai", ["M", "W", "B", "E", "X", "R"])
    def test_macro(self, chu_cai):
        assert nhom_loai_tram(chu_cai) == NHOM_MACRO

    def test_ibs(self):
        assert nhom_loai_tram("F") == NHOM_IBS

    @pytest.mark.parametrize("chu_cai", ["S", "P"])
    def test_small_cell(self, chu_cai):
        assert nhom_loai_tram(chu_cai) == NHOM_SMALL_CELL

    @pytest.mark.parametrize("chu_cai", ["Q", "Z", "T", "A", "", None])
    def test_chu_cai_la_tra_khac(self, chu_cai):
        assert nhom_loai_tram(chu_cai) == NHOM_KHAC


class TestLoaiTramTuTenTram:
    @pytest.mark.parametrize(
        "ten_tram,mong_doi",
        [
            ("4G-CGY029M-HNI", NHOM_MACRO),
            ("4G-STY008W-HNI", NHOM_MACRO),
            ("4G-ABC001B-HNI", NHOM_MACRO),
            ("4G-ABC001E-HNI", NHOM_MACRO),
            ("4G-ABC001X-HNI", NHOM_MACRO),
            ("4G-ABC001R-HNI", NHOM_MACRO),
            ("4G-CGY002F-HNI", NHOM_IBS),
            ("4G-TPO065S-TQG", NHOM_SMALL_CELL),
            ("4G-ABC001P-HNI", NHOM_SMALL_CELL),
        ],
    )
    def test_moi_chu_cai_dung_nhom(self, ten_tram, mong_doi):
        assert loai_tram_tu_ten_tram(ten_tram) == mong_doi

    @pytest.mark.parametrize(
        "ten_tram",
        [
            "UL-CGY029M-HNI",
            "UL_CGY029M-HNI",
            "LN-CGY029S-HNI",
            "SN-CGY029F-HNI",
        ],
    )
    def test_tien_to_khac_4G_van_tach_dung(self, ten_tram):
        # Tien to UL-/UL_/LN-/SN-... - GIONG quy uoc _SITE_RE (ho_delaunay.py),
        # khac _LOAI_TRAM_RE (ten CELL) chi nhan "4G-".
        assert loai_tram_tu_ten_tram(ten_tram) in {NHOM_MACRO, NHOM_SMALL_CELL, NHOM_IBS}

    @pytest.mark.parametrize(
        "ten_tram",
        [
            None,
            "",
            "TEN LA KHONG DUNG MAU",
            "4G-X-HNI",  # thieu so site
            "4G-CGY029M11-HNI",  # co them so cell/sector - day la TEN CELL, khong phai TEN TRAM
        ],
    )
    def test_ten_la_tra_khac(self, ten_tram):
        assert loai_tram_tu_ten_tram(ten_tram) == NHOM_KHAC


class TestMaKhuVucCoSo:
    # THEM 15/10/2026 (yeu cau truc tiep user, "SUA TACH TEN TRAM MA KHU VUC
    # CO SO (Q01)") - ma khu vuc HCM dang CHU+SO (Q01=Quan 1, Q08=Quan 8)
    # truoc day khong khop _LOAI_TU_TEN_TRAM_RE (doi [A-Z]{2,4} thuan chu),
    # roi oan vao KHAC - xem 5 vi du dung trong de bai goc.
    @pytest.mark.parametrize(
        "ten_tram,mong_doi",
        [
            ("4G-Q01219S-HCM", NHOM_SMALL_CELL),  # khu vuc Q01, so tram 219
            ("4G-Q08096M-HCM", NHOM_MACRO),  # khu vuc Q08, so tram 096
            ("UL_Q01149M_HCM", NHOM_MACRO),  # tien to UL_ + dau "_"
            ("4G-BDH288M-HNI", NHOM_MACRO),  # ma khu vuc CHU THUAN (BDH) van dung nhu cu
        ],
    )
    def test_ma_khu_vuc_co_so_tach_dung(self, ten_tram, mong_doi):
        assert loai_tram_tu_ten_tram(ten_tram) == mong_doi

    def test_ten_cell_ma_khu_vuc_co_so_nhan_ra_small_cell(self):
        # Ten CELL (co them so sector "11" sau chu loai "S") cua cung 1 tram
        # Q01219S o tren - loai_tram_tu_ten_cell() da dung TU TRUOC (khong can
        # sua), xac nhan lai o day de khong bi regress khi dung chung _MA_KHU_VUC.
        assert loai_tram_tu_ten_cell("4G-Q01219S11-HCM") == "S"
        assert loai_tram_tu_ten_cell("4G-Q01219S11-HCM") in LOAI_TRAM_SMALL_CELL
