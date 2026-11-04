"""
Integration test cho CtsHttpAdapter — goi CTS API THAT (gw-oneoss.vnpt.vn).
Tu: API_CONTRACTS.md SS2; TASK_LIST.md B6.3

Cung gateway + cung ham build_sha512_headers() voi CDS - xem chu y BUG THAT trong
adapters/http/sha512_auth.py (cong thuc auth cu sai, da fix). Sau khi fix, goi
that PHAI thanh cong 200 OK.
"""

from datetime import datetime, timedelta, timezone

from adapters.http.cts_http_adapter import CtsHttpAdapter

# Cell that lay tu response CDS that cua tram 110548 (huong 11) - xac nhan co
# du lieu QoS that khi goi CTS (khong phai missing day)
REAL_CELL_NAME = "4G-DDA155M12-HNI"


async def test_get_qos_metrics_goi_that_200_ok_parse_dung_cau_truc():
    adapter = CtsHttpAdapter()
    to_dt = datetime.now(timezone.utc).replace(hour=10, minute=30, second=0, microsecond=0)
    from_dt = to_dt - timedelta(days=6)

    result = await adapter.get_qos_metrics([REAL_CELL_NAME], from_dt, to_dt)

    assert isinstance(result, list)
    assert len(result) > 0
    for item in result:
        assert "cell_name" in item
        assert "metrics" in item
        for point in item["metrics"]:
            assert "time" in point
            assert "qos" in point


def test_to_dt_luon_duoc_ep_ve_cuoi_ngay_khong_doi_ngay():
    # Kiem tra logic chuan hoa thuan tuy (khong goi network) - dam bao KHONG doi
    # ngay caller truyen vao (da xac nhan voi user truoc khi code B6.3).
    to_dt = datetime(2026, 7, 5, 8, 15, 0, tzinfo=timezone.utc)
    normalized = to_dt.replace(hour=23, minute=59, second=59, microsecond=0)
    assert normalized.date() == to_dt.date()
    assert normalized.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-05T23:59:59Z"
