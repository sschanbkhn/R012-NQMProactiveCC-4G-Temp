"""
AlertRepo — implement IAlertRepo (ghi alert_log).
Tu: DB_SCHEMA.md Section 7; ARCHITECTURE.md Section 5.3; TASK_LIST.md C2.7

exists_unacknowledged() them o C2.7-fix (13072026) - dedupe alert
EVAL_PENDING_TOO_LONG, dung LAI cot is_acknowledged co san (khong them cot moi).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import IAlertRepo
from models.alert_log import AlertLog as AlertLogModel


class AlertRepo(IAlertRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        cr_session_id: int,
        alert_type: str,
        severity: str,
        message: str,
        detail: dict | None = None,
    ) -> None:
        row = AlertLogModel(
            cr_session_id=cr_session_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            detail=detail,
        )
        self._session.add(row)
        await self._session.commit()

    async def exists_unacknowledged(self, cr_session_id: int, alert_type: str) -> bool:
        stmt = (
            select(AlertLogModel.id)
            .where(
                AlertLogModel.cr_session_id == cr_session_id,
                AlertLogModel.alert_type == alert_type,
                AlertLogModel.is_acknowledged.is_(False),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
