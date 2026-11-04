"""
Unit test cho GetSessionDetailUseCase — MOCK session_repo/cell_repo/
affected_cells_repo/cr_log_repo (I/O bien ngoai). chart_use_case DA BO
(20082026) - GetEvaluationChartUseCase bi xoa cung luc snapshot chuyen sang
per-cell, use case nay khong con phu thuoc no.
Tu: docs/DEV_LOG.md muc Phuong an B (22072026, DA DUYET thiet ke).

Muc tieu: xac nhan GET /sessions/{id} tra CA 2 danh sach - cell_params (12
cell Nhanh B, hanh vi CU khong doi) VA affected_cells (47 cell Nhanh A, MOI
them) - khong lan lon, khong lam vo cai cu. cr_logs (22072026) - THAT su doc
tu cr_log (truoc gio LUON []).
"""

from unittest.mock import AsyncMock

import pytest

from application.get_session_detail_use_case import GetSessionDetailUseCase
from domain.entities.cr_session import CrSession, CrStatus
from domain.errors import CrSessionNotFoundError

SESSION_ID = 42


def _make_use_case(affected_cells_return=None, cr_logs_return=None):
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = CrSession(
        id=SESSION_ID, tram_id="110548", action="shutdown", status=CrStatus.DONE, plan_name="plan_test"
    )

    cell_repo = AsyncMock()
    cell_repo.get_by_cr_session_id.return_value = ["cell_param_fake"]  # gia lap 12 cell Nhanh B

    affected_cells_repo = AsyncMock()
    affected_cells_repo.get_by_cr_session_id.return_value = (
        affected_cells_return
        if affected_cells_return is not None
        else [
            {"cell_name": "4G-CELL-A", "tram_id": "115750", "huong_id": "11"},
            {"cell_name": "4G-CELL-B", "tram_id": "114820", "huong_id": "11"},
        ]
    )

    cr_log_repo = AsyncMock()
    cr_log_repo.get_by_cr_session_id.return_value = cr_logs_return if cr_logs_return is not None else []

    uc = GetSessionDetailUseCase(session_repo, cell_repo, affected_cells_repo, cr_log_repo)
    return uc, session_repo, cell_repo, affected_cells_repo, cr_log_repo


class TestAffectedCellsBenCanhCellParams:
    async def test_tra_ca_2_danh_sach_khong_lan_lon(self):
        uc, _, cell_repo, affected_cells_repo, _ = _make_use_case()

        result = await uc.execute(SESSION_ID)

        # cell_params (Nhanh B) GIU NGUYEN hanh vi cu - khong doi
        assert result.cell_params == ["cell_param_fake"]
        cell_repo.get_by_cr_session_id.assert_awaited_once_with(SESSION_ID)

        # affected_cells (Nhanh A) MOI them - danh sach RIENG, khong nam
        # trong/thay the cell_params
        assert result.affected_cells == [
            {"cell_name": "4G-CELL-A", "tram_id": "115750", "huong_id": "11"},
            {"cell_name": "4G-CELL-B", "tram_id": "114820", "huong_id": "11"},
        ]
        affected_cells_repo.get_by_cr_session_id.assert_awaited_once_with(SESSION_ID)

    async def test_session_cu_khong_co_affected_cells_tra_rong_khong_loi(self):
        # Session tao TRUOC 22072026 (Phuong an B) - KHONG backfill (xac nhan
        # voi user, du lieu test) - phai tra [] binh thuong, khong crash.
        uc, _, _, _, _ = _make_use_case(affected_cells_return=[])

        result = await uc.execute(SESSION_ID)

        assert result.affected_cells == []
        assert result.cell_params == ["cell_param_fake"]  # cell_params van co binh thuong


class TestCrLogsDocTuDB:
    # 22072026 (xac nhan voi user) - cr_logs THAT su doc tu cr_log_repo, KHONG
    # con hardcode [] nhu truoc.
    async def test_tra_dung_cr_logs_tu_repo_dung_thu_tu(self):
        logs = [
            {"step": 1, "step_name": "Validate input", "status": "success", "message": "Input hop le", "pct": 5, "created_at": "2026-07-15T09:00:00Z"},
            {"step": 2, "step_name": "Query tram + tao session", "status": "success", "message": "Tao session #196", "pct": 10, "created_at": "2026-07-15T09:00:01Z"},
        ]
        uc, _, _, _, cr_log_repo = _make_use_case(cr_logs_return=logs)

        result = await uc.execute(SESSION_ID)

        # cr_log_repo.get_by_cr_session_id() DA tu sort created_at tang dan
        # (xem adapters/postgres/cr_log_repo.py) - use case chi truyen thang
        # qua, KHONG sort lai o day.
        assert result.cr_logs == logs
        cr_log_repo.get_by_cr_session_id.assert_awaited_once_with(SESSION_ID)

    async def test_session_khong_co_log_nao_tra_rong_khong_loi(self):
        # Session cu (truoc khi _log_step() duoc them vao _emit()/_fail()) -
        # tra [] tu nhien, khong crash - GIONG cach affected_cells xu ly.
        uc, _, _, _, _ = _make_use_case(cr_logs_return=[])

        result = await uc.execute(SESSION_ID)

        assert result.cr_logs == []


class TestEdgeCases:
    async def test_session_khong_ton_tai_raise_not_found(self):
        uc, session_repo, _, _, _ = _make_use_case()
        session_repo.get_by_id.return_value = None

        with pytest.raises(CrSessionNotFoundError):
            await uc.execute(999_999_999)
