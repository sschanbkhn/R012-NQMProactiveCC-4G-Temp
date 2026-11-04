"""
Unit test cho infrastructure/scheduler.py (JOB TU DONG buoc 3/4).

MOCK toan bo I/O: asyncpg.connect (patch trong infrastructure/advisory_lock.py -
noi doan lock da duoc tach ra 20082026), AsyncSessionLocal,
JobRunLogRepo, XuatPhieuUseCase. KHONG ket noi DB that, KHONG POST that,
KHONG cho APScheduler chay job that (chi kiem tra viec DANG KY job).
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure import advisory_lock as khoa_mod
from infrastructure import scheduler as sched


@pytest.fixture
def mock_conn():
    """Connection asyncpg gia - dung de kiem tra lock/unlock goi dung."""
    conn = AsyncMock()
    conn.fetchval.return_value = True  # mac dinh: lay duoc khoa
    return conn


def _patch_moi_thu(mock_conn, use_case=None, job_run_id: int = 1):
    """Gom cac patch dung chung. Tra ve (contextmanagers, use_case_mock)."""
    use_case = use_case or AsyncMock()
    use_case.execute_all_pending.return_value = {
        "so_session_quet": 0,
        "so_phieu_thanh_cong": 0,
        "so_phieu_that_bai": 0,
        "so_cell_vuot_gioi_han": 0,
        "chi_tiet": {"sessions": []},
    }

    job_repo = AsyncMock()
    job_repo.insert.return_value = {"id": job_run_id}

    # AsyncSessionLocal() duoc dung dang "async with" -> can MagicMock co
    # __aenter__/__aexit__, khong phai AsyncMock thuong.
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    patches = [
        # Patch asyncpg TRONG advisory_lock (20082026): doan lock da tach ra
        # module dung chung, scheduler khong con import asyncpg. Patch o day
        # co loi hon: test van di XUYEN QUA code lock THAT (giu_khoa) chu
        # khong gia lap lai no.
        patch.object(khoa_mod.asyncpg, "connect", AsyncMock(return_value=mock_conn)),
        patch.object(sched, "AsyncSessionLocal", MagicMock(return_value=session_ctx)),
        patch.object(sched, "JobRunLogRepo", MagicMock(return_value=job_repo)),
        patch.object(sched, "_tao_use_case", MagicMock(return_value=use_case)),
    ]
    return patches, use_case, job_repo


async def _chay_job(mock_conn, use_case=None):
    patches, use_case, job_repo = _patch_moi_thu(mock_conn, use_case)
    for p in patches:
        p.start()
    try:
        await sched.chay_job_xuat_phieu()
    finally:
        for p in patches:
            p.stop()
    return use_case, job_repo


# === SCHEDULER_ENABLED ===


def test_scheduler_enabled_false_khong_dang_ky_job():
    # Tat hoan toan = KHONG dang ky job nao (an toan hon dang ky roi kiem tra
    # co ben trong job).
    with patch.object(sched, "SCHEDULER_ENABLED", False):
        result = sched.khoi_tao_scheduler()

    assert result is None
    assert sched._scheduler is None


def test_scheduler_enabled_true_dang_ky_dung_1_job_dung_cau_hinh():
    # KHONG cho scheduler chay that: patch start() thanh no-op.
    with patch.object(sched, "SCHEDULER_ENABLED", True), patch.object(
        sched.AsyncIOScheduler, "start", MagicMock()
    ):
        scheduler = sched.khoi_tao_scheduler()

    try:
        assert scheduler is not None
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == sched._JOB_ID
        # 3 tham so chong chay trung/tre gio - dac ta BUOC 2
        assert job.misfire_grace_time == 1800
        assert job.coalesce is True
        assert job.max_instances == 1
        # timezone PHAI la gio VN (+7), neu khong hour=8 se thanh 8h UTC = 15h VN.
        #
        # KHONG assert theo TEN vung: tzdata hien dai da bien "Asia/Ho_Chi_Minh"
        # thanh LINK toi "Asia/Bangkok" (2 vung giong het nhau ke tu 1970 - deu
        # +7, khong DST) nen job.trigger.timezone doc len la "Asia/Bangkok" du
        # ta khai bao "Asia/Ho_Chi_Minh". So sanh ten se fail oan va con phu
        # thuoc phien ban tzdata cai tren tung may. Cai THAT SU quan trong la
        # OFFSET, nen assert thang vao do.
        offset = datetime(2026, 8, 12, 8, 0, tzinfo=job.trigger.timezone).utcoffset()
        assert offset == timedelta(hours=7)
        assert f"hour='{sched.SCHEDULER_HOUR}'" in str(job.trigger)
    finally:
        sched._scheduler = None


# === ADVISORY LOCK ===


async def test_khong_lay_duoc_khoa_thi_thoat_em_khong_goi_use_case(mock_conn):
    # Worker khac dang chay -> bo qua luot, KHONG raise, KHONG chay use case.
    mock_conn.fetchval.return_value = False

    use_case, job_repo = await _chay_job(mock_conn)

    use_case.execute_all_pending.assert_not_called()
    job_repo.insert.assert_not_called()  # khong tao dong job_run_log rac
    # Chi goi try_lock, KHONG goi unlock (chua tung giu khoa - unlock se tra
    # false va ghi warning vo ich trong log Postgres)
    assert mock_conn.fetchval.await_count == 1
    assert "pg_try_advisory_lock" in mock_conn.fetchval.await_args_list[0].args[0]
    mock_conn.close.assert_awaited_once()  # van dong connection


async def test_lay_duoc_khoa_thi_insert_running_va_goi_use_case(mock_conn):
    use_case, job_repo = await _chay_job(mock_conn)

    # Dong RUNNING duoc ghi TRUOC khi chay viec that
    job_repo.insert.assert_awaited_once()
    log_moi = job_repo.insert.await_args.args[0]
    assert log_moi["job_type"] == "xuat_phieu_auto"
    assert log_moi["trang_thai"] == "RUNNING"

    use_case.execute_all_pending.assert_awaited_once()
    assert use_case.execute_all_pending.await_args.kwargs["job_run_log_id"] == 1

    # Lock roi unlock
    goi = [c.args[0] for c in mock_conn.fetchval.await_args_list]
    assert "pg_try_advisory_lock" in goi[0]
    assert "pg_advisory_unlock" in goi[1]
    mock_conn.close.assert_awaited_once()


async def test_loi_giua_chung_van_unlock_va_dong_connection(mock_conn):
    # finally PHAI nha khoa - neu khong, job se tu khoa vinh vien tu ngay mai.
    use_case = AsyncMock()
    use_case.execute_all_pending.side_effect = RuntimeError("CTS chet")

    await _chay_job(mock_conn, use_case=use_case)

    goi = [c.args[0] for c in mock_conn.fetchval.await_args_list]
    assert "pg_advisory_unlock" in goi[-1]
    mock_conn.close.assert_awaited_once()


async def test_loi_giua_chung_khong_raise_ra_ngoai(mock_conn):
    # Job chay nen - de loi thoat ra se lam APScheduler tu tat job sau vai lan
    # loi lien tiep. Ham PHAI nuot loi (da log).
    use_case = AsyncMock()
    use_case.execute_all_pending.side_effect = RuntimeError("DB chet")

    await _chay_job(mock_conn, use_case=use_case)  # khong pytest.raises -> khong duoc nem


# === V2 (12/08): CHI CON 1 CO - da bo XUAT_PHIEU_AUTO_ENABLED ===


async def test_v2_khong_con_co_XUAT_PHIEU_AUTO_ENABLED():
    # Bo sot 1 tham chieu se lam scheduler doc bien khong ton tai -> luot chay
    # chet im lang. Kiem tra o CA module scheduler.
    assert not hasattr(sched, "XUAT_PHIEU_AUTO_ENABLED")


async def test_v2_khong_truyen_dry_run_xuong_use_case_va_job_run_log(mock_conn):
    use_case, job_repo = await _chay_job(mock_conn)

    assert "dry_run" not in use_case.execute_all_pending.await_args.kwargs
    assert "dry_run" not in job_repo.insert.await_args.args[0]
    # Dong RUNNING van phai duoc ghi TRUOC khi chay (bai hoc session #197)
    assert job_repo.insert.await_args.args[0]["trang_thai"] == "RUNNING"


def test_co_chi_bat_khi_dung_chu_true():
    # Moi gia tri khac "true" deu la TAT - lien quan WRITE API that.
    for gia_tri, mong_doi in [
        ("true", True), ("TRUE", True), ("  true  ", True),
        ("false", False), ("1", False), ("yes", False), ("", False),
    ]:
        with patch.dict("os.environ", {"CO_TEST": gia_tri}):
            assert sched._co_bat("CO_TEST") is mong_doi, f"gia tri {gia_tri!r}"
