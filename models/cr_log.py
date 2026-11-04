"""
SQLModel: bang cr_log.
Tu: DB_SCHEMA.md Section 4; TASK_LIST.md B4.4
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CrLog(SQLModel, table=True):
    __tablename__ = "cr_log"

    id: int | None = Field(default=None, primary_key=True)
    cr_session_id: int = Field(
        sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), nullable=False, index=True)
    )

    step: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))
    step_name: str = Field(sa_column=sa.Column(sa.VARCHAR(100), nullable=False))
    status: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))

    message: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))
    pct: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    detail: dict | None = Field(default=None, sa_column=sa.Column(JSONB))
    # ma_loi (THEM 16/10/2026, yeu cau truc tiep user, migration VIET TAY - xem
    # alembic/versions/) - error_code cua DomainError (xem domain/errors.py),
    # CHI dien o dong status="failed" gay FAILED/KHONG_CHAY cho cr_session (xem
    # application/trigger_cr_use_case.py::_fail()) - NULL o moi dong buoc khac
    # (status="running"/"success"). VARCHAR(30) - dong bo voi cr_session.ma_loi.
    ma_loi: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(30)))

    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (sa.Index("idx_cr_log_step", "cr_session_id", "step"),)
