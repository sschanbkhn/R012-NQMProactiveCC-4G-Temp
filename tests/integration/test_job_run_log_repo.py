"""
Integration test cho JobRunLogRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: yeu cau truc tiep user (JOB TU DONG buoc 1/4) - lich su moi lan job chay.

MOI test dung fixture clean_job_run_log (conftest.py) - job_type PHAI bat dau
bang TEST_JOB_ de teardown loc dung, khong cham du lieu job that.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from adapters.postgres.job_run_log_repo import JobRunLogRepo
from models.job_run_log import JobRunLog as JobRunLogModel

JOB_XUAT_PHIEU = "TEST_JOB_xuat_phieu_auto"
JOB_KHAC = "TEST_JOB_evaluate_cr"


def _mau_log(job_type: str = JOB_XUAT_PHIEU) -> dict:
    # V2 (12/08): da BO key dry_run - job khong con che do chay thu.
    return {"job_type": job_type, "trang_thai": "RUNNING"}


async def test_insert_tao_dong_running_kem_id_started_at(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)

    result = await repo.insert(_mau_log())

    assert result["id"] is not None
    assert result["job_type"] == JOB_XUAT_PHIEU
    assert result["trang_thai"] == "RUNNING"
    assert "dry_run" not in result  # V2 (12/08) - da bo cot
    # started_at do adapter tu set (khong nhan tu caller) va PHAI tz-aware -
    # cot la TIMESTAMPTZ (C1.4-fix9), doc len mat tzinfo la dau hieu sai kieu cot
    assert result["started_at"] is not None
    assert result["started_at"].tzinfo is not None
    # chua xong -> finished_at NULL, 4 cot so ve 0 (server_default), khong None
    assert result["finished_at"] is None
    assert result["so_session_quet"] == 0
    assert result["so_phieu_thanh_cong"] == 0
    assert result["so_phieu_that_bai"] == 0
    assert result["so_cell_vuot_gioi_han"] == 0
    assert result["error_message"] is None
    assert result["chi_tiet"] is None


async def test_update_result_done_cap_nhat_du_cot(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)
    inserted = await repo.insert(_mau_log())
    finished = datetime.now(timezone.utc)

    await repo.update_result(
        inserted["id"],
        trang_thai="DONE",
        finished_at=finished,
        so_session_quet=5,
        so_phieu_thanh_cong=12,
        so_phieu_that_bai=2,
        so_cell_vuot_gioi_han=1,
        chi_tiet={"sessions": [553, 554], "cells": ["4G-SSN087M43-HNI"]},
    )

    row = (await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10))[0]
    assert row["trang_thai"] == "DONE"
    assert row["finished_at"] is not None
    assert row["finished_at"].tzinfo is not None
    assert row["so_session_quet"] == 5
    assert row["so_phieu_thanh_cong"] == 12
    assert row["so_phieu_that_bai"] == 2
    assert row["so_cell_vuot_gioi_han"] == 1
    assert row["error_message"] is None
    # V3a (12/08): chi_tiet KHONG con nam trong ket qua list - doi sang
    # get_by_id(). Y DINH cua assert nay khong doi (JSONB round-trip: doc len
    # phai la dict/list Python, khong phai chuoi JSON), chi doi duong doc.
    chi_tiet = (await repo.get_by_id(inserted["id"]))["chi_tiet"]
    assert chi_tiet["sessions"] == [553, 554]


async def test_update_result_failed_luu_error_message(db_session, clean_job_run_log):
    # Nhanh job chet - 4 cot so KHONG truyen (mac dinh 0), chi can trang_thai +
    # error_message. Dong RUNNING khong duoc ket vinh vien (bai hoc C1.4-fix2).
    repo = JobRunLogRepo(db_session)
    inserted = await repo.insert(_mau_log())

    await repo.update_result(
        inserted["id"],
        trang_thai="FAILED",
        finished_at=datetime.now(timezone.utc),
        error_message="CTS API timeout sau 3 lan retry",
    )

    row = (await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10))[0]
    assert row["trang_thai"] == "FAILED"
    assert row["error_message"] == "CTS API timeout sau 3 lan retry"
    assert row["so_session_quet"] == 0
    assert row["finished_at"] is not None


async def test_update_result_id_khong_ton_tai_khong_crash(db_session, clean_job_run_log):
    # Ban ghi phu tro - khong duoc lam job that crash chi vi id sai.
    repo = JobRunLogRepo(db_session)

    await repo.update_result(
        999_999_999, trang_thai="DONE", finished_at=datetime.now(timezone.utc)
    )


async def test_list_loc_theo_job_type(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)
    await repo.insert(_mau_log(JOB_XUAT_PHIEU))
    await repo.insert(_mau_log(JOB_XUAT_PHIEU))
    await repo.insert(_mau_log(JOB_KHAC))

    rows = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10)

    assert len(rows) == 2
    assert {r["job_type"] for r in rows} == {JOB_XUAT_PHIEU}
    assert await repo.count_job_runs(JOB_XUAT_PHIEU) == 2
    assert await repo.count_job_runs(JOB_KHAC) == 1


async def test_list_khong_loc_tra_ca_loai_job(db_session, clean_job_run_log):
    # job_type=None -> tat ca. Assert TUONG DOI (>=) vi bang co the co du lieu
    # job that cua he thong, khong duoc assert con so tuyet doi.
    repo = JobRunLogRepo(db_session)
    await repo.insert(_mau_log(JOB_XUAT_PHIEU))
    await repo.insert(_mau_log(JOB_KHAC))

    total_tat_ca = await repo.count_job_runs(None)

    assert total_tat_ca >= 2
    assert total_tat_ca > await repo.count_job_runs(JOB_XUAT_PHIEU)


async def test_list_phan_trang_khong_trung_khong_sot(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)
    ids = [(await repo.insert(_mau_log()))["id"] for _ in range(5)]

    trang_1 = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=2, sort_by="id", order="asc")
    trang_2 = await repo.list_job_runs(JOB_XUAT_PHIEU, page=2, size=2, sort_by="id", order="asc")
    trang_3 = await repo.list_job_runs(JOB_XUAT_PHIEU, page=3, size=2, sort_by="id", order="asc")

    assert [r["id"] for r in trang_1] == ids[:2]
    assert [r["id"] for r in trang_2] == ids[2:4]
    assert [r["id"] for r in trang_3] == ids[4:]  # trang cuoi le
    assert await repo.count_job_runs(JOB_XUAT_PHIEU) == 5


async def test_list_sort_mac_dinh_started_at_desc(db_session, clean_job_run_log):
    # Luot MOI NHAT truoc - dung index idx_job_run_log_started (DESC).
    repo = JobRunLogRepo(db_session)
    await repo.insert(_mau_log())
    await repo.insert(_mau_log())

    rows = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10)

    assert rows[0]["started_at"] >= rows[-1]["started_at"]
    # so bang id de chac chan (2 dong co the trung mili-giay tren may nhanh)
    assert rows[0]["id"] > rows[-1]["id"]


async def test_list_sort_by_ngoai_whitelist_ve_mac_dinh_khong_crash(db_session, clean_job_run_log):
    # An toan lop 2: router (buoc 4) se chan bang Literal, nhung neu bi goi truc
    # tiep tu script/use case voi ten cot bay ba thi repo PHAI ve mac dinh,
    # KHONG duoc crash hay ghep chuoi do vao SQL.
    repo = JobRunLogRepo(db_session)
    await repo.insert(_mau_log())

    rows = await repo.list_job_runs(
        JOB_XUAT_PHIEU, page=1, size=10, sort_by="chi_tiet; DROP TABLE job_run_log"
    )

    assert len(rows) == 1


async def _doi_started_at(db_session, id: int, moc: datetime) -> None:
    # insert() CO Y tu set started_at=now() (khong nhan tu caller) nen muon dung
    # 1 moc thoi gian CU THE de test loc theo ngay thi phai sua thang tren DB.
    # Chi dung trong test - KHONG mo them tham so o repo that chi de phuc vu test.
    await db_session.execute(
        update(JobRunLogModel).where(JobRunLogModel.id == id).values(started_at=moc)
    )
    await db_session.commit()


async def test_list_loc_theo_trang_thai(db_session, clean_job_run_log):
    # V3a - man hinh lich su can loc rieng luot FAILED (di tim nguyen nhan) va
    # luot RUNNING (job treo).
    repo = JobRunLogRepo(db_session)
    dang_chay = await repo.insert(_mau_log())
    da_xong = await repo.insert(_mau_log())
    await repo.update_result(da_xong["id"], trang_thai="DONE", finished_at=datetime.now(timezone.utc))

    chi_running = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10, trang_thai="RUNNING")
    chi_done = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10, trang_thai="DONE")

    assert [r["id"] for r in chi_running] == [dang_chay["id"]]
    assert [r["id"] for r in chi_done] == [da_xong["id"]]
    # count PHAI dung CHUNG dieu kien loc voi list - neu lech, FE phan trang sai
    assert await repo.count_job_runs(JOB_XUAT_PHIEU, trang_thai="RUNNING") == 1
    assert await repo.count_job_runs(JOB_XUAT_PHIEU, trang_thai="DONE") == 1
    assert await repo.count_job_runs(JOB_XUAT_PHIEU) == 2


async def test_list_loc_theo_khoang_ngay(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)
    cu = await repo.insert(_mau_log())
    moi = await repo.insert(_mau_log())
    await _doi_started_at(db_session, cu["id"], datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc))
    await _doi_started_at(db_session, moi["id"], datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc))

    trong_khoang = await repo.list_job_runs(
        JOB_XUAT_PHIEU,
        page=1,
        size=10,
        tu_ngay=datetime(2026, 8, 15, tzinfo=timezone.utc),
        den_ngay=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )

    assert [r["id"] for r in trong_khoang] == [moi["id"]]
    assert (
        await repo.count_job_runs(
            JOB_XUAT_PHIEU,
            tu_ngay=datetime(2026, 8, 15, tzinfo=timezone.utc),
            den_ngay=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        == 1
    )


async def test_list_den_ngay_la_moc_loai_tru(db_session, clean_job_run_log):
    # Nua khoang [tu, den) - dong dung DUNG moc den_ngay bi LOAI. Router cong
    # san 1 ngay truoc khi goi, nho do ngay cuoi van tron ven; test o day khoa
    # dung hop dong do de router va repo khong hieu khac nhau.
    repo = JobRunLogRepo(db_session)
    dong = await repo.insert(_mau_log())
    moc = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    await _doi_started_at(db_session, dong["id"], moc)

    assert await repo.count_job_runs(JOB_XUAT_PHIEU, tu_ngay=moc) == 1
    assert await repo.count_job_runs(JOB_XUAT_PHIEU, den_ngay=moc) == 0


async def test_list_khong_tra_chi_tiet(db_session, clean_job_run_log):
    # V3a - chi_tiet bi bo HAN khoi cau SELECT (khong phai loc sau khi doc).
    repo = JobRunLogRepo(db_session)
    inserted = await repo.insert(_mau_log())
    await repo.update_result(
        inserted["id"],
        trang_thai="DONE",
        finished_at=datetime.now(timezone.utc),
        chi_tiet={"sessions": [{"cr_session_id": 553, "cell_da_xu_ly": ["4G-A", "4G-B"]}]},
    )

    row = (await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10))[0]

    assert "chi_tiet" not in row
    # 10 cot con lai VAN phai co du - bo chi_tiet khong duoc lam rung cot khac
    assert row["so_session_quet"] == 0
    assert row["error_message"] is None
    assert row["trang_thai"] == "DONE"


async def test_get_by_id_tra_day_du_kem_chi_tiet(db_session, clean_job_run_log):
    repo = JobRunLogRepo(db_session)
    inserted = await repo.insert(_mau_log())
    await repo.update_result(
        inserted["id"],
        trang_thai="DONE",
        finished_at=datetime.now(timezone.utc),
        so_session_quet=3,
        chi_tiet={"sessions": [{"cr_session_id": 553}]},
    )

    row = await repo.get_by_id(inserted["id"])

    assert row["id"] == inserted["id"]
    assert row["so_session_quet"] == 3
    assert row["chi_tiet"]["sessions"][0]["cr_session_id"] == 553


async def test_get_by_id_khong_ton_tai_tra_none(db_session, clean_job_run_log):
    # Tra None (KHONG raise) - repo khong biet gi ve HTTP, router moi doi ra 404.
    repo = JobRunLogRepo(db_session)

    assert await repo.get_by_id(999_999_999) is None


async def test_list_sort_finished_at_asc(db_session, clean_job_run_log):
    # finished_at nam trong whitelist - sort duoc theo cot nay (dung cho man
    # hinh loc job da xong).
    repo = JobRunLogRepo(db_session)
    som = await repo.insert(_mau_log())
    muon = await repo.insert(_mau_log())
    base = datetime.now(timezone.utc)
    await repo.update_result(som["id"], trang_thai="DONE", finished_at=base)
    await repo.update_result(muon["id"], trang_thai="DONE", finished_at=base + timedelta(hours=1))

    rows = await repo.list_job_runs(JOB_XUAT_PHIEU, page=1, size=10, sort_by="finished_at", order="asc")

    assert [r["id"] for r in rows] == [som["id"], muon["id"]]
