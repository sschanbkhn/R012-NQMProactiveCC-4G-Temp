"""
CemHttpAdapter — implement ISocGateway.get_qoe() bang API CEM THAT.
Tu: spec CEM (08/2026); kiem chung bang scripts/test_cem_qoe.py (goi that 15/08).

THAY THE SocHttpAdapter (mock qoe=3.5 cung, OQ-01) nhung KHONG xoa no: wiring
o infrastructure/dependencies.py chon 1 trong 2 theo bien CEM_ENABLED, doi lai
duoc bang 1 dong neu CEM co van de.

Implement DUNG chu ky ISocGateway.get_qoe(cell_names, from_dt, to_dt) -> list[dict]
nen KHONG use case nao phai sua. Shape tra ve giong het SocHttpAdapter:
    [{"cell_name": ..., "metrics": [{"time": "YYYY-MM-DDTHH:MM:SS", "qoe": float}]}]
("time" phai bat dau bang "YYYY-MM-DD" - EvaluateCrUseCase._daily_averages_dict()
cat 10 ky tu dau lam khoa ngay.)

=== 5 DIEM DAC THU CUA CEM (deu phat hien khi goi that, KHONG phai phong doan) ===
1. TLS DH key 1024-bit -> OpenSSL 3.x tu choi thang (DH_KEY_TOO_SMALL). Phai ha
   SECLEVEL=1 nhung VAN verify chung chi - xem _ssl_context().
2. Ten cell nam o "cellName" (camelCase). Response CON co "cell_id" dang so
   ("1166-29537579") - lay nham la hong doi chieu hoan toan.
3. API BO QUA cell khong co du lieu (gui 4 cell tra ve 3) -> map theo cellName,
   TUYET DOI khong zip theo thu tu.
4. 1 request = 1 NGAY. Cua so 7 ngay = 7 request, moi request gui CA danh sach
   cell trong cells[].
5. CEM TRE 2 NGAY: xin data hom qua van tra data:[] du HTTP 200 (do that 15/08).
   CTS tre 1 ngay, CEM tre 2 ngay -> cua so QoE LECH 1 NGAY so voi QoS.
   Adapter CO Y KHONG tu dich cua so (xem _canh_bao_ngay_qua_moi).
"""

import asyncio
import hashlib
import logging
import os
import ssl
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from domain.errors import CemApiError
from domain.ports.outbound.gateway_ports import ISocGateway

load_dotenv()

logger = logging.getLogger(__name__)

_API_PATH = "/api5/daily/cell/kpi"
_DEFAULT_BASE_URL = "https://api-cem.vnptmedia.vn"

# Hang so CO DINH trong cong thuc hash cua CEM, chen giua hashKey va timestamp.
# KHONG phai nam hien tai - dung thay bang datetime.now().year.
_SALT = "@2022"

# Giong CDS/CTS - so lan va nhip retry da dung o cac adapter khac, khong tu nghi
# con so moi.
_RETRY_DELAYS = [1, 2, 4]

# So ngay CEM tre so voi hom nay (do that 15/08: xin 20260815 tra rong, 20260814
# co du lieu). Chi dung de CANH BAO, khong dung de dich cua so.
_CEM_LAG_DAYS = 2

_GMT7 = timezone(timedelta(hours=7))


def _ssl_context() -> ssl.SSLContext:
    """SSLContext ha security level ve 1 NHUNG VAN verify chung chi.

    Server CEM bat tay TLS bang DH key 1024-bit; OpenSSL 3.x mac dinh SECLEVEL=2
    tu choi thang ("[SSL: DH_KEY_TOO_SMALL] dh key too small") nen httpx mac dinh
    KHONG goi duoc. Ha SECLEVEL chi de bat tay duoc voi server noi bo cu - KHONG
    tat verify (khong dung verify=False): van phai chac dang noi chuyen voi dung
    server CEM.
    """
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx


class CemHttpAdapter(ISocGateway):
    def __init__(self):
        self._account = (os.getenv("CEM_ACCOUNT") or "").strip()
        self._hash_key = (os.getenv("CEM_HASH_KEY") or "").strip()
        self._base_url = ((os.getenv("CEM_BASE_URL") or "").strip() or _DEFAULT_BASE_URL).rstrip("/")

        # DUNG NGAY luc khoi tao neu thieu credential - KHONG de den luc goi API
        # moi phat hien qua 401. Ly do: 401 cua CEM chi noi "SecureCode is not
        # valid!", nguoi doc log se di do cong thuc hash/timestamp trong khi
        # nguyen nhan that chi la quen dien .env. ValueError (khong phai
        # DomainError) - day la loi CAU HINH luc khoi dong, khong phai loi
        # nghiep vu de tra ve cho client.
        thieu = [
            ten
            for ten, gia_tri in (("CEM_ACCOUNT", self._account), ("CEM_HASH_KEY", self._hash_key))
            if not gia_tri
        ]
        if thieu:
            raise ValueError(
                f"CemHttpAdapter: thieu bien moi truong {', '.join(thieu)} trong .env "
                "(xem .env.example muc CEM API). Xin credential tu VNPT-TSC, hoac dat "
                "CEM_ENABLED=false de dung lai SocHttpAdapter mock."
            )

    # === Auth ===
    def _secure_code(self, request_id: str, timestamp: str) -> str:
        """SHA-256(request_id + account + hashKey + "@2022" + timestamp).

        KHAC HAN CDS/CTS (adapters/http/sha512_auth.py): CDS/CTS dung SHA-512,
        co dau phan cach pipe "|", va gui qua HEADER X-*. CEM noi THANG khong
        dau phan cach, SHA-256, va tat ca nam trong BODY. Dung nham 1 trong 3
        diem deu ra 401 giong het nhau.
        """
        raw = f"{request_id}{self._account}{self._hash_key}{_SALT}{timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _body(self, cell_names: list[str], ngay: date) -> dict:
        # timestamp phai lech KHONG QUA 30 PHUT so voi gio server -> sinh MOI
        # cho tung request, khong tai dung giua cac ngay trong vong lap (7
        # request co the keo dai neu CEM cham).
        #
        # Gio LOCAL cua may (khong phai UTC): da xac minh bang goi that - server
        # CEM chap nhan gio GMT+7 cua may VN. Neu sau nay deploy len may dat
        # timezone khac se phai xem lai cho nay.
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        request_id = str(uuid.uuid4())
        return {
            "request_id": request_id,
            "timestamp": timestamp,
            "account": self._account,
            "secure_code": self._secure_code(request_id, timestamp),
            "date": ngay.strftime("%Y%m%d"),
            "cells": cell_names,
        }

    # === Goi 1 ngay ===
    async def _goi_mot_ngay(
        self, client: httpx.AsyncClient, cell_names: list[str], ngay: date
    ) -> list[dict]:
        url = f"{self._base_url}{_API_PATH}"
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                resp = await client.post(url, json=self._body(cell_names, ngay))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                logger.warning(
                    "CEM API timeout, retry %d/3", attempt + 1, extra={"ngay": str(ngay)}
                )
                if attempt < 2:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                continue

            if resp.status_code >= 400:
                # KHONG retry loi 4xx/5xx: 401 (sai credential) va 400 (sai cu
                # phap) thu lai bao nhieu lan cung y het. Nem luon de nguoi truc
                # thay ngay, thay vi tra ve QoE thieu ngay roi bi hieu nham
                # thanh "CEM chua co data".
                raise CemApiError(
                    f"CEM API HTTP {resp.status_code} cho ngay {ngay}: {resp.text[:300]}",
                    status_code=resp.status_code,
                )

            data = resp.json()
            # CEM tra 200 + data:[] khi khong co du lieu (ngay chua chot so lieu,
            # hoac cell khong ton tai) - day la BINH THUONG, khong phai loi.
            return data.get("data") or []

        raise CemApiError(f"CEM API timeout sau 3 lan retry (ngay {ngay}): {last_error}")

    def _canh_bao_ngay_qua_moi(self, ngay_list: list[date]) -> None:
        """Canh bao khi cua so xin data cham vao vung CEM CHUA CO.

        CO Y KHONG TU DICH CUA SO: cua so T-7..T-1 / T+1..T+7 la QUYET DINH
        NGHIEP VU cua EvaluateCrUseCase (BUSINESS_RULES.md SS8.2). Adapter tu tru
        2 ngay se lam ket qua danh gia khac voi dieu docs mo ta ma khong ai biet.
        Thay vao do tra ve dung nhung gi CEM co - ngay thieu se lam so ngay < 5
        -> INSUFFICIENT_DATA -> EVAL_PENDING -> n8n goi lai hom sau (co che da
        co san, dung cho dung truong hop nay).
        """
        moc = datetime.now(_GMT7).date() - timedelta(days=_CEM_LAG_DAYS)
        qua_moi = [n for n in ngay_list if n > moc]
        if qua_moi:
            logger.warning(
                "CEM tre %d ngay - %d/%d ngay trong cua so nhieu kha nang tra ve rong",
                _CEM_LAG_DAYS,
                len(qua_moi),
                len(ngay_list),
                extra={"ngay_qua_moi": [str(n) for n in qua_moi]},
            )

    # === Port ===
    async def get_qoe(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]:
        if not cell_names:
            return []

        # 1 request = 1 NGAY -> tra ngay tung ngay trong cua so (bao gom CA 2
        # dau mut, giong cach CTS hieu from/to).
        so_ngay = (to_dt.date() - from_dt.date()).days
        if so_ngay < 0:
            return []
        ngay_list = [from_dt.date() + timedelta(days=i) for i in range(so_ngay + 1)]
        self._canh_bao_ngay_qua_moi(ngay_list)

        # Khoi tao DU cell duoc hoi (ke ca cell CEM khong tra ve) - giu hop dong
        # "1 entry cho 1 cell da hoi" giong SocHttpAdapter. Cell khong co du lieu
        # se co metrics rong, KHONG bien mat khoi ket qua.
        diem_theo_cell: dict[str, list[dict]] = {ten: [] for ten in cell_names}

        async with httpx.AsyncClient(verify=_ssl_context(), timeout=60) as client:
            for ngay in ngay_list:
                for ban_ghi in await self._goi_mot_ngay(client, cell_names, ngay):
                    # "cellName" camelCase - KHONG phai "cell_name". Response con
                    # co "cell_id" dang so, lay nham la khong khop cell nao.
                    ten = ban_ghi.get("cellName")
                    ux_final = ban_ghi.get("ux_final")
                    if ten is None or ux_final is None:
                        continue
                    if ten not in diem_theo_cell:
                        # CEM tra ve cell KHONG nam trong danh sach da hoi -
                        # khong nen xay ra; bo qua thay vi them vao ket qua (se
                        # lam sai trung binh cua session).
                        logger.warning("CEM tra ve cell khong hoi: %s", ten, extra={"ngay": str(ngay)})
                        continue
                    diem_theo_cell[ten].append(
                        {
                            # CEM tra du lieu THEO NGAY (khong co gio) - dat
                            # 00:00:00 cho dung dinh dang ISO ma
                            # _daily_averages_dict() doi (no chi doc 10 ky tu dau).
                            "time": f"{ngay.isoformat()}T00:00:00",
                            # ux_final la thang 1-5 (da xac minh du lieu that:
                            # 3/5/5). KHONG dung ux_final_idx_value - do la thang
                            # 0-100, lay nham thi nguong chenh lech 0.2 cua
                            # BUSINESS_RULES thanh vo nghia.
                            "qoe": float(ux_final),
                        }
                    )

        thieu = [ten for ten, diem in diem_theo_cell.items() if not diem]
        if thieu:
            logger.info(
                "CEM khong co du lieu cho %d/%d cell trong cua so",
                len(thieu),
                len(cell_names),
                extra={"cells_thieu": thieu[:20]},
            )

        return [{"cell_name": ten, "metrics": diem} for ten, diem in diem_theo_cell.items()]
