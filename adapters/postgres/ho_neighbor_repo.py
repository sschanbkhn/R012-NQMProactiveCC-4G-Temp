"""
HoNeighborRepo - implement IHoNeighborRepo (doc ho_neighbor).
Tu: quyet dinh 06-08/10/2026 (BO CDS, thay bang HO + Delaunay) - xem
domain/ports/outbound/repo_ports.py::IHoNeighborRepo va models/ho_neighbor.py.

CHI DOC - viec NAP du lieu (xoa + insert hang loat theo netact) nam o
adapters/netact/import_ho_neighbor.py (script doc file CSV, KHONG qua repo
nay), vi do la thao tac batch 1 lan/NetAct, khac ban chat voi doc cho use
case (repo nay phuc vu doc, khong phuc vu ghi hang loat).
"""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import IHoNeighborRepo
from models.ho_neighbor import HoNeighbor as HoNeighborModel


class HoNeighborRepo(IHoNeighborRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_source_enb(self, netact: str, source_enb: int) -> list[dict]:
        stmt = select(HoNeighborModel).where(
            HoNeighborModel.netact == netact, HoNeighborModel.source_enb == source_enb
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "source_lncel_name": r.source_lncel_name,
                "source_sector": r.source_sector,
                "target_enb": r.target_enb,
                "target_lcr": r.target_lcr,
                "target_eci": r.target_eci,
                "ho_attempt": r.ho_attempt,
                "ho_sr": float(r.ho_sr) if r.ho_sr is not None else None,
                # THEM BUOC 4b (08/10/2026) - ngay du lieu THAT trong file NetAct
                # (PERIOD_START_TIME, KHAC created_at luc nap). SUA 14/10/2026
                # (yeu cau truc tiep user): KHONG con noi nao doc field nay qua
                # repo (truoc dung ghep chuoi "nguon_du_lieu" cho API preview,
                # da BO field do) - GIU LAI trong dict tra ve vi cot
                # ho_neighbor.ngay_du_lieu van giu trong DB (biet du lieu cu/
                # moi khi tra truc tiep), domain/services/ho_cell_selector.py
                # KHONG doc field nay (bo qua khoa la).
                "ngay_du_lieu": r.ngay_du_lieu,
            }
            for r in rows
        ]

    # THEM 15/10/2026 (yeu cau truc tiep user, "SUA THONG BAO KHI THIEU HO") -
    # xem dac ta ly do o domain/ports/outbound/repo_ports.py::IHoNeighborRepo.
    async def get_by_target_enb(self, netact: str, target_enb: int) -> list[dict]:
        stmt = select(HoNeighborModel.source_enb, HoNeighborModel.ho_attempt).where(
            HoNeighborModel.netact == netact, HoNeighborModel.target_enb == target_enb
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"source_enb": r.source_enb, "ho_attempt": r.ho_attempt} for r in rows]

    async def co_du_lieu_netact(self, netact: str) -> bool:
        stmt = select(exists().where(HoNeighborModel.netact == netact))
        return bool((await self._session.execute(stmt)).scalar())
