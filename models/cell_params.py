"""
SQLModel: bang cell_params (rsboost NUMERIC(4,1)).
Tu: DB_SCHEMA.md Section 2; TASK_LIST.md B4.2
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class CellParams(SQLModel, table=True):
    __tablename__ = "cell_params"

    id: int | None = Field(default=None, primary_key=True)
    tram_id: str = Field(
        sa_column=sa.Column(sa.VARCHAR(50), sa.ForeignKey("tram.tram_id"), nullable=False, index=True)
    )
    cell_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False, index=True))
    cell_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))

    dist_name_base: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(300), index=True))
    # SUA (13072026, xac nhan that qua psql \d cell_params tren DB that) - ten
    # cot That la "dist_name_lncel_fdd" (co suffix "_fdd"), KHONG PHAI
    # "dist_name_lncel" nhu migration f582103cf794 goc khai bao (DB da bi doi
    # ten cot ngoai luong, khong qua migration moi nao - cung dang bug doc/
    # thuc te da gap nhieu lan truoc do trong project nay).
    dist_name_lncel_fdd: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(350)))
    dist_name_sib: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(350)))

    rsboost_current: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(4, 1)))
    rsboost_before_cr: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(4, 1)))
    rsboost_new: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(4, 1)))

    qrxlevmin_current: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    qrxlevmin_before_cr: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    qrxlevmin_new: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))

    huong_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(10)))
    priority: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    action_type: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(20)))

    cr_session_id: int | None = Field(
        default=None, sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), index=True)
    )

    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
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

    __table_args__ = (
        # DB_SCHEMA.md dong 127 - "Upsert on conflict (tram_id, cell_name) -> update"
        # doi hoi UNIQUE constraint dung 2 cot nay de Postgres ON CONFLICT hoat dong.
        # Thieu o CREATE TABLE goc (B4.2/B4.9) - bo sung khi lam B5.3 (cell_params_repo.py).
        sa.UniqueConstraint("tram_id", "cell_name", name="uq_cell_params_tram_cell"),
    )
