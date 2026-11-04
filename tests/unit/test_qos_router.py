"""
Unit test cho api/routers/qos.py - validate query param from/to (Gap 1,
22072026). MOCK use case qua FastAPI dependency_overrides, KHONG goi CTS that.
"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from domain.ports.inbound.use_case_ports import IGetQosSparklineUseCase
from infrastructure.dependencies import get_qos_sparkline_use_case

CELL_NAME = "4G-STY008M43-HNI"


def _client_with_mock_use_case():
    mock_use_case = AsyncMock(spec=IGetQosSparklineUseCase)
    mock_use_case.execute.return_value = [{"time": "2026-07-08T00:00:00Z", "qos": 4}]
    main.app.dependency_overrides[get_qos_sparkline_use_case] = lambda: mock_use_case
    client = TestClient(main.app)
    return client, mock_use_case


def _clear_overrides():
    main.app.dependency_overrides.clear()


class TestValidateFromTo:
    def test_khong_truyen_from_to_van_200_dung_hanh_vi_cu(self):
        client, mock_use_case = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}")
            assert resp.status_code == 200
            # from_dt/to_dt truyen xuong use case PHAI la None (khong tu tinh
            # o router) - use case tu quyet dinh fallback ve days.
            call_kwargs = mock_use_case.execute.call_args
            assert call_kwargs.args[2] is None
            assert call_kwargs.args[3] is None
        finally:
            _clear_overrides()

    def test_truyen_ca_from_va_to_200_va_truyen_dung_xuong_use_case(self):
        client, mock_use_case = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?from=2026-07-08&to=2026-07-22")
            assert resp.status_code == 200
            from_dt, to_dt = mock_use_case.execute.call_args.args[2:4]
            assert from_dt.date().isoformat() == "2026-07-08"
            assert to_dt.date().isoformat() == "2026-07-22"
        finally:
            _clear_overrides()

    def test_chi_truyen_from_thieu_to_422(self):
        client, _ = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?from=2026-07-08")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_chi_truyen_to_thieu_from_422(self):
        client, _ = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?to=2026-07-22")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_from_lon_hon_to_422(self):
        client, _ = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?from=2026-07-22&to=2026-07-08")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khoang_vuot_qua_60_ngay_422(self):
        client, _ = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?from=2026-01-01&to=2026-12-31")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khoang_dung_60_ngay_hop_le(self):
        client, _ = _client_with_mock_use_case()
        try:
            resp = client.get(f"/api/v1/qos/{CELL_NAME}?from=2026-07-01&to=2026-08-30")  # dung 60 ngay
            assert resp.status_code == 200
        finally:
            _clear_overrides()
