"""
Unit test cho XoaSessionUseCase + DELETE /sessions/{id} (20082026).
MOCK repo, KHONG cham DB.

Trong tam: LUAT CHAN. Xoa nham 1 session DONE la mat vinh vien bang chung ve
viec tram do da doi tham so RF that - khong khoi phuc duoc tu dau.
"""

from unittest.mock import AsyncMock

import pytest

import main
from application.xoa_session_use_case import XoaSessionUseCase
from domain.entities.cr_session import CrSession, CrStatus
from domain.errors import CrSessionNotFoundError, XoaSessionKhongHopLeError
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_xoa_session_use_case

SESSION_ID = 4242
SO_DONG_MAU = {
    "audit_log_set_null": 0,
    "qos_snapshot": 135,
    "qoe_snapshot": 135,
    "cr_phieu": 4,
    "cr_log": 18,
    "cr_affected_cells": 9,
    "alert_log": 0,
    "cell_params": 3,
    "cr_session": 1,
}


def _session(status: CrStatus, so_cell_thanh_cong=None, so_cell_tong=None) -> CrSession:
    return CrSession(
        id=SESSION_ID,
        tram_id="112721",
        action="shutdown",
        status=status,
        plan_name="plan_test",
        so_cell_thanh_cong=so_cell_thanh_cong,
        so_cell_tong=so_cell_tong,
    )


def _use_case(session, so_rollback: int = 0):
    repo = AsyncMock()
    repo.get_by_id.return_value = session
    repo.dem_session_rollback_tu.return_value = so_rollback
    repo.xoa_cascade.return_value = dict(SO_DONG_MAU)
    return XoaSessionUseCase(repo), repo


class TestLuatChan:
    async def test_FAILED_xoa_duoc_va_tra_so_dong_tung_bang(self):
        uc, repo = _use_case(_session(CrStatus.FAILED, 0, 4))

        so_dong = await uc.execute(SESSION_ID)

        repo.xoa_cascade.assert_awaited_once_with(SESSION_ID)
        assert so_dong == SO_DONG_MAU

    async def test_KHONG_CHAY_xoa_duoc_giong_het_FAILED(self):
        # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") -
        # KHONG_CHAY "sach" hon FAILED (chua tung gui lenh len NetAct) nen
        # duoc xoa an toan CUNG ly do - xem dac ta dau file.
        uc, repo = _use_case(_session(CrStatus.KHONG_CHAY, 0, 4))

        so_dong = await uc.execute(SESSION_ID)

        repo.xoa_cascade.assert_awaited_once_with(SESSION_ID)
        assert so_dong == SO_DONG_MAU

    async def test_DONE_bi_chan_409_va_KHONG_goi_xoa(self):
        uc, repo = _use_case(_session(CrStatus.DONE, 4, 4))

        with pytest.raises(XoaSessionKhongHopLeError) as exc:
            await uc.execute(SESSION_ID)

        # QUAN TRONG hon ca ma loi: KHONG duoc cham vao DB.
        repo.xoa_cascade.assert_not_awaited()
        assert "4/4 tram da doi tham so RF that" in str(exc.value)

    async def test_PARTIAL_SUCCESS_bi_chan_du_chi_1_CELL_thanh_cong(self):
        # 1 tram da doi that VAN la 1 tram can truy duoc - khong duoc xoa.
        uc, repo = _use_case(_session(CrStatus.PARTIAL_SUCCESS, 1, 4))

        with pytest.raises(XoaSessionKhongHopLeError) as exc:
            await uc.execute(SESSION_ID)

        repo.xoa_cascade.assert_not_awaited()
        assert "PARTIAL_SUCCESS" in str(exc.value)
        assert "1/4" in str(exc.value)

    @pytest.mark.parametrize(
        "status",
        [CrStatus.PENDING, CrStatus.RUNNING, CrStatus.EVALUATING, CrStatus.EVAL_PENDING,
         CrStatus.EVALUATED, CrStatus.KHONG_DU_DU_LIEU],
    )
    async def test_moi_status_khac_deu_bi_chan(self, status):
        # Whitelist: chi FAILED xoa duoc. Test nay khoa dieu do lai - them
        # status moi vao he thong thi mac dinh KHONG xoa duoc.
        uc, repo = _use_case(_session(status))

        with pytest.raises(XoaSessionKhongHopLeError):
            await uc.execute(SESSION_ID)
        repo.xoa_cascade.assert_not_awaited()

    async def test_session_cu_thieu_so_CELL_KHONG_doan_la_0(self):
        # "0 tram da doi" la cau NGUY HIEM neu sai - phai noi khong ro.
        uc, _ = _use_case(_session(CrStatus.DONE, None, None))

        with pytest.raises(XoaSessionKhongHopLeError) as exc:
            await uc.execute(SESSION_ID)

        assert "khong ro" in str(exc.value)
        assert "0/" not in str(exc.value)

    async def test_khong_ton_tai_raise_not_found(self):
        uc, repo = _use_case(None)

        with pytest.raises(CrSessionNotFoundError):
            await uc.execute(SESSION_ID)
        repo.xoa_cascade.assert_not_awaited()

    async def test_dang_la_nguon_rollback_thi_chan(self):
        # rollback_of_id la FK NO ACTION - xoa se FK violation. Chan o day,
        # va KHONG tu set NULL dum session khac.
        uc, repo = _use_case(_session(CrStatus.FAILED, 0, 4), so_rollback=2)

        with pytest.raises(XoaSessionKhongHopLeError) as exc:
            await uc.execute(SESSION_ID)

        repo.xoa_cascade.assert_not_awaited()
        assert "rollback" in str(exc.value)


class TestRouter:
    def _client(self, uc):
        main.app.dependency_overrides[get_xoa_session_use_case] = lambda: uc
        return TestClient(main.app)

    def test_FAILED_tra_200_kem_so_dong(self):
        uc = AsyncMock()
        uc.execute.return_value = dict(SO_DONG_MAU)
        try:
            resp = self._client(uc).delete(f"/api/v1/sessions/{SESSION_ID}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == SESSION_ID
            assert body["da_xoa"] is True
            assert body["so_dong_da_xoa"]["cr_phieu"] == 4
            assert body["so_dong_da_xoa"]["cr_session"] == 1
        finally:
            main.app.dependency_overrides.clear()

    def test_DONE_tra_409(self):
        uc = AsyncMock()
        uc.execute.side_effect = XoaSessionKhongHopLeError(
            "Chi xoa duoc session FAILED. Session nay la DONE, co 4/4 tram da doi tham so RF that.",
            session_id=SESSION_ID,
        )
        try:
            resp = self._client(uc).delete(f"/api/v1/sessions/{SESSION_ID}")
            assert resp.status_code == 409
            assert "4/4 tram" in resp.json()["message"]
        finally:
            main.app.dependency_overrides.clear()

    def test_PARTIAL_SUCCESS_tra_409(self):
        uc = AsyncMock()
        uc.execute.side_effect = XoaSessionKhongHopLeError(
            "Chi xoa duoc session FAILED. Session nay la PARTIAL_SUCCESS, co 3/4 tram da doi tham so RF that.",
            session_id=SESSION_ID,
        )
        try:
            resp = self._client(uc).delete(f"/api/v1/sessions/{SESSION_ID}")
            assert resp.status_code == 409
            assert "PARTIAL_SUCCESS" in resp.json()["message"]
        finally:
            main.app.dependency_overrides.clear()

    def test_khong_ton_tai_tra_404(self):
        uc = AsyncMock()
        uc.execute.side_effect = CrSessionNotFoundError("khong ton tai", session_id=SESSION_ID)
        try:
            assert self._client(uc).delete(f"/api/v1/sessions/{SESSION_ID}").status_code == 404
        finally:
            main.app.dependency_overrides.clear()
