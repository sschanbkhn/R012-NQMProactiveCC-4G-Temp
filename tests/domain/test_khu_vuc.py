"""
Unit test cho domain/value_objects/khu_vuc.py::khu_vuc_tu_ma_tinh().
Tu: quyet dinh 04/10/2026 (KV1/KV2/KV3 cho tram), xac nhan voi user sau khi
doi chieu SQL that (xem docs/DEV_LOG.md).
"""

from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh, ma_tinh_theo_khu_vuc


def test_ma_moi_moi_kv_ra_dung():
    # 1 ma moi (sau Nghi quyet 306/NQ-CP/2025) dai dien cho moi KV.
    assert khu_vuc_tu_ma_tinh("HNI") == "KV1"
    assert khu_vuc_tu_ma_tinh("HCM") == "KV2"
    assert khu_vuc_tu_ma_tinh("DNG") == "KV3"


def test_ma_cu_van_ra_dung_kv():
    # Giu ca ma CU (truoc sap nhap) - RIMS co the chua dong bo kip cho 1 so
    # tram, KHONG duoc de tram do "bien mat" khoi KV nao.
    assert khu_vuc_tu_ma_tinh("HDG") == "KV1"  # Ha Dong/Ha Tay cu
    assert khu_vuc_tu_ma_tinh("VTU") == "KV2"  # Ba Ria-Vung Tau cu
    assert khu_vuc_tu_ma_tinh("DLK") == "KV3"  # Dak Lak cu
    assert khu_vuc_tu_ma_tinh("PYN") == "KV3"  # Phu Yen cu


def test_dlc_dak_lak_moi_ra_kv3():
    # DLC = Dak Lak MOI (gop Dak Lak cu + Phu Yen cu) - xac nhan bang SQL
    # that (right(tram_name,3): DLK 1.231 tram, PYN 529 tram, ca 2 deu KV3).
    assert khu_vuc_tu_ma_tinh("DLC") == "KV3"


def test_lam_dong_moi_ra_kv2_khong_theo_vung_kinh_te():
    # Lam Dong moi (gop Dak Nong + Lam Dong + Binh Thuan cu) xep KV2 vi ca 3
    # tinh cu do NetAct 10 (NOC2) quan ly - KHAC vung kinh te chinh thuc (Tay
    # Nguyen/Nam Trung Bo), dung quyet dinh van hanh NOC lam chuan.
    assert khu_vuc_tu_ma_tinh("LDG") == "KV2"
    assert khu_vuc_tu_ma_tinh("DNO") == "KV2"  # Dak Nong cu
    assert khu_vuc_tu_ma_tinh("BTN") == "KV2"  # Binh Thuan cu


def test_ma_la_tra_none_khong_tu_doan():
    # "DLC" tung la ma la truoc khi duoc xac nhan (04/10/2026) - gia lap 1 ma
    # chua tung xac nhan de khoa hanh vi "KHONG tu doan".
    assert khu_vuc_tu_ma_tinh("XYZ") is None


def test_rong_hoac_none_tra_none():
    assert khu_vuc_tu_ma_tinh(None) is None
    assert khu_vuc_tu_ma_tinh("") is None


def test_khong_tu_chuan_hoa_chu_thuong_hay_khoang_trang():
    # Khac chuan_hoa_vendor() (CO .strip().upper()) - ma_tinh la cot da chuan
    # hoa san tu truoc (xem station_schemas.py), chu thuong/khoang trang la
    # DAU HIEU LOI can dieu tra rieng, khong nen am tham "sua ho".
    assert khu_vuc_tu_ma_tinh("hni") is None
    assert khu_vuc_tu_ma_tinh(" HNI") is None


def test_ma_tinh_theo_khu_vuc_chieu_nguoc_gom_ca_ma_cu_moi():
    # Chieu nguoc cho GET /stations?khu_vuc=... loc o tang DB - phai gom CA
    # ma cu lan ma moi cua 1 KV (vd KV3 phai co ca DLK/PYN cu lan DLC moi).
    kv3 = ma_tinh_theo_khu_vuc(["KV3"])
    assert "DLK" in kv3
    assert "PYN" in kv3
    assert "DLC" in kv3
    assert "HNI" not in kv3  # thuoc KV1, khong duoc lan sang KV3


def test_ma_tinh_theo_khu_vuc_nhieu_kv_la_hop_cac_tap():
    kv1 = set(ma_tinh_theo_khu_vuc(["KV1"]))
    kv3 = set(ma_tinh_theo_khu_vuc(["KV3"]))
    ca_hai = set(ma_tinh_theo_khu_vuc(["KV1", "KV3"]))
    assert ca_hai == kv1 | kv3


def test_ma_tinh_theo_khu_vuc_rong_tra_rong():
    assert ma_tinh_theo_khu_vuc([]) == []
