"""
Unit test cho POST /jobs/xuat-phieu-auto va .../xem-truoc (20082026).
MOCK gateway + repo, KHONG POST len CTS, KHONG cham DB that.

Trong tam 3 thu de sai nhat o day:
  1. XEM TRUOC phai KHONG ghi gi va KHONG POST - no la loi hua ban an toan
     cho nut "chay that", loi hua do phai kiem duoc.
  2. XEM TRUOC va CHAY THAT phai ra CUNG danh sach cell. Lech nhau thi xem
     truoc thanh cai bay: nguoi bam thay 3 phieu roi he thong xuat 30.
  3. 409 phai tra TRUOC khi vao background - neu kiem khoa trong background
     thi nguoi bam nhan 202 roi khong co gi xay ra.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main
from api.routers import jobs as jobs_router
from application.xuat_phieu_use_case import XUAT_PHIEU_AFTER_DAYS
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_job_run_log_repo, get_xuat_phieu_use_case

XEM_TRUOC = "/api/v1/jobs/xuat-phieu-auto/xem-truoc"
CHAY_THAT = "/api/v1/jobs/xuat-phieu-auto"


def _hom_nay_vn() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=7)).date()


def _ngay_hop_le() -> tuple[str, str]:
    """1 khoang 3 ngay CHAC CHAN qua duoc 3 chan an toan."""
    den = _hom_nay_vn() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
    return str(den - timedelta(days=2)), str(den)


@pytest.fixture
def don_override():
    yield
    main.app.dependency_overrides.clear()


def _client(use_case=None, job_repo=None):
    if use_case is None:
        use_case = AsyncMock()
        # Mac dinh tra ket qua RONG hop le - de test nao khong quan tam noi
        # dung van dung duoc client nay.
        use_case.xem_truoc.return_value = {"tong_phieu_se_xuat": 0, "sessions": []}
    job_repo = job_repo or AsyncMock()
    job_repo.insert.return_value = {"id": 555}
    main.app.dependency_overrides[get_xuat_phieu_use_case] = lambda: use_case
    main.app.dependency_overrides[get_job_run_log_repo] = lambda: job_repo
    return TestClient(main.app), use_case, job_repo


def _patch_khoa(lay_duoc: bool = True):
    """Gia lap advisory lock. Patch TRONG api.routers.jobs (noi import vao)."""

    class _Khoa:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return lay_duoc

        async def __aexit__(self, *a):
            return False

    return patch.object(jobs_router, "giu_khoa", _Khoa)


# === C: 3 CHAN AN TOAN (ap dung cho CA HAI endpoint) ===


class TestChanAnToan:
    @pytest.mark.parametrize("url", [XEM_TRUOC, CHAY_THAT])
    def test_khoang_31_ngay_tra_422(self, url, don_override):
        den = _hom_nay_vn() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
        tu = den - timedelta(days=30)  # 31 ngay ke ca 2 dau mut
        client, use_case, _ = _client()

        with _patch_khoa():
            resp = client.post(url, json={"tu_ngay": str(tu), "den_ngay": str(den)})

        assert resp.status_code == 422
        assert "31 ngay" in resp.json()["detail"]
        # Chan TRUOC khi lam bat cu viec gi - khong duoc quet roi moi tu choi.
        use_case.xem_truoc.assert_not_awaited()
        use_case.execute_all_pending.assert_not_awaited()

    @pytest.mark.parametrize("url", [XEM_TRUOC, CHAY_THAT])
    def test_dung_30_ngay_thi_QUA(self, url, don_override):
        # Bien: 30 ngay la HOP LE, 31 moi bi chan. Test nay giu cho gioi han
        # khong bi lech 1 don vi khi ai do sua lai phep tinh.
        den = _hom_nay_vn() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
        tu = den - timedelta(days=29)
        client, _, _ = _client()

        with _patch_khoa():
            resp = client.post(url, json={"tu_ngay": str(tu), "den_ngay": str(den)})

        assert resp.status_code in (200, 202)

    @pytest.mark.parametrize("url", [XEM_TRUOC, CHAY_THAT])
    def test_tu_ngay_sau_den_ngay_tra_422(self, url, don_override):
        den = _hom_nay_vn() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
        client, use_case, _ = _client()

        with _patch_khoa():
            resp = client.post(
                url, json={"tu_ngay": str(den), "den_ngay": str(den - timedelta(days=1))}
            )

        assert resp.status_code == 422
        assert "phai <=" in resp.json()["detail"]
        use_case.execute_all_pending.assert_not_awaited()

    @pytest.mark.parametrize("url", [XEM_TRUOC, CHAY_THAT])
    def test_den_ngay_qua_gan_tra_422_kem_ngay_toi_da(self, url, don_override):
        # CR hom qua chua du 7 ngay KPI sau CR -> danh gia se sai, te hon la
        # khong chay.
        hom_qua = _hom_nay_vn() - timedelta(days=1)
        client, use_case, _ = _client()

        with _patch_khoa():
            resp = client.post(url, json={"tu_ngay": str(hom_qua), "den_ngay": str(hom_qua)})

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert f"chua du {XUAT_PHIEU_AFTER_DAYS} ngay" in detail
        # Phai noi RO ngay toi da, khong bat nguoi dung tu doan.
        assert str(_hom_nay_vn() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)) in detail
        use_case.execute_all_pending.assert_not_awaited()


# === A: XEM TRUOC ===


class TestXemTruoc:
    def test_tra_dung_hinh_dang_va_tong(self, don_override):
        use_case = AsyncMock()
        use_case.xem_truoc.return_value = {
            "tong_phieu_se_xuat": 2,
            "sessions": [
                {
                    "cr_session_id": 2641,
                    "tram_id": "113492",
                    "tram_name": "4G-TEST-HNI",
                    "executed_at": datetime(2026, 8, 1, 2, 0, tzinfo=timezone.utc),
                    "so_cell_se_xuat": 2,
                    "cells": [
                        {
                            "cell_name": "CELL_A",
                            "nguon": "CA_HAI",
                            "do_te": 0.85,
                            "avg_before": 5.0,
                            "avg_after": 4.15,
                        },
                        {
                            "cell_name": "CELL_B",
                            "nguon": "QOE",
                            "do_te": 0.4,
                            "avg_before": 4.2,
                            "avg_after": 3.8,
                        },
                    ],
                    "loi": None,
                }
            ],
        }
        client, _, _ = _client(use_case)
        tu, den = _ngay_hop_le()

        resp = client.post(XEM_TRUOC, json={"tu_ngay": tu, "den_ngay": den})

        assert resp.status_code == 200  # DONG BO, khong phai 202
        body = resp.json()
        assert body["tong_phieu_se_xuat"] == 2
        s = body["sessions"][0]
        assert s["cr_session_id"] == 2641
        assert s["so_cell_se_xuat"] == 2
        assert [c["cell_name"] for c in s["cells"]] == ["CELL_A", "CELL_B"]
        assert s["cells"][0]["nguon"] == "CA_HAI"
        assert s["cells"][0]["avg_after"] == 4.15

    def test_KHONG_ghi_job_run_log(self, don_override):
        use_case = AsyncMock()
        use_case.xem_truoc.return_value = {"tong_phieu_se_xuat": 0, "sessions": []}
        client, _, job_repo = _client(use_case)
        tu, den = _ngay_hop_le()

        client.post(XEM_TRUOC, json={"tu_ngay": tu, "den_ngay": den})

        job_repo.insert.assert_not_awaited()

    def test_KHONG_goi_execute_all_pending(self, don_override):
        # Chan nham lan chet nguoi: xem truoc ma goi ham chay that = POST that.
        use_case = AsyncMock()
        use_case.xem_truoc.return_value = {"tong_phieu_se_xuat": 0, "sessions": []}
        client, _, _ = _client(use_case)
        tu, den = _ngay_hop_le()

        client.post(XEM_TRUOC, json={"tu_ngay": tu, "den_ngay": den})

        use_case.execute_all_pending.assert_not_awaited()
        use_case.xem_truoc.assert_awaited_once()


# === B: CHAY THAT + ADVISORY LOCK ===


class TestChayThat:
    def test_lay_duoc_khoa_thi_202_va_ghi_job_run_log_manual(self, don_override):
        client, use_case, job_repo = _client()
        tu, den = _ngay_hop_le()

        with _patch_khoa(lay_duoc=True):
            resp = client.post(CHAY_THAT, json={"tu_ngay": tu, "den_ngay": den})

        assert resp.status_code == 202
        assert resp.json()["job_run_log_id"] == 555

        # job_type PHAI phan biet duoc voi luot tu dong
        job_repo.insert.assert_awaited_once()
        dong = job_repo.insert.await_args.args[0]
        assert dong["job_type"] == "xuat_phieu_manual"
        assert dong["job_type"] != "xuat_phieu_auto"
        assert dong["trang_thai"] == "RUNNING"

    def test_truyen_dung_khoang_ngay_xuong_use_case(self, don_override):
        client, use_case, _ = _client()
        tu, den = _ngay_hop_le()

        with _patch_khoa(lay_duoc=True):
            client.post(CHAY_THAT, json={"tu_ngay": tu, "den_ngay": den})

        # TestClient chay background task truoc khi tra ve
        use_case.execute_all_pending.assert_awaited_once()
        kw = use_case.execute_all_pending.await_args.kwargs
        assert kw["tu_ngay"] == date.fromisoformat(tu)
        assert kw["den_ngay"] == date.fromisoformat(den)
        assert kw["job_run_log_id"] == 555

    def test_khoa_dang_bi_giu_tra_409(self, don_override):
        client, use_case, job_repo = _client()
        tu, den = _ngay_hop_le()

        with _patch_khoa(lay_duoc=False):
            resp = client.post(CHAY_THAT, json={"tu_ngay": tu, "den_ngay": den})

        assert resp.status_code == 409
        assert "dang chay" in resp.json()["detail"]

    def test_409_tra_TRUOC_khi_vao_background(self, don_override):
        # Day la diem chinh cua yeu cau B: neu kiem khoa trong background thi
        # nguoi bam nhan 202 "da nhan" roi khong co gi xay ra, va se bam lai.
        client, use_case, job_repo = _client()
        tu, den = _ngay_hop_le()

        with _patch_khoa(lay_duoc=False):
            resp = client.post(CHAY_THAT, json={"tu_ngay": tu, "den_ngay": den})

        assert resp.status_code == 409
        # KHONG tao dong job_run_log rac, KHONG chay gi
        job_repo.insert.assert_not_awaited()
        use_case.execute_all_pending.assert_not_awaited()

    def test_background_khong_lay_duoc_khoa_thi_ghi_FAILED(self, don_override):
        # Cua so ho: khoa lay duoc luc tra 202 nhung job tu dong chen vao truoc
        # khi background lay lai. Dong RUNNING KHONG duoc treo vinh vien.
        job_repo = AsyncMock()
        job_repo.insert.return_value = {"id": 777}
        use_case = AsyncMock()

        goi = {"n": 0}

        class _KhoaLanDau:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                goi["n"] += 1
                return goi["n"] == 1  # lan 1 (router) duoc, lan 2 (background) mat

            async def __aexit__(self, *a):
                return False

        client, _, _ = _client(use_case, job_repo)
        tu, den = _ngay_hop_le()

        with patch.object(jobs_router, "giu_khoa", _KhoaLanDau):
            resp = client.post(CHAY_THAT, json={"tu_ngay": tu, "den_ngay": den})

        assert resp.status_code == 202
        use_case.execute_all_pending.assert_not_awaited()
        job_repo.update_result.assert_awaited_once()
        kw = job_repo.update_result.await_args.kwargs
        assert kw["trang_thai"] == "FAILED"
        assert "khoa" in kw["error_message"].lower()


# === CUNG MOT KHOA voi job tu dong ===


def test_dung_chung_khoa_voi_scheduler():
    """Router va scheduler PHAI dung cung 1 hang so khoa.

    Neu 2 ben dung 2 so khac nhau thi advisory lock vo tac dung hoan toan: ca
    hai deu "lay duoc khoa" va cung chay, POST 2 phieu cho 1 cell.
    """
    from infrastructure import advisory_lock, scheduler

    assert jobs_router.KHOA_XUAT_PHIEU is advisory_lock.KHOA_XUAT_PHIEU
    assert scheduler.KHOA_XUAT_PHIEU is advisory_lock.KHOA_XUAT_PHIEU
    # Va CUNG MOT ham lock - khong phai 2 ban copy
    assert jobs_router.giu_khoa is advisory_lock.giu_khoa
    assert scheduler.giu_khoa is advisory_lock.giu_khoa
