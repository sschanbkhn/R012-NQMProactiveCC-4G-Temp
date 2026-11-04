"""
SQLModel: bang qos_snapshot.
Tu: DB_SCHEMA.md Section 6; TASK_LIST.md B4.6
"""

from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class QosSnapshot(SQLModel, table=True):
    __tablename__ = "qos_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    cr_session_id: int = Field(
        sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), nullable=False, index=True)
    )
    cell_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False))
    snapshot_date: date = Field(sa_column=sa.Column(sa.DATE, nullable=False))
    qos_score: float = Field(sa_column=sa.Column(sa.NUMERIC(3, 2), nullable=False))
    period: str = Field(sa_column=sa.Column(sa.VARCHAR(10), nullable=False))
    source: str = Field(
        default="cts", sa_column=sa.Column(sa.VARCHAR(20), nullable=False, server_default="cts")
    )

    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
    #
    # LUU Y (20082026): day la thoi diem chup LAN DAU, KHONG phai lan ghi gan
    # nhat. upsert dung on_conflict_do_update chi cap nhat cot DIEM nen ghi de
    # 1 dong cu KHONG lam created_at moi lai. Vi vay KHONG duoc dung cot nay de
    # suy ra "cache con moi khong" - hay DEM so ngay da luu
    # (I*SnapshotRepo.dem_ngay_theo_cell()).
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        sa.UniqueConstraint("cr_session_id", "cell_name", "snapshot_date", "period"),
        sa.Index("idx_qos_cell_date", "cell_name", "snapshot_date"),
        sa.Index("idx_qos_period", "cr_session_id", "period"),
    )
