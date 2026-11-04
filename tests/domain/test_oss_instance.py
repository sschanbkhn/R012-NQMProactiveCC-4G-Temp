"""
Test OssInstance (domain/value_objects/oss_instance.py) - repr() KHONG duoc
lo user/password. Tu: bao loi 27/09/2026 (OssInstance nam trong PlanResult/
PreviewResult, moi log/exception/pytest assert in nguyen doi tuong se lo
credential NetAct neu khong tat repr tren 2 field nay).
"""

from domain.value_objects.oss_instance import OssInstance

_OSS = OssInstance(instance_id="NA09", host="10.212.242.20", user="test_user", password="test_password_bimat")


def test_repr_khong_chua_password():
    assert "test_password_bimat" not in repr(_OSS)


def test_repr_khong_chua_user():
    assert "test_user" not in repr(_OSS)


def test_repr_van_co_instance_id_va_host():
    # repr=False chi tat 2 field nhay cam - instance_id/host (KHONG phai bi
    # mat) van can hien de con debug duoc dang route sai vao OSS nao.
    dai_dien = repr(_OSS)
    assert "NA09" in dai_dien
    assert "10.212.242.20" in dai_dien


def test_str_cung_khong_chua_password():
    # str() dataclass mac dinh goi lai __repr__ - kiem tra ca 2 duong f-string
    # hay co the dung de log ("%s" % obj, f"{obj}", print(obj)).
    assert "test_password_bimat" not in str(_OSS)


def test_eq_va_hash_van_dung_du_password_khong_hien_trong_repr():
    # repr=False KHONG anh huong toi __eq__/__hash__ (van tu dong sinh tu
    # TAT CA field) - 2 OssInstance khac password PHAI khac nhau, dung cho
    # TriggerCrUseCase._chon_oss_va_loc_cells() gom nhom/phat hien CR_NHIEU_OSS.
    khac_password = OssInstance(instance_id="NA09", host="10.212.242.20", user="test_user", password="khac")
    assert _OSS != khac_password
    assert _OSS == OssInstance(
        instance_id="NA09", host="10.212.242.20", user="test_user", password="test_password_bimat"
    )
