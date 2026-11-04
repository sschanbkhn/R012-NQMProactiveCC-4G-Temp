"""
SQLModel: bang alert_log.
Tu: DB_SCHEMA.md Section 7; TASK_LIST.md B4.7
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AlertLog(SQLModel, table=True):
    __tablename__ = "alert_log"

    id: int | None = Field(default=None, primary_key=True)
    cr_session_id: int = Field(
        sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), nullable=False, index=True)
    )
    alert_type: str = Field(sa_column=sa.Column(sa.VARCHAR(50), nullable=False, index=True))

    severity: str = Field(
        default="WARNING", sa_column=sa.Column(sa.VARCHAR(20), nullable=False, server_default="WARNING")
    )

    message: str = Field(sa_column=sa.Column(sa.TEXT, nullable=False))
    detail: dict | None = Field(default=None, sa_column=sa.Column(JSONB))

    is_acknowledged: bool = Field(
        default=False,
        sa_column=sa.Column(sa.BOOLEAN, nullable=False, server_default=sa.false(), index=True),
    )
    acknowledged_by: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100)))
    # KHONG doi (van TIMESTAMP thuong) - hien khong co code nao set gia tri
    # nay (TU GIA DINH ack chua duoc code, xem TASK_LIST.md), khong dinh bug
    # server_default=now() nen ngoai pham vi 13 cot C1.4-fix9.
    acknowledged_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP))

    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        # DB_SCHEMA.md dong 329 - DESC index, khong dung index=True (mac dinh ASC)
        sa.Index("idx_alert_created", sa.text("created_at DESC")),
    )
