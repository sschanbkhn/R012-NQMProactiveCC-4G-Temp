"""
Unit test cho GET /sessions/{id} - kiem response KHONG con qoe_snapshots/
qos_snapshots (20082026). MOCK use case qua dependency_overrides.

VI SAO CAN TEST NAY: 2 mang do bi bo cung luc snapshot chuyen sang PER-CELL -
neu giu, moi session se tra 15 ngay x so cell (17 cell -> 255 diem) trong khi
FE da khong doc 2 mang nay tu 23/07. Test chot lai de khong ai vo tinh them
lai ma khong biet hau qua.
"""

from unittest.mock import AsyncMock

import main
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.inbound.use_case_ports import CrSessionDetail, IGetSessionDetailUseCase
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_session_detail_use_case

SESSION_ID = 553


def _client():
    uc = AsyncMock(spec=IGetSessionDetailUseCase)
    uc.execute.return_value = CrSessionDetail(
        session=CrSession(
            id=SESSION_ID,
            tram_id="112721",
            action="shutdown",
            status=CrStatus.DONE,
            plan_name="plan_test",
        ),
        cell_params=[],
        cr_logs=[],
        affected_cells=[{"cell_name": "4G-CELL-A", "tram_id": "112721", "huong_id": "11"}],
    )
    main.app.dependency_overrides[get_session_detail_use_case] = lambda: uc
    return TestClient(main.app)


def test_response_khong_con_2_mang_snapshot():
    try:
        resp = _client().get(f"/api/v1/sessions/{SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "qoe_snapshots" not in body
        assert "qos_snapshots" not in body
    finally:
        main.app.dependency_overrides.clear()


def test_cac_field_con_lai_van_nguyen_ven():
    # Bo 2 mang KHONG duoc lam mat gi khac (FE dang dung cac field nay).
    try:
        body = _client().get(f"/api/v1/sessions/{SESSION_ID}").json()
        assert body["id"] == SESSION_ID
        assert body["tram_id"] == "112721"
        assert body["status"] == "DONE"
        assert body["affected_cells"] == [
            {"cell_name": "4G-CELL-A", "tram_id": "112721", "huong_id": "11"}
        ]
        assert body["cell_params"] == []
        assert body["cr_logs"] == []
    finally:
        main.app.dependency_overrides.clear()


def test_response_co_duong_dan_log():
    # Cot da co trong DB tu b3f7d21ac504 nhung truoc 04092026 khong lo ra API -
    # muon doc log phai vao DB go tay.
    try:
        uc = AsyncMock(spec=IGetSessionDetailUseCase)
        uc.execute.return_value = CrSessionDetail(
            session=CrSession(
                id=SESSION_ID,
                tram_id="112721",
                action="shutdown",
                status=CrStatus.DONE,
                plan_name="plan_test",
                duong_dan_log="docs/logs/netact_runs/553_20260722.log",
            ),
            cell_params=[],
            cr_logs=[],
            affected_cells=[],
        )
        main.app.dependency_overrides[get_session_detail_use_case] = lambda: uc
        body = TestClient(main.app).get(f"/api/v1/sessions/{SESSION_ID}").json()
        assert body["duong_dan_log"] == "docs/logs/netact_runs/553_20260722.log"
    finally:
        main.app.dependency_overrides.clear()


def test_duong_dan_log_None_voi_session_cu():
    # Session chay TRUOC khi co co che luu log -> None, khong phai chuoi rong.
    try:
        uc = AsyncMock(spec=IGetSessionDetailUseCase)
        uc.execute.return_value = CrSessionDetail(
            session=CrSession(
                id=SESSION_ID, tram_id="112721", action="shutdown",
                status=CrStatus.DONE, plan_name="plan_test",
            ),
            cell_params=[], cr_logs=[], affected_cells=[],
        )
        main.app.dependency_overrides[get_session_detail_use_case] = lambda: uc
        assert TestClient(main.app).get(f"/api/v1/sessions/{SESSION_ID}").json()["duong_dan_log"] is None
    finally:
        main.app.dependency_overrides.clear()
