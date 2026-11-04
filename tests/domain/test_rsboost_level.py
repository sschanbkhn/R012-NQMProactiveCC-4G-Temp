"""
Unit test cho RsboostLevel — RSBOOST_SCALE, next_level(), from_raw(), to_xml_value().
Tu: BUSINESS_RULES.md Section 5; TASK_LIST.md B2.2
"""

from domain.value_objects.rsboost_level import RSBOOST_SCALE, RsboostLevel


def test_rsboost_scale_is_4_buoc():
    # BUSINESS_RULES.md SS5.1 dong 188 — da xac nhan voi user: dung 4 phan tu
    assert RSBOOST_SCALE == [-3.0, 0.0, 3.0, 6.0]


def test_next_level_tang_1_buoc():
    # BUSINESS_RULES.md SS5.2 — rsboost_new = RSBOOST_SCALE[current_index + 1]
    assert RsboostLevel(-3.0).next_level() == RsboostLevel(0.0)
    assert RsboostLevel(0.0).next_level() == RsboostLevel(3.0)
    assert RsboostLevel(3.0).next_level() == RsboostLevel(6.0)


def test_next_level_cap_o_bac_cao_nhat():
    # BUSINESS_RULES.md SS5.2 dong 198-201 — da o 6dB (max) -> khong doi
    assert RsboostLevel(6.0).next_level() == RsboostLevel(6.0)


def test_constructor_chap_nhan_gia_tri_lien_tuc_khong_crash():
    # C1.4-fix12 (21072026) - bug that: session #198/tram 111139,
    # rsboost_current=1.77 (dB THAT tren mang, khong nam tren scale) tung
    # lam crash ValueError. Constructor PHAI chap nhan bat ky gia tri nao,
    # giu nguyen (KHONG snap).
    assert RsboostLevel(1.77).value == 1.77
    assert RsboostLevel(-1.5).value == -1.5
    assert RsboostLevel(4.2).value == 4.2


def test_next_level_tu_gia_tri_lien_tuc_snap_len_buoc_chuan_gan_nhat():
    # C1.4-fix12 - gia tri hien tai KHONG nam tren scale (dB that tu mang) ->
    # next_level() phai tim buoc chuan NHO NHAT LON HON gia tri do (KHONG
    # crash, KHONG dung .index()).
    assert RsboostLevel(1.77).next_level() == RsboostLevel(3.0)
    assert RsboostLevel(-1.5).next_level() == RsboostLevel(0.0)
    assert RsboostLevel(4.2).next_level() == RsboostLevel(6.0)


def test_next_level_gia_tri_vuot_buoc_cao_nhat_khong_doi():
    # Gia tri THAT co the > 6.0 (vd loi cau hinh mang) - khong co buoc nao
    # cao hon de tang, giu nguyen (an toan mang, giong truong hop =6.0).
    assert RsboostLevel(7.5).next_level() == RsboostLevel(7.5)


def test_from_raw_gia_tri_da_nam_trong_scale():
    assert RsboostLevel.from_raw(3.0) == RsboostLevel(3.0)
    assert RsboostLevel.from_raw(-3.0) == RsboostLevel(-3.0)


def test_from_raw_lam_tron_ve_bac_gan_nhat():
    # BUSINESS_RULES.md SS5.2 dong 213 — -4.0dB: cach -3.0 la 1.0, gan nhat -> -3.0
    assert RsboostLevel.from_raw(-4.0) == RsboostLevel(-3.0)
    # 1.0dB gan 0.0 (cach 1.0) hon 3.0 (cach 2.0)
    assert RsboostLevel.from_raw(1.0) == RsboostLevel(0.0)


def test_from_raw_tie_chon_bac_thap_hon():
    # BUSINESS_RULES.md SS5.2 dong 210 — tie (nam chinh giua) -> chon bac THAP HON
    assert RsboostLevel.from_raw(-1.5) == RsboostLevel(-3.0)  # giua -3.0 va 0.0
    assert RsboostLevel.from_raw(1.5) == RsboostLevel(0.0)    # giua 0.0 va 3.0
    assert RsboostLevel.from_raw(4.5) == RsboostLevel(3.0)    # giua 3.0 va 6.0


def test_to_xml_value_bo_trailing_zero():
    # BUSINESS_RULES.md SS5.3 dong 220-227 — DUNG: "3dB", SAI: "3.0dB" / "3"
    assert RsboostLevel(3.0).to_xml_value() == "3dB"
    assert RsboostLevel(-3.0).to_xml_value() == "-3dB"
    assert RsboostLevel(0.0).to_xml_value() == "0dB"
    assert RsboostLevel(6.0).to_xml_value() == "6dB"
