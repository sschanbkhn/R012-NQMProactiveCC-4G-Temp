"""
SyncEnodebUseCase — dong bo danh sach tram tu RIMS eNodeB API vao bang tram.
Tu: BUSINESS_RULES.md Section 10.1; API_CONTRACTS.md Section 4 (Pagination Script
Pattern, dong 322-335); CONTEXT.md Section 5.3; TASK_LIST.md C2.5

Boc lai logic cua adapters/http/sync_tram_from_enodeb.py (script thu cong, da
chay THAT thanh cong 58259 tram) thanh use case chuan - dung LAI y nguyen:
  - EnodebHttpAdapter (INetworkGateway.get_enodeb_list(), B6.4 - DA TEST THAT,
    .env-based URL/token, async httpx) THAY vi script tu goi `requests` dong
    bo + hardcode URL/TOKEN rieng.
  - IEnodebRepo.upsert_many() (B5.1 - DA TEST THAT, tu map raw dict tu API ->
    cot DB + sanitize longitude/latitude=0) THAY vi script tu quan ly
    asyncpg.connect() + SQL rieng.
Vong lap phan trang dung DUNG mau "Pagination Script Pattern" da co san trong
API_CONTRACTS.md SS4 dong 322-335 (fetch den khi 1 trang tra ve rong thi dung),
KHONG phai logic tu nghi.

CONTEXT.md SS5.3 dong 206: API nay CHI goi duoc tu IP 10.155.43.196 - job nay
phai duoc trigger tu server do (rang buoc van hanh, khong lien quan code).
"""

import logging

from domain.ports.inbound.use_case_ports import ISyncEnodebUseCase, SyncResult
from domain.ports.outbound.gateway_ports import INetworkGateway
from domain.ports.outbound.repo_ports import IEnodebRepo

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000  # API_CONTRACTS.md SS4 dong 287 - "pageSize toi da: 1000"


class SyncEnodebUseCase(ISyncEnodebUseCase):
    def __init__(self, network_gw: INetworkGateway, enodeb_repo: IEnodebRepo):
        self._network_gw = network_gw
        self._enodeb_repo = enodeb_repo

    async def execute(self, tram_id: str | None = None) -> SyncResult:
        page = 1
        total_synced = 0
        while True:
            records = await self._network_gw.get_enodeb_list(page, _PAGE_SIZE)
            if not records:
                break

            if tram_id:
                # Dung y logic --tram-id cua script cu (sync_tram_from_enodeb.py
                # dong 58-59, 65-66) - loc theo enodeb_id, dung so sanh string
                # (enodeb_id API tra ve co the la int - xac nhan that o B6.4).
                # Dung som ngay khi tim thay (giong script cu), KHONG can quet
                # het 5822 trang cho 1 tram.
                matches = [r for r in records if str(r.get("enodeb_id")) == str(tram_id)]
                if matches:
                    total_synced += await self._enodeb_repo.upsert_many(matches)
                    break
            else:
                total_synced += await self._enodeb_repo.upsert_many(records)

            page += 1

        logger.info(
            "Sync enodeb hoan thanh", extra={"total_synced": total_synced, "tram_id": tram_id}
        )
        return SyncResult(total_synced=total_synced)
