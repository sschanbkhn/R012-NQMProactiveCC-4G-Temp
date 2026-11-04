"""
Test cho SocHttpAdapter — MOCK, khong goi mang (OQ-01 con block).
Tu: API_CONTRACTS.md SS3; TASK_LIST.md B6.5
"""

import logging
from datetime import datetime, timezone

from adapters.http.soc_http_adapter import SocHttpAdapter


async def test_get_qoe_tra_ve_mock_dung_shape_cho_moi_cell():
    adapter = SocHttpAdapter()
    from_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 7, 7, tzinfo=timezone.utc)

    result = await adapter.get_qoe(["4G-HKM005M11-HNI", "4G-HKM005M12-HNI"], from_dt, to_dt)

    assert len(result) == 2
    for item, cell_name in zip(result, ["4G-HKM005M11-HNI", "4G-HKM005M12-HNI"]):
        assert item["cell_name"] == cell_name
        assert item["metrics"] == [{"time": from_dt.isoformat(), "qoe": 3.5}]


async def test_get_qoe_log_warning_dung_mock_data(caplog):
    adapter = SocHttpAdapter()
    with caplog.at_level(logging.WARNING):
        await adapter.get_qoe(["4G-HKM005M11-HNI"], datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert any("MOCK" in record.message for record in caplog.records)
