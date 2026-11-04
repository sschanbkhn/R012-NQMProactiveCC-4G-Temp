"""
EnodebHttpAdapter — implement INetworkGateway.get_enodeb_list().
Tu: ARCHITECTURE.md Section 5.1; CONTEXT.md Section 5.3; TASK_LIST.md B6.4
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def _sanitize_coord(v):
    # API_CONTRACTS.md SS4 dong 302 - 0 la gia tri loi tu RIMS (khong phai toa do
    # that), luu NULL. Trung voi sanitize da co trong EnodebRepo.upsert_many()
    # (B5.1) - vo hai (idempotent), giu ca 2 lop vi B6.4 yeu cau ro rang tai day.
    return None if v == 0 else v


class EnodebHttpAdapter:
    # Khong ke thua INetworkGateway truc tiep - xem chu y chi tiet trong
    # adapters/http/cds_http_adapter.py (gap phat hien + da xac nhan voi user
    # khi test that B6.2).
    #
    # QUAN TRONG (CONTEXT.md SS5.3 dong 206): API nay CHI goi duoc tu IP
    # 10.155.43.196 - goi tu may khac se fail (connection refused/timeout hoac
    # 403), khong phai loi code.
    def __init__(self):
        self._url = os.getenv("ENODEB_API_URL")
        self._token = os.getenv("ENODEB_BEARER_TOKEN")

    async def get_enodeb_list(self, page: int, size: int) -> list[dict]:
        # 1 page/call - vong lap phan trang (API_CONTRACTS.md SS4 dong 310-323,
        # "Pagination Script Pattern") thuoc ve use case goi ham nay nhieu lan,
        # khong thuoc adapter (port signature nhan san page/size).
        body = {"pageIndex": page, "pageSize": size}
        headers = {"Authorization": f"Bearer {self._token}"}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self._url, json=body, headers=headers)
        resp.raise_for_status()

        records = resp.json().get("data", [])
        for r in records:
            r["longitude"] = _sanitize_coord(r.get("longitude"))
            r["latitude"] = _sanitize_coord(r.get("latitude"))
        return records
