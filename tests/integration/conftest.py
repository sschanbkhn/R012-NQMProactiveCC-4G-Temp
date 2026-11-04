"""
Fixtures dung chung cho integration test cua adapters/postgres/ — can DB that.
Tu: ARCHITECTURE.md Section 10 (Testing Strategy)
"""

from sqlalchemy import delete, select, update as sa_update
import pytest_asyncio

from infrastructure.db import AsyncSessionLocal
from models.alert_log import AlertLog as AlertLogModel
from models.audit_log import AuditLog as AuditLogModel
from models.cell_params import CellParams as CellParamsModel
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel
from models.cr_log import CrLog as CrLogModel
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_session import CrSession as CrSessionModel
from models.job_run_log import JobRunLog as JobRunLogModel
from models.qoe_snapshot import QoeSnapshot as QoeSnapshotModel
from models.qos_snapshot import QosSnapshot as QosSnapshotModel
from models.tram import Tram as TramModel

# Prefix rieng de nhan dien + don sach du lieu test — khong dung tram_id trung
# voi du lieu that trong schema system_nsn_nqmproactivecc.
TEST_TRAM_ID = "TEST_B5_990001"

# job_run_log KHONG co FK toi tram/cr_session (1 dong = 1 luot chay job, khong
# thuoc session nao) nen KHONG don duoc qua fixture test_tram nhu cac bang kia -
# phai co fixture rieng, loc theo tien to job_type. Dung tien to nay cho MOI
# job_type trong test de teardown khong bao gio cham vao du lieu job that.
TEST_JOB_TYPE_PREFIX = "TEST_JOB_"


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def test_tram(db_session):
    # cr_session/cell_params co FK -> tram.tram_id nen phai co tram truoc khi test.
    row = TramModel(tram_id=TEST_TRAM_ID, tram_name="TEST STATION B5", trang_thai="active")
    db_session.add(row)
    await db_session.commit()

    yield TEST_TRAM_ID

    # Don sach theo thu tu nguoc FK: cr_affected_cells/cr_log/cr_phieu/cell_params ->
    # cr_session -> tram. cr_affected_cells (22072026, Phuong an B)/cr_log
    # (22072026, persist log tung buoc CR)/cr_phieu (KHOI 2/5 SaveCellClm) deu
    # FK cr_session_id, KHONG co cot tram_id truc tiep nen phai loc qua
    # subquery cr_session.tram_id, khac cell_params/cr_session loc thang duoc.
    # QUAN TRONG: PHAI xoa cac bang nay TRUOC cr_session, neu khong FK
    # violation khi xoa cr_session (bai hoc tu bug that gap khi them
    # cr_affected_cells - xem docs/DEV_LOG.md).
    session_ids = select(CrSessionModel.id).where(CrSessionModel.tram_id == TEST_TRAM_ID)
    await db_session.execute(
        delete(CrAffectedCellsModel).where(CrAffectedCellsModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(delete(CrLogModel).where(CrLogModel.cr_session_id.in_(session_ids)))
    await db_session.execute(delete(CrPhieuModel).where(CrPhieuModel.cr_session_id.in_(session_ids)))
    # qos_snapshot/qoe_snapshot (20082026) - CUNG FK cr_session_id. Thieu 2
    # dong nay thi xoa cr_session ben duoi bi FK violation, teardown chet giua
    # chung -> dong tram con sot lai -> LAN CHAY SAU loi "duplicate key
    # tram_id" ngay o buoc setup (da gap that khi them test snapshot).
    await db_session.execute(
        delete(QosSnapshotModel).where(QosSnapshotModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(
        delete(QoeSnapshotModel).where(QoeSnapshotModel.cr_session_id.in_(session_ids))
    )
    await db_session.execute(delete(CellParamsModel).where(CellParamsModel.tram_id == TEST_TRAM_ID))
    # alert_log/audit_log/rollback_of_id (20082026) - 3 FK con lai tro toi
    # cr_session. Do bang pg_constraint tren DB THAT: co 9 FK tro toi
    # cr_session, TAT CA ON DELETE NO ACTION (Postgres KHONG tu don).
    #
    # DUNG LOAI BUG DA GAP 19/08: thieu 1 bang -> xoa cr_session ben duoi bi FK
    # violation -> teardown chet GIUA CHUNG -> dong tram sot lai -> LAN CHAY
    # SAU loi "duplicate key tram_id" ngay o buoc setup.
    #
    # audit_log/rollback_of_id SET NULL chu KHONG xoa: audit_log la vet kiem
    # toan (phai song lau hon doi tuong bi thao tac, va cot NULLABLE nen lam
    # duoc); rollback_of_id nam tren cr_session KHAC - xoa dong do la xoa 1
    # session khong thuoc dien don.
    await db_session.execute(delete(AlertLogModel).where(AlertLogModel.cr_session_id.in_(session_ids)))
    await db_session.execute(
        sa_update(AuditLogModel)
        .where(AuditLogModel.cr_session_id.in_(session_ids))
        .values(cr_session_id=None)
    )
    await db_session.execute(
        sa_update(CrSessionModel)
        .where(CrSessionModel.rollback_of_id.in_(session_ids))
        .values(rollback_of_id=None)
    )
    await db_session.execute(delete(CrSessionModel).where(CrSessionModel.tram_id == TEST_TRAM_ID))
    await db_session.execute(delete(TramModel).where(TramModel.tram_id == TEST_TRAM_ID))
    await db_session.commit()


@pytest_asyncio.fixture
async def clean_job_run_log(db_session):
    # Don TRUOC va SAU: neu 1 lan chay truoc bi ngat giua chung (Ctrl-C/crash)
    # thi dong cu con sot lai se lam test dem so luong sai - don dau vao dam bao
    # moi lan chay deu bat dau tu trang thai sach. Ap dung dung bai hoc leftover
    # tu cr_affected_cells (xem docs/DEV_LOG.md): them buoc don NGAY khi tao
    # bang, KHONG doi den luc phat hien rac.
    stmt = delete(JobRunLogModel).where(JobRunLogModel.job_type.like(f"{TEST_JOB_TYPE_PREFIX}%"))
    await db_session.execute(stmt)
    await db_session.commit()

    yield TEST_JOB_TYPE_PREFIX

    await db_session.execute(stmt)
    await db_session.commit()
