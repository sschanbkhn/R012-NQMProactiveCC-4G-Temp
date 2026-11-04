"""
Unit test cho GET /qoe/{cell_name} va GET /sessions/{id}/qoe-cells (16082026).
MOCK use case qua dependency_overrides, KHONG goi CEM that.

Rieng test cuoi (TestSoRequestThucTe) di XUYEN QUA CemHttpAdapter that de dem
so HTTP request - httpx van bi patch nen khong co ket noi mang nao.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import main
from application.get_qoe_cells_use_case import GetQoeCellsUseCase, QoeCellEvaluation
from application.get_qoe_sparkline_use_case import GetQoeSparklineUseCase
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.inbound.use_case_ports import IGetQoeSparklineUseCase
from domain.services.evaluation_service import EvaluationService, MetricEvaluation
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_qoe_cells_use_case, get_qoe_sparkline_use_case

CELL = "4G-SSN087M43-HNI"


def _clear():
    main.app.dependency_overrides.clear()


# === GET /qoe/{cell_name} ===


class TestQoeSparklineRouter:
    def _client(self, data=None):
        uc = AsyncMock(spec=IGetQoeSparklineUseCase)
        uc.execute.return_value = data if data is not None else [
            {"time": "2026-08-14T00:00:00", "qoe": 5.0}
        ]
        main.app.dependency_overrides[get_qoe_sparkline_use_case] = lambda: uc
        return TestClient(main.app), uc

    def test_tra_diem_tho_khong_tinh_danh_gia(self):
        client, _ = self._client()
        try:
            resp = client.get(f"/api/v1/qoe/{CELL}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["cell_name"] == CELL
            assert body["data"] == [{"time": "2026-08-14T00:00:00", "qoe": 5.0}]
            # KHONG co avg/delta/ket_qua - day la endpoint diem THO, giong /qos.
            assert set(body) == {"cell_name", "data"}
        finally:
            _clear()

    def test_chi_truyen_from_khong_truyen_to_thi_422(self):
        client, _ = self._client()
        try:
            assert client.get(f"/api/v1/qoe/{CELL}?from=2026-08-01").status_code == 422
            assert client.get(f"/api/v1/qoe/{CELL}?to=2026-08-07").status_code == 422
        finally:
            _clear()

    def test_from_lon_hon_to_thi_422(self):
        client, _ = self._client()
        try:
            r = client.get(f"/api/v1/qoe/{CELL}?from=2026-08-07&to=2026-08-01")
            assert r.status_code == 422
        finally:
            _clear()

    def test_khoang_qua_60_ngay_thi_422(self):
        client, _ = self._client()
        try:
            assert client.get(f"/api/v1/qoe/{CELL}?from=2026-01-01&to=2026-12-31").status_code == 422
            # Dung 60 ngay -> van cho qua (bien).
            assert client.get(f"/api/v1/qoe/{CELL}?from=2026-08-01&to=2026-09-30").status_code == 200
        finally:
            _clear()

    def test_days_ngoai_1_30_thi_422(self):
        client, _ = self._client()
        try:
            assert client.get(f"/api/v1/qoe/{CELL}?days=0").status_code == 422
            assert client.get(f"/api/v1/qoe/{CELL}?days=31").status_code == 422
            assert client.get(f"/api/v1/qoe/{CELL}?days=30").status_code == 200
        finally:
            _clear()

    def test_khong_truyen_gi_thi_days_mac_dinh_7(self):
        client, uc = self._client()
        try:
            assert client.get(f"/api/v1/qoe/{CELL}").status_code == 200
            assert uc.execute.call_args.args[1] == 7
        finally:
            _clear()


# === GET /sessions/{id}/qoe-cells ===


def _eval(result, avg_before, avg_after, thap_nhat=None, so_ngay_dat=0):
    return MetricEvaluation(
        result=result,
        avg_before=avg_before,
        avg_after=avg_after,
        diem_thap_nhat_sau=thap_nhat,
        so_ngay_dat_sau=so_ngay_dat,
        ly_do_khong_dat="TUT_VA_CHAT_LUONG_KEM" if result == "FAIL" else None,
    )


class TestQoeCellsRouter:
    def _client(self, rows):
        uc = AsyncMock(spec=GetQoeCellsUseCase)
        # Router goi danh_gia_kem_cua_so() (04092026) chu khong con execute():
        # no can CA danh sach cell LAN cua so de tra ra API.
        uc.danh_gia_kem_cua_so.return_value = (rows, {"ngay_cr": date(2026, 8, 13), "before_from": datetime(2026, 8, 6), "before_to": datetime(2026, 8, 12), "after_from": datetime(2026, 8, 14), "after_to": datetime(2026, 8, 20)})
        main.app.dependency_overrides[get_qoe_cells_use_case] = lambda: uc
        return TestClient(main.app), uc

    def test_tra_du_9_truong_moi_cell(self):
        rows = [
            QoeCellEvaluation(
                CELL,
                _eval("FAIL", 5.0, 3.0, 1.0, 2),
                so_ngay_before=7,
                so_ngay_after=6,
                after_points=[3.0] * 6,
            )
        ]
        client, _ = self._client(rows)
        try:
            resp = client.get("/api/v1/sessions/553/qoe-cells")
            assert resp.status_code == 200
            body = resp.json()
            assert body["cr_session_id"] == 553
            assert body["total"] == 1
            item = body["data"][0]
            assert item == {
                "cell_name": CELL,
                "avg_before": 5.0,
                "avg_after": 3.0,
                # SUA 03/10/2026: delta = avg_before - avg_after, DUONG = tut
                # (truoc day AM = tut) - xem domain/services/
                # evaluation_service.py muc "SUA 03/10/2026". 5.0 -> 3.0 la
                # TUT 2 diem nen delta DUONG.
                "delta": 2.0,
                "so_ngay_before": 7,
                "so_ngay_after": 6,
                "ket_qua": "FAIL",
                "diem_thap_nhat_sau": 1.0,
                "so_ngay_dat_sau": 2,
            }
        finally:
            _clear()

    def test_cell_thieu_du_lieu_tra_null_khong_crash(self):
        rows = [
            QoeCellEvaluation(
                "4G-CELL-TRONG",
                _eval("INSUFFICIENT_DATA", None, None),
                so_ngay_before=0,
                so_ngay_after=0,
                after_points=[],
            )
        ]
        client, _ = self._client(rows)
        try:
            item = client.get("/api/v1/sessions/553/qoe-cells").json()["data"][0]
            assert item["ket_qua"] == "INSUFFICIENT_DATA"
            assert item["avg_before"] is None
            assert item["avg_after"] is None
            assert item["delta"] is None
        finally:
            _clear()

    def test_session_khong_co_cell_tra_mang_rong(self):
        client, _ = self._client([])
        try:
            body = client.get("/api/v1/sessions/553/qoe-cells").json()
            assert body["total"] == 0
            assert body["data"] == []
        finally:
            _clear()


# === So request THUC TE xuong CEM ===


class TestSoRequestThucTe:
    async def test_17_cell_7_cong_8_ngay_dung_15_request(self):
        """Di xuyen qua CemHttpAdapter THAT de dem so HTTP request.

        Day la con so quan trong nhat cua thiet ke nay: copy may moc cach QoS
        (1 cell/lan goi) se ra 17 x 2 x 7 = 238 request.

        SUA 09/2026 (D2): 14 -> 15. Cua so FETCH sau gio RONG 8 ngay (T..T+7)
        thay vi 7 ngay (T+1..T+7) de co diem luu period="cr_day" - GIONG
        EvaluateCrUseCase (xem application/get_qoe_cells_use_case.py::execute()).
        Cua so DANH GIA (avg_after) KHONG doi, van dung T+1..T+7.
        """
        from adapters.http.cem_http_adapter import CemHttpAdapter

        cells = [f"4G-CELL-{i:02d}" for i in range(17)]

        class _Resp:
            status_code = 200
            text = ""

            def json(self):
                # Moi ngay tra ve DU 17 cell.
                return {"data": [{"cellName": c, "ux_final": 5.0} for c in cells]}

        client_gia = AsyncMock()
        client_gia.post = AsyncMock(return_value=_Resp())
        client_gia.__aenter__ = AsyncMock(return_value=client_gia)
        client_gia.__aexit__ = AsyncMock(return_value=False)

        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = CrSession(
            id=553, tram_id="112721", action="shutdown", status=CrStatus.DONE,
            plan_name="p", executed_at=datetime(2026, 7, 22, 2, 15, tzinfo=timezone.utc),
        )
        affected_repo = AsyncMock()
        affected_repo.get_by_cr_session_id.return_value = [{"cell_name": c} for c in cells]

        with patch.dict(
            "os.environ", {"CEM_ACCOUNT": "A_TEST", "CEM_HASH_KEY": "K_TEST"}, clear=False
        ), patch("httpx.AsyncClient", return_value=client_gia):
            uc = GetQoeCellsUseCase(
                session_repo, affected_repo, CemHttpAdapter(), EvaluationService()
            )
            ket_qua = await uc.execute(553)

        assert len(ket_qua) == 17
        # before 7 ngay + after (RONG, T..T+7) 8 ngay = 15. KHONG phai 238.
        assert client_gia.post.await_count == 15


class TestQoeSparklineUseCase:
    async def test_mac_dinh_lui_2_ngay_khong_phai_1(self):
        # CEM tre 2 ngay (do that) - khac QoS lui 1 ngay.
        soc_gw = AsyncMock()
        soc_gw.get_qoe.return_value = []
        await GetQoeSparklineUseCase(soc_gw).execute(CELL, days=7)

        _, from_dt, to_dt = soc_gw.get_qoe.await_args.args
        hom_nay = datetime.now(timezone.utc)
        assert 1.5 < (hom_nay - to_dt).days + (hom_nay - to_dt).seconds / 86400 < 2.5
        assert (to_dt - from_dt).days == 7

    async def test_uu_tien_from_to_khi_truyen_ca_hai(self):
        soc_gw = AsyncMock()
        soc_gw.get_qoe.return_value = []
        f = datetime(2026, 7, 15, tzinfo=timezone.utc)
        t = datetime(2026, 7, 21, tzinfo=timezone.utc)
        await GetQoeSparklineUseCase(soc_gw).execute(CELL, days=7, from_dt=f, to_dt=t)

        _, from_dt, to_dt = soc_gw.get_qoe.await_args.args
        assert (from_dt, to_dt) == (f, t)

    async def test_tach_dung_cell_tu_response_nhieu_cell(self):
        soc_gw = AsyncMock()
        soc_gw.get_qoe.return_value = [
            {"cell_name": "4G-KHAC-HNI", "metrics": [{"time": "2026-08-14T00:00:00", "qoe": 1.0}]},
            {"cell_name": CELL, "metrics": [{"time": "2026-08-14T00:00:00", "qoe": 5.0}]},
        ]
        data = await GetQoeSparklineUseCase(soc_gw).execute(CELL)
        assert data == [{"time": "2026-08-14T00:00:00", "qoe": 5.0}]

    async def test_cell_khong_co_trong_response_tra_mang_rong(self):
        soc_gw = AsyncMock()
        soc_gw.get_qoe.return_value = [{"cell_name": "4G-KHAC-HNI", "metrics": []}]
        assert await GetQoeSparklineUseCase(soc_gw).execute(CELL) == []
