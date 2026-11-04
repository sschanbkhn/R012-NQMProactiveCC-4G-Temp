"""
SQLModel: bang audit_log.
Tu: DB_SCHEMA.md Section 8; TASK_LIST.md B4.8
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)

    actor: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100), index=True))

    action: str = Field(sa_column=sa.Column(sa.VARCHAR(50), nullable=False, index=True))

    target_type: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(50)))
    target_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100)))

    status: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False, index=True))

    detail: dict | None = Field(default=None, sa_column=sa.Column(JSONB))

    # FK optional - audit_log ghi doc lap, khong bat buoc gan voi 1 cr_session
    # (DB_SCHEMA.md dong 26, 378-379)
    cr_session_id: int | None = Field(
        default=None, sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), index=True)
    )

    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        # DB_SCHEMA.md dong 386 - DESC index, khong dung index=True (mac dinh ASC)
        sa.Index("idx_audit_created", sa.text("created_at DESC")),
    )
