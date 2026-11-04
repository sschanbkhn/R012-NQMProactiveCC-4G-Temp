"""
QosSnapshotRepo — implement IQosSnapshotRepo (upsert_many/get_by_session_id).
Tu: DB_SCHEMA.md Section 5; ARCHITECTURE.md Section 5.3; Nhom 4 (13072026).

SUA 20082026 - LUU PER-CELL: truoc day cell_name ghi hang so sentinel
"__ALL_CELLS__" vi EvaluateCrUseCase gop cheo moi cell thanh 1 con so/ngay.
Do la CHO CUOI CUNG con sot lai cua cach "gop chung moi cell" - da bo o moi
noi khac (QoE per-cell 17/08, danh gia per-cell cua xuat phieu tu truoc). Gio
ghi TEN CELL THAT, dung dung schema goc (1 dong/cell/ngay).
10 dong sentinel cu da bi XOA (chung tu 1 lan chay thu evaluate_mot_session.py
--session 553, khong phai du lieu that co gia tri).
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import IQosSnapshotRepo
from models.qos_snapshot import QosSnapshot as QosSnapshotModel


class QosSnapshotRepo(IQosSnapshotRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_many(self, cr_session_id: int, points: list[dict]) -> int:
        if not points:
            return 0

        values = [
            {
                "cr_session_id": cr_session_id,
                # Ten cell THAT (18082026 -> 20082026). Truoc day la sentinel
                # "__ALL_CELLS__" vi EvaluateCrUseCase gop cheo moi cell
                # thanh 1 con so/ngay - cho CUOI CUNG con sot lai cua
                # cach lam do, da bo o moi noi khac.
                "cell_name": p["cell_name"],
                "snapshot_date": p["snapshot_date"],
                "qos_score": p["qos_score"],
                "period": p["period"],
                "source": "cts",
            }
            for p in points
        ]
        stmt = insert(QosSnapshotModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["cr_session_id", "cell_name", "snapshot_date", "period"],
            set_={"qos_score": stmt.excluded.qos_score},
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return len(values)

    async def get_by_session_id(self, cr_session_id: int) -> list[dict]:
        stmt = (
            select(QosSnapshotModel)
            .where(QosSnapshotModel.cr_session_id == cr_session_id)
            .order_by(QosSnapshotModel.snapshot_date)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "cell_name": row.cell_name,
                "snapshot_date": row.snapshot_date,
                "qos_score": float(row.qos_score),
                "period": row.period,
                # THEM 18/10/2026 - thoi diem chup LAN DAU (upsert giu nguyen
                # created_at) -> API tra "ngay_chup_snapshot" cho FE ghi "So lieu
                # tai thoi diem danh gia dd/mm".
                "created_at": row.created_at,
            }
            for row in result.scalars().all()
        ]

    async def dem_ngay_theo_cell(self, cr_session_id: int) -> dict:
        """{(cell_name, period): so_ngay} - dem so NGAY co du lieu da luu.

        Dung cho lazy cache: du 7 ngay before + 7 ngay after thi KHONG can goi
        API nua.

        VI SAO DEM thay vi dua vao created_at: upsert dung
        on_conflict_do_update chi cap nhat cot DIEM, GIU NGUYEN created_at -
        nen created_at la "thoi diem chup LAN DAU", KHONG phai lan ghi gan
        nhat. No noi doi ve thoi diem cua so hien tai. Dem so ngay la du kien
        TRUC TIEP: co du 7 ngay hay khong, khong can biet chup luc nao.
        """
        stmt = (
            select(
                QosSnapshotModel.cell_name,
                QosSnapshotModel.period,
                func.count().label("so_ngay"),
            )
            .where(QosSnapshotModel.cr_session_id == cr_session_id)
            .group_by(QosSnapshotModel.cell_name, QosSnapshotModel.period)
        )
        result = await self._session.execute(stmt)
        return {(r.cell_name, r.period): r.so_ngay for r in result}
