"""
CdsHttpAdapter — implement INetworkGateway.get_cell_neighbors().
Tu: ARCHITECTURE.md Section 5.1; API_CONTRACTS.md (CDS); TASK_LIST.md B6.2
"""

import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv

from adapters.http.sha512_auth import build_sha512_headers
from domain.errors import CdsApiError

load_dotenv()

logger = logging.getLogger(__name__)

_NEIGHBORS_PATH = "/oss/vps/service/vpsService/cell/neighbors"
_RETRY_DELAYS = [1, 2, 4]  # API_CONTRACTS.md SS1 dong 15 - backoff 1s/2s/4s

# Mac dinh CU, GIU NGUYEN cho moi caller khong truyen gi (luong CR that chay
# nen, script chan doan): 3 lan x 30s + 3s cho = toi da 93s.
_TIMEOUT_MAC_DINH = 30
_SO_LAN_THU_MAC_DINH = 3


class CdsHttpAdapter:
    # GAP phat hien khi test that (B6.2): INetworkGateway (B2.7, domain/ports) la
    # 1 ABC gom ca 3 method (get_cell_neighbors/get_qos_metrics/get_enodeb_list),
    # nhung ARCHITECTURE.md SS5.1 lai chia 3 file adapter rieng - khong class nao
    # co du 3 method de Python cho instantiate ABC. Da xac nhan voi user: class nay
    # KHONG ke thua INetworkGateway truc tiep, chi implement dung 1 method tuong
    # ung. INetworkGateway se duoc thoa man gian tiep qua 1 composite/facade o
    # B8.1 (DI wiring, chua lam) delegate get_cell_neighbors() sang class nay.
    def __init__(self):
        self._base_url = os.getenv("CDS_BASE_URL")
        self._cp_code = os.getenv("CDS_CP_CODE")
        self._secure_key = os.getenv("CDS_SECURE_KEY")

    async def get_cell_neighbors(
        self,
        tram_id: str,
        tram_name: str,
        action: str,
        timeout: int = _TIMEOUT_MAC_DINH,
        so_lan_thu: int = _SO_LAN_THU_MAC_DINH,
    ) -> list[dict]:
        # timeout/so_lan_thu them o V6 (12/08, yeu cau truc tiep user).
        #
        # VI SAO PHAI THAM SO HOA thay vi nang thang 30 -> 120: method nay dung
        # CHUNG cho 2 luong co yeu cau NGUOC NHAU:
        #   - POST /cr/preview: DONG BO, nguoi dung ngoi cho truoc man hinh ->
        #     can chiu duoc 1 lan goi lau (120s), va KHONG nen retry (nguoi dung
        #     CHINH LA co che retry - ho bam lai; retry tu dong chi bat ho nhin
        #     spinner 6 phut roi moi bao loi).
        #   - run_cr_flow() (CR that): chay NEN qua BackgroundTasks, khong ai
        #     cho -> retry 3 lan la dung, con timeout dai chi lam session treo
        #     lau hon khi CDS chet.
        # Mac dinh GIU NGUYEN 30s x 3 nen moi noi goi cu khong doi hanh vi.
        #
        # B2.7 - "technology" luon "4G", khong can tham so port (CONTEXT.md SS5.1)
        body = {"tramId": tram_id, "tramName": tram_name, "action": action, "technology": "4G"}

        last_error: Exception | None = None
        for attempt in range(so_lan_thu):
            headers = build_sha512_headers(self._cp_code, self._secure_key)
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{self._base_url}{_NEIGHBORS_PATH}", json=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # CONTEXT.md SS5.1 dong 171 - retry khi timeout, khong retry khi 4xx
                last_error = e
                logger.warning(
                    "CDS API timeout, retry %d/%d", attempt + 1, so_lan_thu, extra={"tram_id": tram_id}
                )
                if attempt < so_lan_thu - 1:
                    # min(): so_lan_thu co the lon hon so phan tu cua _RETRY_DELAYS
                    # -> giu nguyen do tre CUOI CUNG thay vi IndexError.
                    await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
                continue

            if resp.status_code >= 400:
                # 4xx/5xx - khong retry (CONTEXT.md SS5.1 dong 171)
                raise CdsApiError(
                    f"CDS API HTTP {resp.status_code}", tram_id=tram_id, status_code=resp.status_code
                )

            data = resp.json()
            if data.get("status") != "success":
                # Loi nghiep vu (VD SITE_NOT_FOUND) - API_CONTRACTS.md SS1 dong 86-94,
                # khong retry vi khong phai loi mang tam thoi
                raise CdsApiError(
                    data.get("message", "CDS API loi khong xac dinh"),
                    tram_id=tram_id,
                    error_code_cds=data.get("error_code"),
                )

            # NeighborCellService.filter() (B3.2) nhan thang raw_huongs: list[dict]
            # - tra ve dung field "huongs" tu response, khong wrap/transform gi them
            return data.get("huongs", [])

        raise CdsApiError(
            f"CDS API timeout sau {so_lan_thu} lan thu: {last_error}", tram_id=tram_id
        )
