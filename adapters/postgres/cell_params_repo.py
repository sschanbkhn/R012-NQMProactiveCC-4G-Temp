"""
CellParamsRepo — implement ICellParamsRepo (upsert/get_by_tram_id/snapshot_before_cr).
Tu: ARCHITECTURE.md Section 5.3; TASK_LIST.md B5.3
"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cell_param import CellParam
from domain.ports.outbound.repo_ports import ICellParamsRepo
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel
from models.cell_params import CellParams as CellParamsModel
from models.cr_session import CrSession as CrSessionModel


def _to_domain(row: CellParamsModel) -> CellParam:
    return CellParam(
        tram_id=row.tram_id,
        cell_name=row.cell_name,
        huong_id=row.huong_id,
        priority=row.priority,
        action_type=row.action_type,
        rsboost_current=RsboostLevel(float(row.rsboost_current)) if row.rsboost_current is not None else None,
        rsboost_before_cr=RsboostLevel(float(row.rsboost_before_cr)) if row.rsboost_before_cr is not None else None,
        rsboost_new=RsboostLevel(float(row.rsboost_new)) if row.rsboost_new is not None else None,
        qrxlevmin_current=Qrxlevmin(int(row.qrxlevmin_current)) if row.qrxlevmin_current is not None else None,
        qrxlevmin_before_cr=Qrxlevmin(int(row.qrxlevmin_before_cr)) if row.qrxlevmin_before_cr is not None else None,
        qrxlevmin_new=Qrxlevmin(int(row.qrxlevmin_new)) if row.qrxlevmin_new is not None else None,
        cr_session_id=row.cr_session_id,
    )


class CellParamsRepo(ICellParamsRepo):
    # upsert() duoc goi o 2 thoi diem khac nhau voi tap field khac nhau
    # (domain/entities/cell_param.py dong 24-27): sync-netact chi truyen
    # rsboost_current/qrxlevmin_current (cac field con lai None); CR-trigger flow
    # buoc 11 (WORKFLOW.md dong 176-188) truyen action_type/cr_session_id/*_new,
    # con rsboost_before_cr/qrxlevmin_before_cr van None luc nay vi da duoc ghi
    # truoc do boi snapshot_before_cr() o buoc 7 (RsboostCalculator/QrxlevminCalculator
    # khong tu set before_cr — xem test_before_cr_va_cr_session_id_deu_none).
    # => Moi field dung COALESCE(EXCLUDED.col, cell_params.col): field nao caller
    # khong truyen (None) thi giu nguyen gia tri cu trong DB — tu nhien thoa man
    # DB_SCHEMA.md dong 128-129 "sync-netact KHONG duoc ghi de *_before_cr va *_new"
    # ma khong can kiem tra rieng cr_session_id trong upsert() (schema that thieu
    # UNIQUE(tram_id, cell_name) da bo sung o migration c67cefa52d9e — xac nhan
    # voi user truoc khi lam B5.3, xem log session).
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(self, params: list[CellParam]) -> None:
        if not params:
            return

        # C1.4-fix9 (21072026) - last_synced_at/updated_at gio la TIMESTAMPTZ
        # (models/cell_params.py), PHAI giu tzinfo (KHONG .replace(tzinfo=None)
        # nhu truoc).
        now = datetime.now(timezone.utc)
        values = [
            {
                "tram_id": p.tram_id,
                "cell_name": p.cell_name,
                "huong_id": p.huong_id,
                "priority": p.priority,
                "action_type": p.action_type,
                "rsboost_current": p.rsboost_current.value if p.rsboost_current is not None else None,
                "rsboost_before_cr": p.rsboost_before_cr.value if p.rsboost_before_cr is not None else None,
                "rsboost_new": p.rsboost_new.value if p.rsboost_new is not None else None,
                "qrxlevmin_current": p.qrxlevmin_current.value if p.qrxlevmin_current is not None else None,
                "qrxlevmin_before_cr": p.qrxlevmin_before_cr.value if p.qrxlevmin_before_cr is not None else None,
                "qrxlevmin_new": p.qrxlevmin_new.value if p.qrxlevmin_new is not None else None,
                "cr_session_id": p.cr_session_id,
                "last_synced_at": now,
                "updated_at": now,
            }
            for p in params
        ]

        stmt = insert(CellParamsModel).values(values)
        stmt = stmt.on_conflict_do_update(
            # UNIQUE(tram_id, cell_name) — migration c67cefa52d9e (them rieng cho B5.3,
            # CREATE TABLE goc B4.2/B4.9 khong co, xem chu y o tren)
            index_elements=["tram_id", "cell_name"],
            set_={
                "huong_id": func.coalesce(stmt.excluded.huong_id, CellParamsModel.huong_id),
                "priority": func.coalesce(stmt.excluded.priority, CellParamsModel.priority),
                "action_type": func.coalesce(stmt.excluded.action_type, CellParamsModel.action_type),
                "rsboost_current": func.coalesce(stmt.excluded.rsboost_current, CellParamsModel.rsboost_current),
                "rsboost_before_cr": func.coalesce(
                    stmt.excluded.rsboost_before_cr, CellParamsModel.rsboost_before_cr
                ),
                "rsboost_new": func.coalesce(stmt.excluded.rsboost_new, CellParamsModel.rsboost_new),
                "qrxlevmin_current": func.coalesce(
                    stmt.excluded.qrxlevmin_current, CellParamsModel.qrxlevmin_current
                ),
                "qrxlevmin_before_cr": func.coalesce(
                    stmt.excluded.qrxlevmin_before_cr, CellParamsModel.qrxlevmin_before_cr
                ),
                "qrxlevmin_new": func.coalesce(stmt.excluded.qrxlevmin_new, CellParamsModel.qrxlevmin_new),
                "cr_session_id": func.coalesce(stmt.excluded.cr_session_id, CellParamsModel.cr_session_id),
                "last_synced_at": stmt.excluded.last_synced_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_by_tram_id(self, tram_id: str) -> list[CellParam]:
        stmt = select(CellParamsModel).where(CellParamsModel.tram_id == tram_id)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def get_by_cell_names(self, cell_names: list[str]) -> list[CellParam]:
        # Bo sung o C2.1 (12072026, xac nhan voi user) — cell lan gieng cua 1 CR
        # thuoc nhieu tram_id vat ly khac nhau, get_by_tram_id() khong dung duoc
        # cho truong hop nay (xem chu y trong domain/ports/outbound/repo_ports.py).
        # KHONG loc theo tram_id — dung dung cho TriggerCrUseCase buoc 7/9.
        if not cell_names:
            return []
        stmt = select(CellParamsModel).where(CellParamsModel.cell_name.in_(cell_names))
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def get_by_cr_session_id(self, session_id: int) -> list[CellParam]:
        # Bo sung o C2.4/C2.6 (Nhom 2, 13072026) - xem chu y trong
        # domain/ports/outbound/repo_ports.py (khac get_by_tram_id/get_by_cell_names).
        stmt = select(CellParamsModel).where(CellParamsModel.cr_session_id == session_id)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def snapshot_before_cr(self, session_id: int) -> None:
        # WORKFLOW.md Buoc 7 dong 123-135 — chay TRUOC step 11 (upsert), tren TOAN
        # BO cell_params hien co cua tram (danh sach cell cu the cua CR nay chua
        # duoc luu vao DB luc nay, se luu o buoc 11) — nen loc theo tram_id (tra ve
        # tu cr_session.tram_id qua session_id), khong loc theo cell_name.
        # WHERE cr_session_id IS NULL — bao ve khong ghi de 1 phien CR da claim
        # truoc do (DB_SCHEMA.md dong 180: moi tram chi co 1 CR session DONE, nen
        # thuc te cell_params cua tram chi bi claim 1 lan duy nhat trong doi).
        tram_id_subq = select(CrSessionModel.tram_id).where(CrSessionModel.id == session_id).scalar_subquery()
        stmt = (
            update(CellParamsModel)
            .where(CellParamsModel.tram_id == tram_id_subq, CellParamsModel.cr_session_id.is_(None))
            .values(
                rsboost_before_cr=CellParamsModel.rsboost_current,
                qrxlevmin_before_cr=CellParamsModel.qrxlevmin_current,
                cr_session_id=session_id,
                # C1.4-fix9 - updated_at TIMESTAMPTZ, giu tzinfo (xem upsert() o tren)
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
