"""
Unit test cho Qrxlevmin — QRXLEVMIN_FLOOR, decrease(), to_xml_value().
Tu: BUSINESS_RULES.md Section 6; TASK_LIST.md B2.3
"""

import dataclasses

import pytest

from domain.value_objects.qrxlevmin import QRXLEVMIN_FLOOR, Qrxlevmin


def test_qrxlevmin_floor_la_am_144():
    assert QRXLEVMIN_FLOOR == -144


def test_decrease_binh_thuong_giam_4dbm():
    # BUSINESS_RULES.md SS6.1 dong 254
    assert Qrxlevmin(-128).decrease() == Qrxlevmin(-132)


def test_decrease_tai_floor_da_bang_khong_doi():
    # BUSINESS_RULES.md SS6.1 dong 261-263 — qrxlevmin_current = -144 -> khong doi
    assert Qrxlevmin(-144).decrease() == Qrxlevmin(-144)


def test_decrease_tai_floor_se_vuot_clamp_ve_floor():
    # BUSINESS_RULES.md SS6.1 dong 256-259 — -142 - 4 = -146 < -144 -> clamp -144
    assert Qrxlevmin(-142).decrease() == Qrxlevmin(-144)


def test_decrease_tra_ve_instance_moi_khong_mutate():
    original = Qrxlevmin(-128)
    result = original.decrease()
    assert result is not original
    assert original.value == -128  # goc khong doi
    assert result.value == -132


def test_to_xml_value_gia_tri_am():
    # BUSINESS_RULES.md SS6.2 dong 268-271 — integer thuan, co dau am, khong ".0"
    assert Qrxlevmin(-144).to_xml_value() == "-144"
    assert Qrxlevmin(-128).to_xml_value() == "-128"


def test_frozen_khong_cho_mutate_truc_tiep():
    q = Qrxlevmin(-128)
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.value = -999
