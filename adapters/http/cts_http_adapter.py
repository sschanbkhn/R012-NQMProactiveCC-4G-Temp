"""
CtsHttpAdapter — implement INetworkGateway.get_qos_metrics().
Tu: ARCHITECTURE.md Section 5.1; API_CONTRACTS.md (CTS); TASK_LIST.md B6.3
"""

import asyncio
import logging
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

from adapters.http.sha512_auth import build_sha512_headers
from domain.errors import CdsApiError

load_dotenv()

logger = logging.getLogger(__name__)

_QOS_PATH = "/oss/cts-integrate/api/CtsReport/mbb-qos-cell-4g"
_RETRY_DELAYS = [1, 2, 4]  # giong CDS - cung gateway gw-oneoss.vnpt.vn


class CtsHttpAdapter:
    # Khong ke thua INetworkGateway truc tiep - xem chu y chi tiet trong
    # adapters/http/cds_http_adapter.py (gap phat hien + da xac nhan voi user
    # khi test that B6.2/B6.3).
    #
    # CTS dung chung SHA-512 credentials voi CDS (API_CONTRACTS.md SS2 dong 116)
    # - doc cung khong dinh nghia rieng CTS_CP_CODE/CTS_SECURE_KEY trong .env.
    #
    # Khong co CtsApiError rieng trong domain/errors.py, va API_CONTRACTS.md SS7
    # "Ma loi chuan" cung chi co 1 ma CDS_API_ERROR cho ca gateway gw-oneoss.vnpt.vn
    # (CDS + CTS deu qua gateway nay) - tai su dung CdsApiError, khong tu tao class
    # moi ngoai docs.
    def __init__(self):
        self._base_url = os.getenv("CTS_BASE_URL")
        self._cp_code = os.getenv("CDS_CP_CODE")
        self._secure_key = os.getenv("CDS_SECURE_KEY")

    async def get_qos_metrics(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]:
        # API_CONTRACTS.md SS2 dong 129-140 "QUAN TRONG - to parameter": phai la
        # 23:59:59Z cuoi ngay, khong phai 00:00:00 ngay ke tiep (mat data ngay do).
        # Chuan hoa GIO cua to_dt caller truyen vao, KHONG doi NGAY - vi 2 muc dich
        # dung API nay (Widget F33 vs danh gia sau CR) can ngay "to" khac nhau hoan
        # toan (xem chu y da xac nhan voi user truoc khi code B6.3).
        to_normalized = to_dt.replace(hour=23, minute=59, second=59, microsecond=0)

        body = {
            "cell_name": cell_names,
            "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_normalized.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "granularity": "day",  # API_CONTRACTS.md dong 139 - luon "day", hardcode
        }

        last_error: Exception | None = None
        for attempt in range(3):
            headers = build_sha512_headers(self._cp_code, self._secure_key)
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(f"{self._base_url}{_QOS_PATH}", json=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                logger.warning("CTS API timeout, retry %d/3", attempt + 1, extra={"cells": len(cell_names)})
                if attempt < 2:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                continue

            if resp.status_code >= 400:
                raise CdsApiError(f"CTS API HTTP {resp.status_code}", status_code=resp.status_code)

            data = resp.json()
            if data.get("status") != "success":
                raise CdsApiError(data.get("message", "CTS API loi khong xac dinh"))

            # API_CONTRACTS.md dong 160-161 - so ngay tra ve co the it hon request
            # (missing day binh thuong) - khong validate/raise o day, tra nguyen data
            return data.get("data", [])

        raise CdsApiError(f"CTS API timeout sau 3 lan retry: {last_error}")
