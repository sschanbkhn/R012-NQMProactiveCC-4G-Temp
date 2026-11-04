"""
SQLModel: bang cr_affected_cells.
Tu: DB_SCHEMA.md Section 8.1; alembic/versions/35c121cc3135_create_cr_affected_cells.py

Phuong an B (22072026, DA DUYET) - luu 47 cell "bi anh huong" (Nhanh A) rieng
khoi cell_params (12 cell "chay CR", Nhanh B). Khoa theo (cr_session_id,
cell_name) - GIONG qoe_snapshot/qos_snapshot (models/qoe_snapshot.py), KHONG
dung UNIQUE(tram_id, cell_name) nhu cell_params (1 cell chi giu 1 session tai
1 thoi diem, se mat lich su neu 1 cell la affected cua nhieu session).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class CrAffectedCells(SQLModel, table=True):
    __tablename__ = "cr_affected_cells"

    id: int | None = Field(default=None, primary_key=True)
    cr_session_id: int = Field(
        sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), nullable=False, index=True)
    )
    cell_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False, index=True))
    # LNBTS, nullable - mot so LNBTS chua join duoc bang tram (site chua sync
    # RIMS), van luu cell_name/huong_id de khong mat du lieu (giong xu ly
    # "missing_id" trong preview_cr_use_case.py).
    tram_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(50)))
    huong_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(10)))
    dist_name: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(300)))
    # THEM 04/10/2026 (luat xuat phieu toi da 2/sector cua tram tat) - xem
    # alembic/versions/83ce2300cade_them_cr_affected_cells_sector.py. Nullable
    # vi huong_id nguon (RAW tu CDS) co the NULL (nhom huong ten "W...") nen
    # khong phai luc nao cung suy duoc sector - KHONG ep gia tri gia.
    sector: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))

    # C1.4-fix9 (21072026) - KHONG server_default=now(), xem chu y day du
    # trong models/tram.py + alembic/versions/35c121cc3135_*.py.
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        sa.UniqueConstraint("cr_session_id", "cell_name", name="uq_affected_cells_session_cell"),
    )
