"""
SQLModel: bang tram.
Tu: DB_SCHEMA.md Section 1; TASK_LIST.md B4.1
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Tram(SQLModel, table=True):
    __tablename__ = "tram"

    id: int | None = Field(default=None, primary_key=True)
    tram_id: str = Field(sa_column=sa.Column(sa.VARCHAR(50), nullable=False, unique=True, index=True))
    tram_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False, index=True))
    ten_quan_ly: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))
    ma_csht: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100)))
    ma_tinh: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(20)))
    longitude: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(10, 6)))
    latitude: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(10, 6)))
    ten_thiet_bi: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))
    trang_thai: str = Field(
        default="active",
        sa_column=sa.Column(sa.VARCHAR(20), nullable=False, server_default="active", index=True),
    )
    # C1.4-fix9 (21072026): TIMESTAMPTZ + default Python UTC (KHONG con
    # server_default=now()) - DB server TimeZone GUC=Asia/Ho_Chi_Minh khien
    # now() cua Postgres tra ve GIO VN thay vi UTC khi ep xuong cot TIMESTAMP
    # thuong (da xac nhan that: SELECT now()::timestamp lech +7h so UTC that).
    # default=lambda... la client-side (SQLAlchemy tu tinh truoc khi gui SQL),
    # KHONG phai server_default - ap dung cho CA insert() Core lan ORM
    # add(), khong phu thuoc session TimeZone cua ket noi dang chay.
    last_synced_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )
    updated_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )
    )
