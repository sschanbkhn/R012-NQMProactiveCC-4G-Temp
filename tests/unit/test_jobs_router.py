"""
Unit test cho GET /jobs/runs + GET /jobs/runs/{id} (V3a, 12/08) - MOCK
IJobRunLogRepo, KHONG cham DB. Query THAT tren DB nam o
tests/integration/test_job_run_log_repo.py.

3 endpoint POST /jobs/* cung file router KHONG dung toi day - chung chi trigger
BackgroundTasks, goi that se chay job len CTS.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from domain.ports.outbound.repo_ports import IJobRunLogRepo
from infrastructure.dependencies import get_job_run_log_repo

_GMT7 = timezone(timedelta(hours=7))


def _mau_row(id: int = 1, **ghi_de) -> dict:
    # 11 cot cua man hinh danh sach - CO Y khong co chi_tiet, dung nhu
    # JobRunLogRepo.list_job_runs() tra ve.
    row = {
        "id": id,
        "job_type": "xuat_phieu_auto",
        "started_at": datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 8, 20, 3, 5, tzinfo=timezone.utc),
        "trang_thai": "DONE",
        "so_session_quet": 8,
        "so_phieu_thanh_cong": 5,
        "so_phieu_that_bai": 1,
        "so_cell_vuot_gioi_han": 2,
        "error_message": None,
    }
    row.update(ghi_de)
    return row


def _client_with_mock_repo(rows=None, total=0, chi_tiet_row=None):
    mock_repo = AsyncMock(spec=IJobRunLogRepo)
    mock_repo.list_job_runs.return_value = rows if rows is not None else []
    mock_repo.count_job_runs.return_value = total
    mock_repo.get_by_id.return_value = chi_tiet_row
    main.app.dependency_overrides[get_job_run_log_repo] = lambda: mock_repo
    return TestClient(main.app), mock_repo


def _clear_overrides():
    main.app.dependency_overrides.clear()


def test_mac_dinh_size_20_sort_moi_nhat_truoc():
    # Mac dinh PHAI la 20 dong + started_at DESC - man hinh lich su luon xem
    # luot moi nhat truoc (dung index idx_job_run_log_started).
    client, mock_repo = _client_with_mock_repo(rows=[_mau_row(9), _mau_row(8)], total=2)
    try:
        resp = client.get("/api/v1/jobs/runs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["page"] == 1
        assert body["size"] == 20
        assert [r["id"] for r in body["data"]] == [9, 8]

        # sort_by=None -> repo tu ve started_at DESC; order mac dinh "desc"
        args = mock_repo.list_job_runs.call_args.args
        assert args[1] == 1  # page
        assert args[2] == 20  # size
        assert args[3] is None  # sort_by
        assert args[4] == "desc"  # order
    finally:
        _clear_overrides()


def test_loc_theo_trang_thai_truyen_xuong_repo():
    client, mock_repo = _client_with_mock_repo(rows=[_mau_row(1, trang_thai="FAILED")], total=1)
    try:
        resp = client.get("/api/v1/jobs/runs?trang_thai=FAILED")

        assert resp.status_code == 200
        assert resp.json()["data"][0]["trang_thai"] == "FAILED"
        # PHAI xuong CA list VA count - neu chi 1 ben co filter thi total lech
        assert mock_repo.list_job_runs.call_args.args[5] == "FAILED"
        assert mock_repo.count_job_runs.call_args.args[1] == "FAILED"
    finally:
        _clear_overrides()


@pytest.mark.parametrize("gia_tri", ["done", "XONG", "PENDING", "SUCCESS"])
def test_trang_thai_ngoai_whitelist_tra_422(gia_tri):
    # Literal chan ngay o tang validate - request khong bao gio toi duoc repo.
    # "PENDING"/"SUCCESS" la trang thai cua cr_phieu, KHONG phai cua job_run_log
    # (3 gia tri: RUNNING/DONE/FAILED) - lay nham bang la loi de xay ra o FE.
    client, mock_repo = _client_with_mock_repo()
    try:
        resp = client.get(f"/api/v1/jobs/runs?trang_thai={gia_tri}")

        assert resp.status_code == 422
        mock_repo.list_job_runs.assert_not_called()
    finally:
        _clear_overrides()


def test_loc_khoang_ngay_quy_doi_gmt7_va_tron_ven_ngay_cuoi():
    client, mock_repo = _client_with_mock_repo(rows=[_mau_row(1)], total=1)
    try:
        resp = client.get("/api/v1/jobs/runs?tu_ngay=2026-08-15&den_ngay=2026-08-20")

        assert resp.status_code == 200
        tu_moc, den_moc = mock_repo.list_job_runs.call_args.args[6:8]
        # NGAY LICH VN, KHONG phai UTC: 15/08 00:00 +07 (= 14/08 17:00 UTC).
        # Thieu buoc quy doi nay se cat mat 7 tieng dau ngay.
        assert tu_moc == datetime(2026, 8, 15, tzinfo=_GMT7)
        # den_ngay CONG 1 NGAY -> nua khoang, luot chay 09:30 ngay 20/08 VAN
        # duoc tinh (day la loi kinh dien neu de nguyen den_ngay 00:00)
        assert den_moc == datetime(2026, 8, 21, tzinfo=_GMT7)
        assert mock_repo.count_job_runs.call_args.args[2:4] == (tu_moc, den_moc)
    finally:
        _clear_overrides()


def test_chi_mot_dau_mut_van_hop_le():
    # tu_ngay/den_ngay DOC LAP (khac /qos from+to phai di cap): "tu 01/08 den
    # nay" la cach loc tu nhien, khong duoc bat FE bia dau mut con lai.
    client, mock_repo = _client_with_mock_repo(rows=[], total=0)
    try:
        resp = client.get("/api/v1/jobs/runs?tu_ngay=2026-08-01")

        assert resp.status_code == 200
        tu_moc, den_moc = mock_repo.list_job_runs.call_args.args[6:8]
        assert tu_moc == datetime(2026, 8, 1, tzinfo=_GMT7)
        assert den_moc is None
    finally:
        _clear_overrides()


def test_tu_ngay_lon_hon_den_ngay_tra_422():
    client, mock_repo = _client_with_mock_repo()
    try:
        resp = client.get("/api/v1/jobs/runs?tu_ngay=2026-08-20&den_ngay=2026-08-15")

        assert resp.status_code == 422
        mock_repo.list_job_runs.assert_not_called()
    finally:
        _clear_overrides()


@pytest.mark.parametrize("size", [101, 200, 1000])
def test_size_vuot_100_bi_chan(size):
    # Tran 100 theo yeu cau V3a - 1 dong la tong ket ca luot chay, 100 dong da
    # la vai thang lich su.
    client, mock_repo = _client_with_mock_repo()
    try:
        resp = client.get(f"/api/v1/jobs/runs?size={size}")

        assert resp.status_code == 422
        mock_repo.list_job_runs.assert_not_called()
    finally:
        _clear_overrides()


def test_size_100_va_size_1_van_qua():
    # Chan tren la 100 CHU KHONG phai 99 - khoa dung bien de lan sau sua khong
    # vo tinh lech 1 don vi.
    client, _ = _client_with_mock_repo(rows=[], total=0)
    try:
        assert client.get("/api/v1/jobs/runs?size=100").status_code == 200
        assert client.get("/api/v1/jobs/runs?size=1").status_code == 200
        assert client.get("/api/v1/jobs/runs?size=0").status_code == 422
        assert client.get("/api/v1/jobs/runs?page=0").status_code == 422
    finally:
        _clear_overrides()


def test_danh_sach_khong_bao_gio_co_chi_tiet():
    # Quyet dinh V3a: chi_tiet gom TOAN BO session x cell cua 1 luot chay - 20
    # dong se keo theo vai tram KB man hinh danh sach khong dung den.
    client, _ = _client_with_mock_repo(rows=[_mau_row(1)], total=1)
    try:
        resp = client.get("/api/v1/jobs/runs")

        assert resp.status_code == 200
        assert "chi_tiet" not in resp.json()["data"][0]
    finally:
        _clear_overrides()


def test_chi_tiet_tra_ve_o_endpoint_rieng():
    chi_tiet = {"sessions": [{"cr_session_id": 553, "cell_vuot_gioi_han": [{"cell_name": "4G-A"}]}]}
    client, mock_repo = _client_with_mock_repo(chi_tiet_row=_mau_row(7) | {"chi_tiet": chi_tiet})
    try:
        resp = client.get("/api/v1/jobs/runs/7")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 7
        assert body["chi_tiet"]["sessions"][0]["cr_session_id"] == 553
        # 10 cot cua danh sach VAN co day du o ban chi tiet (JobRunDetail ke thua
        # JobRunListItem) - FE khong phai goi 2 lan de co du thong tin 1 dong
        assert body["so_session_quet"] == 8
        # V2 (12/08): field dry_run da bi bo khoi schema
        assert "dry_run" not in body
        assert mock_repo.get_by_id.call_args.args[0] == 7
    finally:
        _clear_overrides()


def test_chi_tiet_id_khong_ton_tai_tra_404():
    # Repo tra None (no khong biet gi ve HTTP) - ROUTER doi thanh 404.
    client, _ = _client_with_mock_repo(chi_tiet_row=None)
    try:
        resp = client.get("/api/v1/jobs/runs/999999")

        assert resp.status_code == 404
    finally:
        _clear_overrides()


def test_chi_tiet_null_van_tra_200():
    # Luot chay FAILED som chua kip ghi chi_tiet -> chi_tiet=None. KHONG duoc
    # nham voi "khong tim thay dong" (404) - dong VAN ton tai.
    client, _ = _client_with_mock_repo(
        chi_tiet_row=_mau_row(3, trang_thai="FAILED", error_message="CTS timeout")
        | {"chi_tiet": None}
    )
    try:
        resp = client.get("/api/v1/jobs/runs/3")

        assert resp.status_code == 200
        body = resp.json()
        assert body["chi_tiet"] is None
        assert body["error_message"] == "CTS timeout"
    finally:
        _clear_overrides()


def test_sort_by_ngoai_whitelist_tra_422():
    # An toan lop 1 (Literal o router). Lop 2 la whitelist trong repo - xem
    # tests/integration/test_job_run_log_repo.py.
    client, mock_repo = _client_with_mock_repo()
    try:
        resp = client.get("/api/v1/jobs/runs?sort_by=chi_tiet")

        assert resp.status_code == 422
        mock_repo.list_job_runs.assert_not_called()
    finally:
        _clear_overrides()
