"""
CellViTriUocLuongRepo - implement ICellViTriUocLuongRepo (doc/ghi
cell_vi_tri_uoc_luong). Tu: BUOC 4c (10/10/2026, yeu cau truc tiep user) -
xem domain/ports/outbound/repo_ports.py::ICellViTriUocLuongRepo va
models/cell_vi_tri_uoc_luong.py.
"""

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import ICellViTriUocLuongRepo
from models.cell_vi_tri_uoc_luong import CellViTriUocLuong as CellViTriUocLuongModel


class CellViTriUocLuongRepo(ICellViTriUocLuongRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def xoa_va_ghi(self, netact: str, ngay_du_lieu: date, rows: list[dict]) -> int:
        # XOA + GHI trong 1 transaction (session.commit() CUOI cung) - GIONG
        # triet ly ho_neighbor (file la snapshot DAY DU 1 lan tinh, khong
        # phai incremental) - xem adapters/netact/import_ho_neighbor.py.
        await self._session.execute(
            delete(CellViTriUocLuongModel).where(CellViTriUocLuongModel.netact == netact)
        )
        now = datetime.now(timezone.utc)
        for r in rows:
            self._session.add(
                CellViTriUocLuongModel(
                    netact=netact,
                    enb=r["enb"],
                    lcr=r["lcr"],
                    lat=r["lat"],
                    lon=r["lon"],
                    ty_le_ho_tin_cay=r["ty_le_ho_tin_cay"],
                    so_tram_dich=r["so_tram_dich"],
                    ngay_du_lieu=ngay_du_lieu,
                    created_at=now,
                )
            )
        await self._session.commit()
        return len(rows)

    async def get_by_netact(self, netact: str) -> dict[tuple[int, int], dict]:
        stmt = select(CellViTriUocLuongModel).where(CellViTriUocLuongModel.netact == netact)
        rows = (await self._session.execute(stmt)).scalars().all()
        return {
            (r.enb, r.lcr): {
                "lat": float(r.lat),
                "lon": float(r.lon),
                "ty_le_ho_tin_cay": float(r.ty_le_ho_tin_cay),
                "so_tram_dich": r.so_tram_dich,
                "ngay_du_lieu": r.ngay_du_lieu,
            }
            for r in rows
        }
