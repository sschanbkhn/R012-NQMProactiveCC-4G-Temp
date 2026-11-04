"""
Integration test cho CrSessionRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: ARCHITECTURE.md Section 10; TASK_LIST.md B5.2
"""

from datetime import datetime, timezone

import pytest

from adapters.postgres.cr_session_repo import CrSessionRepo
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.outbound.repo_ports import SessionFilter
from models.cr_session import CrSession as CrSessionModel


def _new_session(tram_id: str, status: CrStatus = CrStatus.RUNNING) -> CrSession:
    # id=0 la placeholder - CrSessionRepo.create() bo qua field nay, DB tu sinh
    # SERIAL PK that (xem chu y trong adapters/postgres/cr_session_repo.py)
    return CrSession(id=0, tram_id=tram_id, action="shutdown", status=status, plan_name=None)


async def test_create_tra_ve_id_that_tu_db(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    created = await repo.create(_new_session(test_tram))
    assert isinstance(created.id, int) and created.id > 0
    assert created.status == CrStatus.RUNNING
    assert created.tram_id == test_tram


async def test_get_by_id_tra_ve_dung_session(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    created = await repo.create(_new_session(test_tram))

    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.status == CrStatus.RUNNING


async def test_get_by_id_khong_ton_tai_tra_ve_none(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    assert await repo.get_by_id(999_999_999) is None


async def test_update_ghi_de_status_va_plan_name(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    created = await repo.create(_new_session(test_tram))

    created.status = CrStatus.DONE
    created.plan_name = "R012_NQMProactiveCC_test_plan"
    updated = await repo.update(created)

    assert updated.status == CrStatus.DONE
    assert updated.plan_name == "R012_NQMProactiveCC_test_plan"

    refetched = await repo.get_by_id(created.id)
    assert refetched.status == CrStatus.DONE
    assert refetched.plan_name == "R012_NQMProactiveCC_test_plan"


async def test_update_ghi_de_ma_loi_va_status_khong_chay(db_session, test_tram):
    # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - xac
    # nhan cot MOI ma_loi (migration 3c380956fd44) + gia tri enum MOI
    # CrStatus.KHONG_CHAY round-trip dung qua DB that (khong chi mock).
    repo = CrSessionRepo(db_session)
    created = await repo.create(_new_session(test_tram))

    created.status = CrStatus.KHONG_CHAY
    created.ma_loi = "KHONG_CO_DU_LIEU_HO"
    updated = await repo.update(created)

    assert updated.status == CrStatus.KHONG_CHAY
    assert updated.ma_loi == "KHONG_CO_DU_LIEU_HO"

    refetched = await repo.get_by_id(created.id)
    assert refetched.status == CrStatus.KHONG_CHAY
    assert refetched.ma_loi == "KHONG_CO_DU_LIEU_HO"


async def test_update_id_khong_ton_tai_raise_valueerror(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    bogus = _new_session(test_tram)
    bogus.id = 999_999_999
    with pytest.raises(ValueError):
        await repo.update(bogus)


async def test_get_by_tram_id_tra_ve_tat_ca_session_cua_tram(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    first = await repo.create(_new_session(test_tram, CrStatus.DONE))
    second = await repo.create(_new_session(test_tram, CrStatus.RUNNING))

    sessions = await repo.get_by_tram_id(test_tram)
    ids = {s.id for s in sessions}
    assert {first.id, second.id} <= ids


async def test_list_bo_qua_filter_rong_va_chua_session_vua_tao(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    created = await repo.create(_new_session(test_tram))

    page = await repo.list(SessionFilter())
    assert page.total == len(page.items)
    assert created.id in {s.id for s in page.items}


# --- sort_by/order (22072026) cho GET /sessions ---
async def test_list_sort_by_status_asc_dung_thu_tu(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    # Thu tu tao (=thu tu id/created_at) CO CHU Y khac thu tu alphabet cua
    # status - de phan biet ro sort_by=status THAT SU sort lai, khong phai
    # trung hop giong thu tu tao/default.
    await repo.create(_new_session(test_tram, CrStatus.PENDING))
    await repo.create(_new_session(test_tram, CrStatus.DONE))
    await repo.create(_new_session(test_tram, CrStatus.RUNNING))
    await repo.create(_new_session(test_tram, CrStatus.FAILED))

    page = await repo.list(SessionFilter(q=test_tram, sort_by="status", order="asc", page=1, size=10))
    statuses = [s.status.value for s in page.items]
    assert statuses == ["DONE", "FAILED", "PENDING", "RUNNING"]  # alphabet tang dan


async def test_list_sort_by_status_desc_dung_thu_tu(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    await repo.create(_new_session(test_tram, CrStatus.PENDING))
    await repo.create(_new_session(test_tram, CrStatus.DONE))
    await repo.create(_new_session(test_tram, CrStatus.RUNNING))
    await repo.create(_new_session(test_tram, CrStatus.FAILED))

    page = await repo.list(SessionFilter(q=test_tram, sort_by="status", order="desc", page=1, size=10))
    statuses = [s.status.value for s in page.items]
    assert statuses == ["RUNNING", "PENDING", "FAILED", "DONE"]  # alphabet giam dan


async def test_list_khong_truyen_sort_by_giu_nguyen_created_at_desc(db_session, test_tram):
    # KHONG regression - hanh vi mac dinh TRUOC khi co task nay la
    # created_at DESC (moi tao truoc), phai giu nguyen y het khi sort_by=None.
    repo = CrSessionRepo(db_session)
    first = await repo.create(_new_session(test_tram, CrStatus.PENDING))
    second = await repo.create(_new_session(test_tram, CrStatus.DONE))
    third = await repo.create(_new_session(test_tram, CrStatus.RUNNING))

    page = await repo.list(SessionFilter(q=test_tram, page=1, size=10))  # khong truyen sort_by
    ids = [s.id for s in page.items]
    assert ids == [third.id, second.id, first.id]  # created_at desc = tao sau cung dung truoc


async def test_list_sort_ap_truoc_phan_trang(db_session, test_tram):
    # Muc dich CHINH cua task: page=1,size=2 sort_by=status asc phai tra
    # dung 2 ban ghi DAU cua TOAN BO 4 ban ghi da sort ("DONE","FAILED") -
    # KHONG phai 2 ban ghi dau theo thu tu tao (PENDING,DONE) roi moi sort
    # trong pham vi 2 ban ghi do (se sai, "sort trong trang").
    repo = CrSessionRepo(db_session)
    await repo.create(_new_session(test_tram, CrStatus.PENDING))  # tao 1
    await repo.create(_new_session(test_tram, CrStatus.DONE))  # tao 2
    await repo.create(_new_session(test_tram, CrStatus.RUNNING))  # tao 3
    await repo.create(_new_session(test_tram, CrStatus.FAILED))  # tao 4

    page1 = await repo.list(SessionFilter(q=test_tram, sort_by="status", order="asc", page=1, size=2))
    statuses_page1 = [s.status.value for s in page1.items]
    assert statuses_page1 == ["DONE", "FAILED"]
    assert page1.total == 4  # total la TOAN BO ban ghi khop filter, khong phai 2

    page2 = await repo.list(SessionFilter(q=test_tram, sort_by="status", order="asc", page=2, size=2))
    statuses_page2 = [s.status.value for s in page2.items]
    assert statuses_page2 == ["PENDING", "RUNNING"]


# === 14/08: ghi_ket_qua_xuat_phieu (2 cot theo doi tien trinh) ===


async def test_ghi_ket_qua_xuat_phieu_ghi_dung_2_cot(db_session, test_tram):
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=test_tram, action="shutdown", status=CrStatus.DONE, plan_name="PLAN_XP")
    )
    moc = datetime(2026, 8, 9, 1, 2, 3, tzinfo=timezone.utc)

    await repo.ghi_ket_qua_xuat_phieu(created.id, xuat_phieu_at=moc, xuat_phieu_ket_qua="DA_XUAT")

    row = await db_session.get(CrSessionModel, created.id)
    await db_session.refresh(row)
    assert row.xuat_phieu_ket_qua == "DA_XUAT"
    # TIMESTAMPTZ - doc len PHAI con tzinfo, neu mat thi cot dang la TIMESTAMP thuong
    assert row.xuat_phieu_at is not None
    assert row.xuat_phieu_at.tzinfo is not None
    assert row.xuat_phieu_at == moc


async def test_ghi_ket_qua_xuat_phieu_KHONG_dung_toi_cot_khac(db_session, test_tram):
    # Job xuat phieu chi ghi chu ben le - KHONG duoc dong vao du lieu NGHIEP VU
    # cua CR (status/plan_name/executed_at/qoe_result...).
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=test_tram, action="shutdown", status=CrStatus.DONE, plan_name="PLAN_GIU")
    )
    row = await db_session.get(CrSessionModel, created.id)
    truoc = (row.status, row.plan_name, row.executed_at, row.evaluated_at, row.qoe_result, row.qos_result)
    updated_at_truoc = row.updated_at

    await repo.ghi_ket_qua_xuat_phieu(
        created.id, xuat_phieu_at=datetime.now(timezone.utc), xuat_phieu_ket_qua="LOI"
    )

    row = await db_session.get(CrSessionModel, created.id)
    await db_session.refresh(row)
    assert (
        row.status, row.plan_name, row.executed_at, row.evaluated_at, row.qoe_result, row.qos_result
    ) == truoc

    # updated_at NHAY - CO Y kiem tra dieu nay de no la HANH VI DA BIET, khong
    # phai bat ngo: models/cr_session.py dat onupdate=now(utc), ma onupdate cua
    # SQLAlchemy ban theo MOI lenh UPDATE tren dong, khong phan biet cot nao doi.
    # Test khang dinh dung su that thay vi khang dinh dieu mong muon (ban dau
    # test nay assert updated_at KHONG doi va da FAIL - xem comment trong
    # CrSessionRepo.ghi_ket_qua_xuat_phieu()).
    assert row.updated_at > updated_at_truoc


async def test_ghi_ket_qua_xuat_phieu_id_khong_ton_tai_KHONG_raise(db_session):
    # Ban ghi phu tro - id sai khong duoc lam ca luot quet crash (giong
    # CrPhieuRepo.update_result/danh_dau_khong_xuat).
    repo = CrSessionRepo(db_session)
    await repo.ghi_ket_qua_xuat_phieu(
        999999999, xuat_phieu_at=datetime.now(timezone.utc), xuat_phieu_ket_qua="DA_XUAT"
    )


async def test_gia_tri_30_ky_tu_van_vua_cot(db_session, test_tram):
    # VARCHAR(30) - bai hoc tu cr_phieu.trang_thai VARCHAR(20) phai them 1
    # migration rieng chi vi gia tri 24 ky tu khong vua.
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=test_tram, action="shutdown", status=CrStatus.DONE, plan_name=None)
    )
    dai_30 = "X" * 30

    await repo.ghi_ket_qua_xuat_phieu(
        created.id, xuat_phieu_at=datetime.now(timezone.utc), xuat_phieu_ket_qua=dai_30
    )

    row = await db_session.get(CrSessionModel, created.id)
    await db_session.refresh(row)
    assert row.xuat_phieu_ket_qua == dai_30
