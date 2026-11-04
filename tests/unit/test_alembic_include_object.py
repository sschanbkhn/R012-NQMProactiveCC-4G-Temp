"""
Unit test cho alembic/env.py::include_object (LOI 2, 12/08).

Goi TRUC TIEP ham include_object - KHONG chay alembic, KHONG ket noi DB.
Muc dich: khoa hanh vi "bang co that trong DB nhung khong co model thi KHONG
duoc sinh lenh DROP" - bug that da xay ra voi cell_infor (27763 dong).
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def include_object():
    """Nap alembic/env.py de lay ham include_object.

    env.py KHONG phai module import duoc binh thuong (khong nam trong package,
    va khi chay that no tu goi run_migrations_online() o cuoi file). Vi vay:
    nap qua importlib VA chan context.is_offline_mode() de file khong tu chay
    migration - chi lay dinh nghia ham ra dung.
    """
    import alembic

    context_gia = MagicMock()
    # is_offline_mode()=True -> env.py di vao nhanh run_migrations_offline(),
    # nhung context.configure()/begin_transaction() cung la MagicMock nen
    # khong co ket noi DB nao duoc mo.
    context_gia.is_offline_mode.return_value = True
    context_gia.config.config_file_name = None
    context_gia.config.get_main_option.return_value = ""

    context_that = alembic.context
    alembic.context = context_gia
    sys.modules["alembic.context"] = context_gia
    try:
        spec = importlib.util.spec_from_file_location("_alembic_env_test", REPO / "alembic" / "env.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.include_object
    finally:
        alembic.context = context_that
        sys.modules["alembic.context"] = context_that


_SCHEMA = "system_nsn_nqmproactivecc"


def test_bang_co_model_thi_cho_qua(include_object):
    # cr_phieu CO model SQLModel -> phai cho autogenerate xu ly binh thuong
    # (neu chan luon thi moi thay doi hop le cung bi bo qua).
    assert include_object(MagicMock(), "cr_phieu", "table", True, None) is True


def test_bang_khong_co_model_bi_chan(include_object):
    # cell_infor: co THAT trong DB (27763 dong) nhung khong co model ->
    # PHAI tra False de khong sinh op.drop_table('cell_infor').
    assert include_object(MagicMock(), "cell_infor", "table", True, None) is False


def test_bang_la_hoan_toan_cung_bi_chan(include_object):
    # Viet GENERIC, khong hardcode "cell_infor" - bang nao khong co model cung
    # duoc bao ve san, khong phai sua ham nay moi lan.
    assert include_object(MagicMock(), "bang_script_khac_tu_tao", "table", True, None) is False


def test_object_khong_phai_table_thi_cho_qua(include_object):
    # Index/column/FK van phai duoc so sanh binh thuong - filter nay CHI nham
    # vao bang, khong dung toi cac loai object khac.
    for loai in ("index", "column", "foreign_key_constraint", "unique_constraint"):
        assert include_object(MagicMock(), "bat_ky_ten_gi", loai, True, None) is True, loai


def test_bang_tu_metadata_khong_reflected_thi_cho_qua(include_object):
    # reflected=False = object den TU target_metadata (model cua ta), khong
    # phai doc tu DB -> khong bao gio roi vao dien "co trong DB, thieu model".
    # Neu chan ca nhanh nay thi bang MOI se khong bao gio duoc CREATE.
    assert include_object(MagicMock(), "bang_model_moi", "table", False, None) is True
