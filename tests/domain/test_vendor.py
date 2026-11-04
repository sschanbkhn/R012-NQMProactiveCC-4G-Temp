"""
Test chuan_hoa_vendor() — domain/value_objects/vendor.py (V2 buoc 2).

Chia 3 nhom: (1) 4 gia tri THAT da do tren DB, (2) dau vao rong/thieu,
(3) dau vao la — nhom 3 la ly do ham nay ton tai.
"""

import pytest

from domain.value_objects.vendor import Vendor, chuan_hoa_vendor


class TestGiaTriThat:
    """4 gia tri DUY NHAT do duoc tren 58.230 dong ngay 13/09/2026."""

    @pytest.mark.parametrize(
        "ten_thiet_bi,mong_doi",
        [
            ("NOKIA", Vendor.NOKIA),  # 22.794 dong
            ("ERICSSON", Vendor.ERICSSON),  # 19.573 dong
            ("HUAWEI", Vendor.HUAWEI),  # 11.247 dong
            ("ZTE", Vendor.ZTE),  # 4.616 dong
        ],
    )
    def test_4_gia_tri_that_khop_dung(self, ten_thiet_bi, mong_doi):
        assert chuan_hoa_vendor(ten_thiet_bi) is mong_doi

    def test_khong_gia_tri_that_nao_ra_unknown(self):
        """Tren du lieu HIEN TAI, UNKNOWN phai la nhanh KHONG BAO GIO chay.

        Neu test nay do, nghia la ham chuan hoa dang gan nhan sai cho tram that
        - nghiem trong hon han viec no tra UNKNOWN cho gia tri la."""
        that = ["NOKIA", "ERICSSON", "HUAWEI", "ZTE"]
        assert [chuan_hoa_vendor(v) for v in that] == [
            Vendor.NOKIA,
            Vendor.ERICSSON,
            Vendor.HUAWEI,
            Vendor.ZTE,
        ]


class TestRongVaThieu:
    """None / rong -> UNKNOWN, KHONG nem loi, KHONG tra None."""

    @pytest.mark.parametrize("dau_vao", [None, "", "   ", "\t", "\n", "  \t\n  "])
    def test_rong_ra_unknown(self, dau_vao):
        assert chuan_hoa_vendor(dau_vao) is Vendor.UNKNOWN

    def test_none_khong_nem_loi(self):
        # Ham nam tren duong DOC cua GET /stations, goi 1 lan MOI DONG - nem
        # loi se lam hong ca trang danh sach chi vi 1 tram thieu du lieu.
        assert chuan_hoa_vendor(None) is Vendor.UNKNOWN


class TestChuanHoaDinhDang:
    """Chu thuong / khoang trang thua VAN phai khop dung vendor.

    Du lieu DB hien sach (0 chu thuong, 0 khoang trang thua) nhung cot la
    VARCHAR tu do - va tham so nguoi dung go o buoc 4 (?vendor=nokia) thi
    KHONG sach. Day la nhom test bao ve duong do."""

    @pytest.mark.parametrize(
        "dau_vao,mong_doi",
        [
            ("nokia", Vendor.NOKIA),
            ("Nokia", Vendor.NOKIA),
            ("NoKiA", Vendor.NOKIA),
            (" NOKIA ", Vendor.NOKIA),
            ("  nokia  ", Vendor.NOKIA),
            ("\tZTE\n", Vendor.ZTE),
            ("ericsson", Vendor.ERICSSON),
            (" Huawei", Vendor.HUAWEI),
        ],
    )
    def test_trim_va_upper(self, dau_vao, mong_doi):
        assert chuan_hoa_vendor(dau_vao) is mong_doi


class TestGiaTriLa:
    """Gia tri KHONG khop -> UNKNOWN. KHONG doan, KHONG nem loi, KHONG bo qua.

    Day la ly do ham nay ton tai: RIMS co the sync ve bat ky chuoi nao."""

    @pytest.mark.parametrize(
        "dau_vao",
        [
            "SAMSUNG",  # vendor that nhung chua co tren mang nay
            "CISCO",
            "NSN",  # ten cu cua Nokia - CO Y khong map (xem docstring vendor.py)
            "HW",  # viet tat Huawei - CO Y khong map
            "NOKIA SIEMENS",  # chuoi dai hon, KHONG duoc khop nhanh "NOKIA"
            "NOKIA_5G",
            "NOKIA-",
            "ZTE ZTE",
            "0",
            "-",
            "unknown",  # chinh chu "unknown" cung KHONG duoc coi la hop le
            "UNKNOWN",
        ],
    )
    def test_gia_tri_la_ra_unknown(self, dau_vao):
        assert chuan_hoa_vendor(dau_vao) is Vendor.UNKNOWN

    def test_khong_khop_chuoi_con(self):
        """"NOKIA SIEMENS" KHONG duoc thanh NOKIA.

        Khop phai la BANG NHAU tuyet doi sau chuan hoa, khong phai startswith/in.
        Neu dung `in` thi "NOKIA_CU_KHONG_DUNG" cung se thanh NOKIA - gan nhan
        sai cho tram that."""
        assert chuan_hoa_vendor("NOKIA SIEMENS") is Vendor.UNKNOWN
        assert chuan_hoa_vendor("NOKIAX") is Vendor.UNKNOWN
        assert chuan_hoa_vendor("XNOKIA") is Vendor.UNKNOWN

    def test_unknown_khong_the_di_vao_tu_dau_vao(self):
        """Chuoi "UNKNOWN" tu DB van ra Vendor.UNKNOWN - nhung vi no KHONG khop
        tap hop le, khong phai vi no "la mot vendor ten UNKNOWN"."""
        assert chuan_hoa_vendor("UNKNOWN") is Vendor.UNKNOWN
        assert "UNKNOWN" not in {
            v.value for v in Vendor if v is not Vendor.UNKNOWN
        }, "UNKNOWN khong duoc nam trong tap vendor hop le"


class TestEnum:
    def test_ke_thua_str(self):
        # Giong CrStatus - value khop thang chuoi khi serialize JSON.
        assert Vendor.NOKIA == "NOKIA"
        assert isinstance(Vendor.NOKIA, str)

    def test_du_5_gia_tri(self):
        assert {v.value for v in Vendor} == {
            "NOKIA",
            "ERICSSON",
            "HUAWEI",
            "ZTE",
            "UNKNOWN",
        }

    def test_tap_hop_le_suy_tu_enum_khong_go_tay(self):
        """Them vendor moi vao enum thi no phai TU DONG duoc chap nhan.

        Chan loi: ai do them Vendor.SAMSUNG nhung quen sua danh sach chuoi
        trong ham -> chuan_hoa_vendor("SAMSUNG") van tra UNKNOWN."""
        from domain.value_objects.vendor import _HOP_LE  # noqa: PLC2701

        assert _HOP_LE == {v.value for v in Vendor if v is not Vendor.UNKNOWN}
        assert len(_HOP_LE) == 4
