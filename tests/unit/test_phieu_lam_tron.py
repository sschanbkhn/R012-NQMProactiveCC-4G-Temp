"""
Unit test co vuot_luat_lam_tron (18/10/2026) - phieu SUCCESS xuat truoc khi lam
tron TB/lech 2 chu so ma nay tinh lai khong con KHONG DAT. MOCK snapshot repo.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from application.phieu_lam_tron import co_vuot_luat_lam_tron
from domain.services.evaluation_service import doi_ket_luan_do_lam_tron

_NGAY = date(2026, 10, 5)


def _snap(cell: str, cot: str, truoc: list, sau: list) -> list[dict]:
    rows = [{"cell_name": cell, "period": "before", cot: v, "snapshot_date": _NGAY - timedelta(days=i + 1)}
            for i, v in enumerate(truoc)]
    rows += [{"cell_name": cell, "period": "after", cot: v, "snapshot_date": _NGAY + timedelta(days=i + 1)}
             for i, v in enumerate(sau)]
    return rows


def _repo(rows):
    r = AsyncMock()
    r.get_by_session_id.return_value = rows
    return r


def test_predicate_TXN092M12_lech_tho_0_5000000000000004_la_doi_do_lam_tron():
    assert doi_ket_luan_do_lam_tron([5, 5, 4, 4, 4, 3], [4, 4, 4, 4, 3, 3], 0.5) is True


def test_predicate_lech_0_51_van_khong_dat_khong_phai_doi():
    assert doi_ket_luan_do_lam_tron([4.0] * 6, [3.49] * 6, 0.5) is False


def test_predicate_thieu_ngay_khong_ket_luan():
    assert doi_ket_luan_do_lam_tron([5, 5, 4], [4, 4, 3], 0.5) is False


async def test_phieu_32084_duoc_danh_dau_phieu_khong_SUCCESS_khong_co_khoa():
    cell = "4G-TXN092M12-HNI"
    rows = [
        {"id": 13514, "cr_session_id": 10707, "cell_name": cell, "trang_thai": "SUCCESS"},
        {"id": 1, "cr_session_id": 10707, "cell_name": cell, "trang_thai": "FAILED"},
    ]
    qos = _repo(_snap(cell, "qos_score", [5, 5, 4, 4, 4, 3], [4, 4, 4, 4, 3, 3]))
    qoe = _repo(_snap(cell, "qoe_score", [5] * 7, [5] * 7))

    co = await co_vuot_luat_lam_tron(rows, qos, qoe)

    assert co == {13514: True}
    qos.get_by_session_id.assert_awaited_once_with(10707)  # 1 lan / session


async def test_chi_so_kia_van_khong_dat_thi_khong_danh_dau():
    cell = "C"
    rows = [{"id": 2, "cr_session_id": 1, "cell_name": cell, "trang_thai": "SUCCESS"}]
    qos = _repo(_snap(cell, "qos_score", [5, 5, 4, 4, 4, 3], [4, 4, 4, 4, 3, 3]))
    qoe = _repo(_snap(cell, "qoe_score", [3] * 7, [2] * 7))  # duoi san -> van KHONG DAT

    assert await co_vuot_luat_lam_tron(rows, qos, qoe) == {2: False}
