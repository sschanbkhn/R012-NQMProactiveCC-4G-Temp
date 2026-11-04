"""
Unit test cho XoaPhieuUseCase + DELETE /phieu/{id} (20082026; SUA 04/10/2026 -
XOA MEM thay the HARD DELETE cu, quyet dinh 04/10/2026).
MOCK repo, KHONG cham DB, KHONG goi CTS.

Trong tam: chan SUCCESS (khong doi) + xoa MEM khong con la "undo, xuat lai
duoc" - nguoc lai, PHAI chan tao lai (xem test_xuat_phieu_use_case.py::
test_cell_co_phieu_da_xoa_tu_choi_409_khong_tao_lai cho phan XuatPhieuUseCase).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

import main
from application.xoa_phieu_use_case import XoaPhieuUseCase
from domain.errors import XoaPhieuKhongHopLeError
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_xoa_phieu_use_case

PHIEU_ROW_ID = 777
CELL = "4G-SSN104M12-HNI"


def _phieu(trang_thai: str, phieu_id=None, deleted_at=None) -> dict:
    return {
        "id": PHIEU_ROW_ID,
        "cr_session_id": 553,
        "cell_name": CELL,
        "trang_thai": trang_thai,
        "phieu_id": phieu_id,
        "deleted_at": deleted_at,
    }


def _use_case(phieu: dict | None):
    repo = AsyncMock()
    repo.get_by_id.return_value = phieu
    repo.xoa.return_value = 1
    return XoaPhieuUseCase(repo), repo


class TestLuatChan:
    @pytest.mark.parametrize(
        "trang_thai",
        ["FAILED", "PENDING", "KHONG_XUAT_VUOT_GIOI_HAN", "KHONG_XUAT_HET_LUOT_THU",
         "KHONG_XUAT_THIEU_DU_LIEU"],
    )
    async def test_moi_trang_thai_khac_SUCCESS_deu_xoa_duoc(self, trang_thai):
        uc, repo = _use_case(_phieu(trang_thai))

        ket_qua = await uc.execute(PHIEU_ROW_ID)

        repo.xoa.assert_awaited_once_with(PHIEU_ROW_ID)
        assert ket_qua["cell_name"] == CELL
        assert ket_qua["trang_thai"] == trang_thai

    async def test_SUCCESS_bi_chan_va_KHONG_goi_xoa(self):
        uc, repo = _use_case(_phieu("SUCCESS", phieu_id="19207"))

        with pytest.raises(XoaPhieuKhongHopLeError) as exc:
            await uc.execute(PHIEU_ROW_ID)

        repo.xoa.assert_not_awaited()
        # Message phai chi ra phieu_id CTS de nguoi dung lien he dung phieu.
        assert "19207" in str(exc.value)
        assert "CTS" in str(exc.value)

    async def test_khong_tim_thay_tra_dict_rong(self):
        uc, repo = _use_case(None)

        assert await uc.execute(PHIEU_ROW_ID) == {}
        repo.xoa.assert_not_awaited()


class TestXoaMemKhongTaoLaiDuoc:
    # SUA 04/10/2026 (quyet dinh 04/10/2026) - DAO NGUOC y nghia cu cua ban
    # test nay. Truoc day (hard delete) xoa xong cell "bien mat sach", xuat lai
    # duoc binh thuong. Gio dong VAN CON trong bang (chi danh dau deleted_at) -
    # get_by_session_cell() PHAI THAY no, KHONG duoc tra None. Phan chan tao
    # lai thuc su (PhieuDaXoaError, 409) nam ben XuatPhieuUseCase - test o day
    # chi xac nhan HOP DONG repo: sau execute(), dong do mang deleted_at co gia
    # tri khi tra cuu lai.
    async def test_sau_khi_xoa_get_by_session_cell_van_thay_dong_kem_deleted_at(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = _phieu("FAILED")
        trang_thai_hien_tai = {"deleted_at": None}

        async def _xoa(id):
            trang_thai_hien_tai["deleted_at"] = datetime(2026, 10, 4, tzinfo=timezone.utc)
            return 1

        async def _get_by_session_cell(sid, cell):
            return _phieu("FAILED", deleted_at=trang_thai_hien_tai["deleted_at"])

        repo.xoa.side_effect = _xoa
        repo.get_by_session_cell.side_effect = _get_by_session_cell

        assert (await repo.get_by_session_cell(553, CELL))["deleted_at"] is None
        await XoaPhieuUseCase(repo).execute(PHIEU_ROW_ID)
        assert (await repo.get_by_session_cell(553, CELL))["deleted_at"] is not None


class TestXoaHaiLan:
    # THEM 04/10/2026 (quyet dinh 04/10/2026) - goi DELETE lai tren dong DA xoa
    # PHAI bao ro rang, KHONG duoc im lang coi nhu vua xoa thanh cong lan nua
    # (repo.xoa() that su se khong lam gi - WHERE deleted_at IS NULL).
    async def test_lan_dau_goi_repo_xoa_message_none(self):
        uc, repo = _use_case(_phieu("FAILED"))

        ket_qua = await uc.execute(PHIEU_ROW_ID)

        repo.xoa.assert_awaited_once_with(PHIEU_ROW_ID)
        assert ket_qua["message"] is None

    async def test_lan_2_khong_goi_lai_repo_xoa_tra_message_da_xoa_truoc_do(self):
        da_xoa_tu = datetime(2026, 10, 4, 1, 0, 0, tzinfo=timezone.utc)
        uc, repo = _use_case(_phieu("FAILED", deleted_at=da_xoa_tu))

        ket_qua = await uc.execute(PHIEU_ROW_ID)

        repo.xoa.assert_not_awaited()
        assert ket_qua["message"] == "Phieu nay da duoc xoa truoc do"
        assert ket_qua["cell_name"] == CELL


class TestRouter:
    def _client(self, uc):
        main.app.dependency_overrides[get_xoa_phieu_use_case] = lambda: uc
        return TestClient(main.app)

    def test_FAILED_tra_200(self):
        uc = AsyncMock()
        uc.execute.return_value = {"id": PHIEU_ROW_ID, "cell_name": CELL, "trang_thai": "FAILED"}
        try:
            resp = self._client(uc).delete(f"/api/v1/phieu/{PHIEU_ROW_ID}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["da_xoa"] is True
            assert body["cell_name"] == CELL
            assert body["trang_thai"] == "FAILED"
        finally:
            main.app.dependency_overrides.clear()

    def test_KHONG_XUAT_tra_200(self):
        uc = AsyncMock()
        uc.execute.return_value = {
            "id": PHIEU_ROW_ID, "cell_name": CELL, "trang_thai": "KHONG_XUAT_THIEU_DU_LIEU",
        }
        try:
            resp = self._client(uc).delete(f"/api/v1/phieu/{PHIEU_ROW_ID}")
            assert resp.status_code == 200
            assert resp.json()["trang_thai"] == "KHONG_XUAT_THIEU_DU_LIEU"
        finally:
            main.app.dependency_overrides.clear()

    def test_SUCCESS_tra_409(self):
        uc = AsyncMock()
        uc.execute.side_effect = XoaPhieuKhongHopLeError(
            "Phieu 19207 da len CTS, khong xoa duoc o day. Lien he team CTS de xoa ben do.",
            id=PHIEU_ROW_ID,
        )
        try:
            resp = self._client(uc).delete(f"/api/v1/phieu/{PHIEU_ROW_ID}")
            assert resp.status_code == 409
            assert "19207" in resp.json()["message"]
        finally:
            main.app.dependency_overrides.clear()

    def test_xoa_lan_2_tra_200_kem_message_da_xoa_truoc_do(self):
        # THEM 04/10/2026 - router chi CHUYEN TIEP message tu use case, khong
        # tu suy luan gi them.
        uc = AsyncMock()
        uc.execute.return_value = {
            "id": PHIEU_ROW_ID, "cell_name": CELL, "trang_thai": "FAILED",
            "message": "Phieu nay da duoc xoa truoc do",
        }
        try:
            resp = self._client(uc).delete(f"/api/v1/phieu/{PHIEU_ROW_ID}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["da_xoa"] is True
            assert body["message"] == "Phieu nay da duoc xoa truoc do"
        finally:
            main.app.dependency_overrides.clear()

    def test_khong_ton_tai_tra_404(self):
        uc = AsyncMock()
        uc.execute.return_value = {}
        try:
            assert self._client(uc).delete(f"/api/v1/phieu/{PHIEU_ROW_ID}").status_code == 404
        finally:
            main.app.dependency_overrides.clear()
