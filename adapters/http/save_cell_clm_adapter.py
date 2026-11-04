"""
SaveCellClmAdapter — implement ISaveCellClmGateway.save_cell_clm().
Tu: yeu cau truc tiep user (KHOI 3/5 SaveCellClm).

Tai dung build_sha512_headers() (adapters/http/sha512_auth.py) da verify that
qua CtsHttpAdapter (QoS, cpCode VNPT.NET.KTM.SOC) - CHI truyen cpCode/secureKey
khac (RNOC1.TTS), KHONG viet lai cong thuc. Them build_access_key() (cung
file, moi) cho 2 header rieng SaveCellClm can (X-User-Name/X-Access-Key) ma
CDS/CTS QoS khong dung.

SUA (doi chieu script da POST THAT thanh cong, tao phieu id=19177): dung HAI
secureKey KHAC NHAU - key cua cpCode cho X-Secure-Code, key cua user cho
X-Access-Key. Ban dau R012 dung CHUNG 1 key cho ca 2 -> X-Secure-Code invalid.

!!! QUY TAC BAT BUOC - POST THAT CHI DUOC DI QUA XuatPhieuUseCase !!!
V2 (12/08): da BO tham so dry_run - GOI HAM NAY LA POST THAT, khong con che do
preview nao de "thu cho an toan". Script chan doan / script chay tay TUYET DOI
khong duoc goi thang vao day; muon xuat phieu thi PHAI goi qua
application/xuat_phieu_use_case.py::XuatPhieuUseCase.execute().

LY DO (su co THAT 11/08/2026 - PHIEU MO COI): 1 script chan doan goi
httpx.post() THANG vao endpoint nay de xem raw response. POST tra 200 -> CTS
DA TAO PHIEU THAT tren TTS, nhung script khong co code ghi DB nen cr_phieu
KHONG co dau vet; dong thoi script crash luc in response (UnicodeEncodeError
cp1252 do tieng Viet co dau) -> MAT LUON id phieu. SaveCellClm KHONG co API
GET nen khong truy lai duoc - phieu do gio mo coi tren TTS.
XuatPhieuUseCase ghi cr_phieu trang_thai PENDING TRUOC khi POST va log
phieu_id NGAY sau khi POST thanh cong -> du buoc sau co chet van con dau vet.
"""

import logging
import os

import httpx
from dotenv import load_dotenv

from adapters.http.sha512_auth import build_access_key, build_sha512_headers
from adapters.http.save_cell_clm_payload import SaveCellClmPayload
from domain.errors import SaveCellClmApiError
from domain.ports.outbound.gateway_ports import ISaveCellClmGateway

load_dotenv()

logger = logging.getLogger(__name__)

_SAVE_CELL_CLM_PATH = "/oss/tts/ticket/ticket-tts-api/ApiCTS/SaveCellClm"
_TIMEOUT = 30

# cpCode/userName co dinh theo he thong dich (TTS) - KHAC CDS_CP_CODE
# (VNPT.NET.KTM.SOC) ma CtsHttpAdapter (QoS) dang dung, nen KHONG doc tu
# CDS_CP_CODE trong .env - tranh nham lan 2 he thong dung chung 1 bien.
#
# SUA (doi chieu script da POST THAT thanh cong, tao phieu id=19177): cpCode
# dung la "RNOC1.TTS" - ban dau R012 dung "VNPT.HNI.TTS" (lay tu curl mau CU,
# chua tung POST thanh cong) nen X-Secure-Code ky sai cpCode.
_CP_CODE = "RNOC1.TTS"
_USER_NAME = "CTS"


class SaveCellClmAdapter(ISaveCellClmGateway):
    def __init__(self):
        self._base_url = os.getenv("CTS_BASE_URL")
        # HAI key KHAC NHAU, KHONG duoc dung chung 1 key cho ca 2 header (bug
        # that: ban dau R012 dung 1 key cho ca 2 -> X-Secure-Code invalid):
        #   - cp_secure_key: key cua CPCODE, ky X-Secure-Code (doi khi doi cpCode)
        #   - access_secure_key: key cua USER (userName="CTS"), sinh X-Access-Key
        #     (dinh danh user, KHONG doi theo cpCode)
        # Ca 2 doc tu .env, KHONG hardcode secret trong code (dung pattern
        # CdsHttpAdapter/CtsHttpAdapter).
        self._cp_secure_key = os.getenv("SAVE_CELL_CLM_CP_SECURE_KEY")
        self._access_secure_key = os.getenv("SAVE_CELL_CLM_ACCESS_SECURE_KEY")

    async def save_cell_clm(self, payload: dict | SaveCellClmPayload) -> dict:
        # payload nhan CA dict (28 field tho) LAN SaveCellClmPayload da dung san -
        # KHOI 3a/5 (XuatPhieuUseCase, tang application/) KHONG duoc import
        # adapters/ truc tiep (ARCHITECTURE.md SS9 dependency rule), nen se luon
        # truyen dict thuan. Adapter TU validate/ep kieu qua SaveCellClmPayload o
        # day - khop dung ranh gioi Hexagonal (adapter la noi duy nhat duoc phep
        # biet ve wire contract).
        validated = payload if isinstance(payload, SaveCellClmPayload) else SaveCellClmPayload(**payload)

        # X-Secure-Code ky bang key cua CPCODE
        headers = build_sha512_headers(_CP_CODE, self._cp_secure_key)
        # 2 header phu SaveCellClm can, ngoai 4 header SHA-512 chuan CDS/CTS dung chung.
        # X-Access-Key sinh tu key cua USER - KEY KHAC voi tren, xem __init__().
        headers["X-User-Name"] = _USER_NAME
        headers["X-Access-Key"] = build_access_key(_USER_NAME, self._access_secure_key)

        body = validated.model_dump()
        url = f"{self._base_url}{_SAVE_CELL_CLM_PATH}"

        logger.warning(
            "SaveCellClm - POST THAT vao CTS/TTS",
            extra={"cell": validated.TenCell, "url": url},
        )
        # KHONG retry O TANG NAY (khac CdsHttpAdapter/CtsHttpAdapter - 3 lan
        # 1s/2s/4s ngay trong adapter): day la WRITE API tao phieu that, POST
        # lai sau loi mang co the tao PHIEU TRUNG neu lan dau thuc ra da toi
        # server thanh cong nhung response bi mat tren duong ve.
        #
        # V3 (12/08) - viec THU LAI da duoc dua len XuatPhieuUseCase, cho do
        # PHAN LOAI duoc loi (mang/5xx thi thu lai, 4xx/isError thi dung ngay)
        # va ghi duoc so lan da thu xuong cr_phieu.so_lan_thu. Adapter GIU
        # NGUYEN nguyen tac "goi 1 lan, bao cao trung thuc" - khong tu y POST
        # lai sau lung caller.
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SaveCellClmApiError(
                f"SaveCellClm POST that loi mang/timeout: {exc}",
                cell=validated.TenCell,
            ) from exc

        # Encoding: response CTS co tieng Viet CO DAU. httpx tu decode theo
        # charset trong Content-Type, nhung neu server KHONG khai bao charset
        # thi httpx doan (co the ra cp1252 tren may Windows) -> hong chu.
        # Ep utf-8 tuong minh khi thieu charset de doc dung moi truong hop.
        if resp.encoding is None:
            resp.encoding = "utf-8"
        raw_text = resp.text

        # resp.json() CO THE RAISE neu body khong phai JSON (vd gateway tra
        # HTML/text khi loi ha tang) - truoc day khong bat -> vo thanh loi 500
        # khong ro nguyen nhan. Bat lai, coi nhu khong co 4 key chuan.
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            # phong truong hop CTS tra JSON scalar/array (khong co .get())
            data = {}

        result = {
            "status_code": resp.status_code,
            "isError": data.get("isError"),
            "code": data.get("code"),
            "message": data.get("message"),
            "data": data.get("data"),
            "totalRecord": data.get("totalRecord"),
        }

        # BUG THAT (11/08): khi CTS tu choi, no tra dang .NET
        # "application/problem+json" voi cac key HOAN TOAN KHAC (title/status/
        # errors/traceId) - 4 key chuan o tren deu None -> MAT SACH noi dung
        # loi, phai viet script POST vong ngoai moi doc duoc (gay ra 1 phieu mo
        # coi tren TTS). Giu NGUYEN VAN body khi that bai de khong ai phai
        # bypass use case nua. CHI them khi that bai - response 200 giu nguyen
        # cau truc cu, KHONG regression cho luong thanh cong.
        if resp.status_code >= 400 or data.get("isError"):
            result["raw_body"] = raw_text
            logger.error(
                "SaveCellClm CTS TU CHOI - giu raw_body de debug",
                extra={
                    "cell": validated.TenCell,
                    "status_code": resp.status_code,
                    "raw_body": raw_text[:2000],  # cat bot cho log, raw_body tra ve van du
                },
            )
        return result
