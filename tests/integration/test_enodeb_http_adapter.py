"""
Integration test cho EnodebHttpAdapter — goi RIMS eNodeB List API THAT.
Tu: API_CONTRACTS.md SS4; TASK_LIST.md B6.4

QUAN TRONG: API nay CHI goi duoc tu IP 10.155.43.196 (CONTEXT.md SS5.3). Neu chay
tu may khac IP nay, test se fail o buoc goi API that (httpx.ConnectError/Timeout/
HTTPStatusError) - KHONG phai loi code, la gioi han ha tang da biet truoc.
"""

from sqlalchemy import delete

from adapters.http.enodeb_http_adapter import EnodebHttpAdapter
from adapters.postgres.enodeb_repo import EnodebRepo
from infrastructure.db import AsyncSessionLocal
from models.tram import Tram as TramModel


async def test_get_enodeb_list_goi_that_tra_ve_dung_page_size():
    adapter = EnodebHttpAdapter()
    records = await adapter.get_enodeb_list(1, 5)
    assert isinstance(records, list)
    assert len(records) == 5
    for r in records:
        assert "enodeb_id" in r
        assert "ten_he_thong" in r


async def test_get_enodeb_list_roundtrip_qua_enodeb_repo_khong_loi_kieu_du_lieu():
    # Regression test cho bug that phat hien khi test B6.4: enodeb_id tu API la
    # int (VD 777, 888), khong phai string nhu vi du API_CONTRACTS.md - asyncpg
    # tu choi bind int vao cot VARCHAR neu EnodebRepo khong str() truoc (da fix
    # trong adapters/postgres/enodeb_repo.py).
    adapter = EnodebHttpAdapter()
    records = await adapter.get_enodeb_list(1, 2)
    tram_ids = [str(r["enodeb_id"]) for r in records]

    async with AsyncSessionLocal() as session:
        repo = EnodebRepo(session)
        try:
            count = await repo.upsert_many(records)
            assert count == len(records)

            found = await repo.find(tram_ids[0])
            assert any(t.tram_id == tram_ids[0] for t in found)
        finally:
            for tid in tram_ids:
                await session.execute(delete(TramModel).where(TramModel.tram_id == tid))
            await session.commit()
