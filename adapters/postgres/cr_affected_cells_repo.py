"""
CrAffectedCellsRepo — implement ICrAffectedCellsRepo (bulk_insert/get_by_cr_session_id).
Tu: DB_SCHEMA.md Section 8.1; Phuong an B (22072026, DA DUYET thiet ke).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import ICrAffectedCellsRepo
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel


class CrAffectedCellsRepo(ICrAffectedCellsRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def bulk_insert(self, cr_session_id: int, cells: list[dict]) -> int:
        if not cells:
            return 0

        # C1.4-fix9 - created_at set qua Python datetime.now(timezone.utc),
        # KHONG server_default (xem models/cr_affected_cells.py).
        now = datetime.now(timezone.utc)
        values = [
            {
                "cr_session_id": cr_session_id,
                "cell_name": c["cell_name"],
                "tram_id": c.get("tram_id"),
                "huong_id": c.get("huong_id"),
                "dist_name": c.get("dist_name"),
                # THEM 04/10/2026 (luat xuat phieu toi da 2/sector) - xem
                # models/cr_affected_cells.py.
                "sector": c.get("sector"),
                "created_at": now,
            }
            for c in cells
        ]
        stmt = insert(CrAffectedCellsModel).values(values)
        # ON CONFLICT DO NOTHING - binh thuong 1 session chi ghi affected_cells
        # DUY NHAT 1 lan (run_cr_flow() buoc 11), khong co ly do UPDATE. Chi de
        # phong truong hop goi lai cung session_id (retry ha tang) khong crash
        # IntegrityError - an toan hon la mot loi phu tro danh gia.
        stmt = stmt.on_conflict_do_nothing(index_elements=["cr_session_id", "cell_name"])
        await self._session.execute(stmt)
        await self._session.commit()
        return len(values)

    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        # ORDER BY id (SUA 18/10/2026, yeu cau hau kiem = DUNG cell anh huong
        # da luu, 1-1, giu thu tu): khong co ORDER BY thi Postgres tra theo thu
        # tu vat ly bat ky - bang hau kiem QoS/QoE, xuat Excel va xem truoc
        # phieu co the xep cell lech nhau giua 2 lan goi. id tang theo thu tu
        # bulk_insert() ghi luc chay CR nen = dung thu tu danh sach luc do.
        stmt = (
            select(CrAffectedCellsModel)
            .where(CrAffectedCellsModel.cr_session_id == cr_session_id)
            .order_by(CrAffectedCellsModel.id)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "cell_name": row.cell_name,
                "tram_id": row.tram_id,
                "huong_id": row.huong_id,
                # THEM 04/10/2026 (luat xuat phieu toi da 2/sector) - xem
                # application/xuat_phieu_use_case.py::_danh_gia_va_xep_hang().
                "sector": row.sector,
                # dist_name (THEM 04/10/2026, danh dau du lieu cu theo dieu
                # kien moi, CHI DOC) - DN THAT cua CHINH CELL nay, mang LNCEL
                # cua no (KHAC huong_id o tren, la huong_id cua TRAM TAT).
                # Cot nay DA CO SAN tu truoc (Phuong an B 22/07/2026) nhung
                # chua tung duoc doc o day - xem
                # domain/services/danh_gia_dieu_kien_cr_moi.py.
                "dist_name": row.dist_name,
            }
            for row in result.scalars().all()
        ]
