"""
Integration test cho CrLogRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: DB_SCHEMA.md Section 4; 22072026 (xac nhan voi user) - bang cr_log da co
san tu B4.4, chi thieu tang repo (cr_logs[] truoc gio LUON RONG).
"""

from adapters.postgres.cr_log_repo import CrLogRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from domain.entities.cr_session import CrSession, CrStatus


async def _new_session_id(db_session, tram_id: str) -> int:
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=tram_id, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
    )
    return created.id


async def test_insert_va_get_by_cr_session_id_dung_field(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrLogRepo(db_session)

    await repo.insert(session_id, 1, "Validate input", "success", "Input hop le", 5)

    rows = await repo.get_by_cr_session_id(session_id)
    assert len(rows) == 1
    assert rows[0]["step"] == 1
    assert rows[0]["step_name"] == "Validate input"
    assert rows[0]["status"] == "success"
    assert rows[0]["message"] == "Input hop le"
    assert rows[0]["pct"] == 5
    assert rows[0]["ma_loi"] is None  # mac dinh, khong truyen
    assert rows[0]["created_at"] is not None


async def test_insert_voi_ma_loi_luu_dung(db_session, test_tram):
    # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - cot
    # MOI ma_loi (migration 3c380956fd44) round-trip dung qua DB that.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrLogRepo(db_session)

    await repo.insert(
        session_id, 3, "Goi CDS API /cell/neighbors", "failed",
        "Chua co du lieu HO", None, ma_loi="KHONG_CO_DU_LIEU_HO",
    )

    rows = await repo.get_by_cr_session_id(session_id)
    assert rows[0]["ma_loi"] == "KHONG_CO_DU_LIEU_HO"


async def test_insert_message_pct_none_hop_le(db_session, test_tram):
    # DB_SCHEMA.md - message/pct nullable (khac step/step_name/status
    # NOT NULL) - phai insert/doc duoc binh thuong voi gia tri None.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrLogRepo(db_session)

    await repo.insert(session_id, 5, "Buoc khong co message/pct", "running", None, None)

    rows = await repo.get_by_cr_session_id(session_id)
    assert rows[0]["message"] is None
    assert rows[0]["pct"] is None


async def test_get_by_cr_session_id_sort_created_at_tang_dan(db_session, test_tram):
    # Muc dich CHINH: nhieu dong (kha nang trung "step" - vd buoc 3 emit 2 lan
    # running roi success) phai tra ve DUNG THU TU THOI GIAN THAT xay ra (buoc
    # dau -> buoc cuoi), KHONG phai sort theo "step".
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrLogRepo(db_session)

    await repo.insert(session_id, 1, "Validate input", "success", "b1", 5)
    await repo.insert(session_id, 2, "Query tram", "success", "b2", 10)
    await repo.insert(session_id, 3, "Goi CDS", "running", "b3-running", 18)
    await repo.insert(session_id, 3, "Goi CDS", "success", "b3-success", 18)  # CUNG step=3, sau ve thoi gian

    rows = await repo.get_by_cr_session_id(session_id)
    messages = [r["message"] for r in rows]
    assert messages == ["b1", "b2", "b3-running", "b3-success"]  # dung thu tu tao (thoi gian), khong phai step


async def test_get_by_cr_session_id_khong_ton_tai_tra_rong(db_session, test_tram):
    repo = CrLogRepo(db_session)
    assert await repo.get_by_cr_session_id(999_999_999) == []


async def test_get_by_cr_session_id_khong_lan_qua_session_khac(db_session, test_tram):
    # 2 session khac nhau CUNG tram - log cua session A KHONG duoc lan sang
    # ket qua cua session B (loc dung cr_session_id, khong phai theo tram).
    session_a = await _new_session_id(db_session, test_tram)
    session_b = await _new_session_id(db_session, test_tram)
    repo = CrLogRepo(db_session)

    await repo.insert(session_a, 1, "Buoc A", "success", "cua session A", 5)
    await repo.insert(session_b, 1, "Buoc B", "success", "cua session B", 5)

    rows_a = await repo.get_by_cr_session_id(session_a)
    assert len(rows_a) == 1
    assert rows_a[0]["message"] == "cua session A"
