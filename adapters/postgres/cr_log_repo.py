"""
CrLogRepo — implement ICrLogRepo (insert/get_by_cr_session_id).
Tu: DB_SCHEMA.md Section 4; 22072026 (xac nhan voi user) - bang cr_log da
ton tai san tu B4.4, chi thieu tang repo (cr_logs[] truoc gio LUON RONG).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import ICrLogRepo
from models.cr_log import CrLog as CrLogModel


class CrLogRepo(ICrLogRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def insert(
        self,
        cr_session_id: int,
        step: int,
        step_name: str,
        status: str,
        message: str | None,
        pct: int | None,
        ma_loi: str | None = None,
    ) -> None:
        # C1.4-fix9 - created_at set qua Python datetime.now(timezone.utc),
        # KHONG server_default (cot da la TIMESTAMPTZ tu B4.4, xem
        # models/cr_log.py).
        row = CrLogModel(
            cr_session_id=cr_session_id,
            step=step,
            step_name=step_name,
            status=status,
            message=message,
            pct=pct,
            ma_loi=ma_loi,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.commit()

    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        stmt = (
            select(CrLogModel)
            .where(CrLogModel.cr_session_id == cr_session_id)
            .order_by(CrLogModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "step": row.step,
                "step_name": row.step_name,
                "status": row.status,
                "message": row.message,
                "pct": row.pct,
                "ma_loi": row.ma_loi,
                "created_at": row.created_at,
            }
            for row in result.scalars().all()
        ]
