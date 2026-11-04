"""
Unit test cho cong tat CEM_ENABLED (16082026) - get_soc_gateway() chon
CemHttpAdapter hay SocHttpAdapter mock.

Day la CHOT AN TOAN quan trong nhat cua lan tich hop nay: bat nham len tren
production se lam QoE that tham gia danh gia cap session va co the doi
qoe_result cua cac session dang chay. Mac dinh PHAI la mock.
"""

import logging
from unittest.mock import patch

from adapters.http.cem_http_adapter import CemHttpAdapter
from adapters.http.soc_http_adapter import SocHttpAdapter
from infrastructure.dependencies import get_soc_gateway
from infrastructure.dependencies import logger as logger_module

_ENV_CEM = {"CEM_ACCOUNT": "NET_KTM_TEST", "CEM_HASH_KEY": "KEY_TEST_KHONG_THAT"}


def test_mac_dinh_khong_co_bien_thi_dung_mock():
    # Khong set CEM_ENABLED -> PHAI la mock (hanh vi cu, khong regression cho
    # moi truong dang chay).
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("CEM_ENABLED", None)
        assert isinstance(get_soc_gateway(), SocHttpAdapter)


def test_CEM_ENABLED_false_thi_dung_mock():
    with patch.dict("os.environ", {"CEM_ENABLED": "false"}, clear=False):
        assert isinstance(get_soc_gateway(), SocHttpAdapter)


def test_CEM_ENABLED_true_thi_dung_cem():
    with patch.dict("os.environ", {**_ENV_CEM, "CEM_ENABLED": "true"}, clear=False):
        assert isinstance(get_soc_gateway(), CemHttpAdapter)


def test_CEM_ENABLED_TRUE_hoa_va_khoang_trang_van_nhan():
    # Nguoi sua .env go "TRUE" hoac " true " la chuyen binh thuong - khong duoc
    # am tham roi ve mock (nguoi dung tuong da bat that).
    for gia_tri in ("TRUE", "True", " true "):
        with patch.dict("os.environ", {**_ENV_CEM, "CEM_ENABLED": gia_tri}, clear=False):
            assert isinstance(get_soc_gateway(), CemHttpAdapter), f"CEM_ENABLED={gia_tri!r}"


def test_gia_tri_la_thi_ve_mock_khong_crash():
    # Fail-safe: gia tri khong hieu duoc -> ve MOCK (an toan), khong phai CEM.
    for gia_tri in ("1", "yes", "bat", ""):
        with patch.dict("os.environ", {**_ENV_CEM, "CEM_ENABLED": gia_tri}, clear=False):
            assert isinstance(get_soc_gateway(), SocHttpAdapter), f"CEM_ENABLED={gia_tri!r}"


def test_nhanh_cem_log_WARNING_noi_ro_dang_dung_api_that(caplog):
    # WARNING (khong phai INFO) CO CHU DINH: cong tac nay doi ket qua danh gia
    # that, phai noi bat de khong ai bat nham roi de chay nhieu ngay.
    with patch.dict("os.environ", {**_ENV_CEM, "CEM_ENABLED": "true"}, clear=False):
        with caplog.at_level(logging.INFO):
            get_soc_gateway()

    ban_ghi = [r for r in caplog.records if "CemHttpAdapter" in r.message]
    assert len(ban_ghi) == 1
    assert ban_ghi[0].levelno == logging.WARNING
    assert "CEM THAT" in ban_ghi[0].message
    assert "CEM_ENABLED=true" in ban_ghi[0].message


def test_nhanh_mock_log_INFO_noi_ro_dang_dung_mock(caplog):
    with patch.dict("os.environ", {"CEM_ENABLED": "false"}, clear=False):
        with caplog.at_level(logging.INFO):
            get_soc_gateway()

    ban_ghi = [r for r in caplog.records if "SocHttpAdapter" in r.message]
    assert len(ban_ghi) == 1
    assert ban_ghi[0].levelno == logging.INFO
    assert "MOCK" in ban_ghi[0].message
    assert "CEM_ENABLED=false" in ban_ghi[0].message


def test_moi_lan_goi_deu_log_khong_chi_lan_dau():
    # Provider duoc goi MOI REQUEST (FastAPI Depends) - neu chi log 1 lan roi
    # im thi doc log giua ca ngay se khong biet dang chay adapter nao.
    with patch.dict("os.environ", {"CEM_ENABLED": "false"}, clear=False):
        with patch.object(logger_module, "warning") as w, patch.object(logger_module, "info") as i:
            get_soc_gateway()
            get_soc_gateway()
    assert i.call_count == 2
    assert w.call_count == 0


def test_ca_hai_deu_implement_cung_port():
    # Doi wiring KHONG duoc pha use case nao - 2 adapter phai thay the duoc cho
    # nhau hoan toan.
    from domain.ports.outbound.gateway_ports import ISocGateway

    with patch.dict("os.environ", {**_ENV_CEM, "CEM_ENABLED": "true"}, clear=False):
        assert isinstance(get_soc_gateway(), ISocGateway)
    with patch.dict("os.environ", {"CEM_ENABLED": "false"}, clear=False):
        assert isinstance(get_soc_gateway(), ISocGateway)
