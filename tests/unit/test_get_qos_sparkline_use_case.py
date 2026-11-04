"""
Unit test cho GetQosSparklineUseCase — MOCK network_gw (INetworkGateway), khong
goi CTS that. Truoc gio (den 21072026) chua co test rieng cho use case nay.
Tu: docs/API_CONTRACTS.md Section 6 (GET /qos/{cell_name}); TASK_LIST.md C1.7;
docs/DEV_LOG.md muc "them param days cho /qos/{cell}" (21072026).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from application.get_qos_sparkline_use_case import GetQosSparklineUseCase

CELL_NAME = "4G-STY008M43-HNI"


def _make_mocks(metrics: list[dict]):
    network_gw = AsyncMock()
    network_gw.get_qos_metrics.return_value = [{"cell_name": CELL_NAME, "metrics": metrics}]
    return network_gw


class TestWindowTinhTuDays:
    async def test_days_7_from_bang_to_tru_7_ngay(self):
        # Khong assert gio tuyet doi (phu thuoc datetime.now() luc chay test) -
        # chi assert DO RONG window (to - from) dung 7 ngay, dung yeu cau
        # "from = to - days".
        network_gw = _make_mocks([{"time": "2026-07-19T00:00:00Z", "qos": 5}])
        uc = GetQosSparklineUseCase(network_gw)

        await uc.execute(CELL_NAME, days=7)

        call_args = network_gw.get_qos_metrics.call_args.args
        cell_names, from_dt, to_dt = call_args
        assert cell_names == [CELL_NAME]
        assert to_dt - from_dt == timedelta(days=7)

    async def test_to_dt_la_hom_qua_khong_phai_hom_nay(self):
        # CTS lag ~2 ngay (da xac nhan thuc te khi goi that) - to=hom nay se
        # thuong ra rong hoac thieu ngay cuoi, gay hieu nham la loi. Assert
        # to_dt nam trong khoang [now-2d, now-1d) de chiu duoc thoi gian chay
        # test (vai giay/mili giay) ma khong flaky.
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)

        before_call = datetime.now(timezone.utc)
        await uc.execute(CELL_NAME, days=7)
        after_call = datetime.now(timezone.utc)

        to_dt = network_gw.get_qos_metrics.call_args.args[2]
        # to_dt = (now ben trong execute) - 1 ngay, voi "now ben trong" nam
        # giua before_call/after_call - tru 1 ngay ca 2 dau de ra khoang dung.
        assert before_call - timedelta(days=1) <= to_dt <= after_call - timedelta(days=1)


class TestDefaultVaBienDays:
    async def test_khong_truyen_days_mac_dinh_la_7(self):
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)

        await uc.execute(CELL_NAME)  # khong truyen days

        from_dt, to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        assert to_dt - from_dt == timedelta(days=7)

    async def test_days_1_min_window_dung_1_ngay(self):
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)

        await uc.execute(CELL_NAME, days=1)

        from_dt, to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        assert to_dt - from_dt == timedelta(days=1)

    async def test_days_30_max_window_dung_30_ngay(self):
        # Chan tren 30 ap dung o router (Query ge=1 le=30) - use case tu no
        # khong tu gioi han, chi verify tinh toan dung khi nhan days=30.
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)

        await uc.execute(CELL_NAME, days=30)

        from_dt, to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        assert to_dt - from_dt == timedelta(days=30)


class TestWindowTuongMinhFromTo:
    # Gap 1 (22072026, xac nhan voi user) - lay QoS quanh 1 ngay CR trong qua
    # khu, KHONG neo cung "hom qua" nhu nhanh days.
    async def test_truyen_ca_from_va_to_dung_nguyen_khong_tinh_lai(self):
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)
        from_dt = datetime(2026, 7, 8, tzinfo=timezone.utc)
        to_dt = datetime(2026, 7, 22, tzinfo=timezone.utc)

        await uc.execute(CELL_NAME, days=7, from_dt=from_dt, to_dt=to_dt)

        call_from_dt, call_to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        # Dung NGUYEN gia tri truyen vao - KHONG bi ghi de boi "days" (days=7
        # o day CO truyen nhung phai bi bo qua vi from_dt/to_dt uu tien hon).
        assert call_from_dt == from_dt
        assert call_to_dt == to_dt

    async def test_chi_truyen_1_trong_2_roi_ve_nhanh_days_mac_dinh(self):
        # Router da chan truong hop nay (422 neu chi truyen 1 trong 2), nhung
        # use case tu no van phai an toan neu bi goi truc tiep (vd tu test/
        # script khac) - KHONG dung "nua window" sai, rot ve tinh tu days.
        network_gw = _make_mocks([])
        uc = GetQosSparklineUseCase(network_gw)
        from_dt = datetime(2026, 7, 8, tzinfo=timezone.utc)

        await uc.execute(CELL_NAME, days=3, from_dt=from_dt, to_dt=None)

        call_from_dt, call_to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        assert call_to_dt - call_from_dt == timedelta(days=3)  # tinh tu days, khong dung from_dt=2026-07-08

    async def test_khong_truyen_from_to_van_chay_nhu_cu_khong_regression(self):
        network_gw = _make_mocks([{"time": "2026-07-19T00:00:00Z", "qos": 5}])
        uc = GetQosSparklineUseCase(network_gw)

        await uc.execute(CELL_NAME, days=7)  # tuong duong goi truoc khi co from_dt/to_dt

        call_from_dt, call_to_dt = network_gw.get_qos_metrics.call_args.args[1:3]
        assert call_to_dt - call_from_dt == timedelta(days=7)


class TestResponseCauTruc:
    async def test_tra_ve_dung_list_metrics_cua_cell_khop_ten(self):
        metrics = [
            {"time": "2026-07-18T00:00:00Z", "qos": 3},
            {"time": "2026-07-19T00:00:00Z", "qos": 5},
        ]
        network_gw = _make_mocks(metrics)
        uc = GetQosSparklineUseCase(network_gw)

        data = await uc.execute(CELL_NAME, days=7)

        assert data == metrics
        for point in data:
            assert "time" in point
            assert "qos" in point

    async def test_khong_khop_cell_name_trong_ket_qua_gateway_tra_ve_rong(self):
        # Gateway tra ve entry cua cell KHAC (vd nhap sai ten, hoac CTS tra
        # thieu) - use case KHONG duoc doan bua, phai tra [] (dung logic goc,
        # khong doi khi them days).
        network_gw = AsyncMock()
        network_gw.get_qos_metrics.return_value = [{"cell_name": "4G-CELL-KHAC", "metrics": [{"time": "x", "qos": 1}]}]
        uc = GetQosSparklineUseCase(network_gw)

        data = await uc.execute(CELL_NAME, days=7)

        assert data == []

    async def test_gateway_tra_list_rong_use_case_tra_list_rong(self):
        network_gw = AsyncMock()
        network_gw.get_qos_metrics.return_value = []
        uc = GetQosSparklineUseCase(network_gw)

        data = await uc.execute(CELL_NAME, days=7)

        assert data == []
