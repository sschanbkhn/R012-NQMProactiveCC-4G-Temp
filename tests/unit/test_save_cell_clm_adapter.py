"""
Unit test SaveCellClmAdapter.
Tu: yeu cau truc tiep user (KHOI 4/5 SaveCellClm).

V2 (12/08): adapter da BO tham so dry_run - goi save_cell_clm() LA POST that,
khong con che do preview. Vi vay MOI test o day deu phai patch
httpx.AsyncClient.post; fixture `chan_post_that` (autouse) chan san moi duong
ra network de mot test quen patch cung KHONG BAO GIO cham vao CTS that.
"""

import hashlib
import os

import httpx
import pytest
from dotenv import load_dotenv

from adapters.http.save_cell_clm_adapter import SaveCellClmAdapter
from adapters.http.save_cell_clm_payload import SaveCellClmPayload

load_dotenv()

_EXPECTED_FIELDS = {
    "Nam", "Thang", "TrangThai", "TenCell", "SiteName", "Qos", "Qoe", "Tsd",
    "Voice", "Ceitsd", "SoChiTieuVP", "NguyenNhan", "PhuongAnXuLyDuKien",
    "MaPhuongAn", "NoiDung", "Vendor", "UserUpdatePa", "LoaiCongNghe",
    "ProvinceCode", "WardCode", "BuildingCode", "BuildingName", "TtvtId",
    "TtvtName", "LoaiTram", "BuildingTypeName", "Address", "NguonSoLieu",
}


def _mau_payload() -> SaveCellClmPayload:
    # SoChiTieuVP=str: DO THAT bang POST that 11/08 - CTS tu choi 400 khi gui
    # Number ("could not be converted to System.String"), doi sang str thi 200.
    # TrangThai=int van giu theo spec (POST 200 chap nhan, chua co bang chung nguoc).
    return SaveCellClmPayload(
        Nam=2006,
        Thang=11,
        TrangThai=1,
        TenCell="4G-Q0718011-HDG",
        SiteName="4G-Q07180M-HCM",
        Qos="0",
        Qoe="1",
        Tsd="0",
        Voice=0,
        Ceitsd="0",
        SoChiTieuVP="1",
        NguyenNhan="NN02, NN05",
        PhuongAnXuLyDuKien="1",
        MaPhuongAn="PA01",
        NoiDung="TEST R012 - kiem tra API SaveCellClm",
        Vendor="NOKIA",
        UserUpdatePa="thembv",
        LoaiCongNghe="4G",
        ProvinceCode="HPG",
        WardCode="HPG094",
        BuildingCode="CSHT_HDG_00011",
        BuildingName="MSAT-THAI-HOC-CLH_HDG",
        TtvtId="77487",
        TtvtName="Phòng Hạ tầng ",
        LoaiTram="Macro",
        BuildingTypeName="Trạm viễn thông loại 2",
        Address="BĐVH Phạm Trấn, thôn Quang Bộ, xã Trường Tân, thành phố Hải Phòng",
        NguonSoLieu="TATHUYTRAM",
    )


# BAO MAT: KHONG hardcode secureKey THAT vao file test (file nay duoc commit
# vao git - secret se nam vinh vien trong lich su, dung thu ma .gitignore cho
# .env sinh ra de ngan). Dung key GIA cho cac test cau truc/cong thuc: chung chi
# kiem tra key nao duoc noi vao header nao, gia tri key that hay gia khong quan
# trong. Rieng test doi chieu GIA TRI VANG (05C618BE...) doc key THAT tu .env.
_FAKE_CP_SECURE_KEY = "FAKE_CP_KEY_KHONG_PHAI_KEY_THAT"  # ky X-Secure-Code (key cua cpCode)
_FAKE_ACCESS_SECURE_KEY = "FAKE_ACCESS_KEY_KHONG_PHAI_KEY_THAT"  # sinh X-Access-Key (key cua user)
_CP_CODE = "RNOC1.TTS"


@pytest.fixture(autouse=True)
def chan_post_that(monkeypatch):
    # LOP CHAN CHUNG (autouse): V2 bo dry_run nen khong con che do an toan mac
    # dinh nao trong adapter. Test nao quen patch post se noi vao CTS THAT va
    # tao phieu that tren TTS - chan o day de dieu do KHONG BAO GIO xay ra.
    async def _cam_post(*args, **kwargs):
        raise AssertionError("Test quen patch httpx.AsyncClient.post - SUYT POST THAT len TTS")

    monkeypatch.setattr("httpx.AsyncClient.post", _cam_post)


@pytest.fixture
def adapter(monkeypatch) -> SaveCellClmAdapter:
    monkeypatch.setenv("CTS_BASE_URL", "https://gw-oneoss.vnpt.vn")
    monkeypatch.setenv("SAVE_CELL_CLM_CP_SECURE_KEY", _FAKE_CP_SECURE_KEY)
    monkeypatch.setenv("SAVE_CELL_CLM_ACCESS_SECURE_KEY", _FAKE_ACCESS_SECURE_KEY)
    return SaveCellClmAdapter()


def _bat_request(monkeypatch) -> dict:
    """Patch post -> ghi lai url/json/headers da gui, tra ve 200 hop le.

    Thay cho cac test doc `result["headers"]/["body"]` cua che do dry_run cu:
    gio muon biet adapter GUI GI thi phai bat tai duong ra network."""
    da_gui: dict = {}

    async def _fake_post(self, url, json=None, headers=None, **kwargs):
        da_gui.update(url=url, body=json, headers=headers)
        return httpx.Response(
            status_code=200,
            text='{"isError":false,"code":"200","message":"OK","data":19177}',
            headers={"content-type": "application/json; charset=utf-8"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
    return da_gui


async def test_post_dung_url_endpoint(adapter, monkeypatch):
    da_gui = _bat_request(monkeypatch)

    await adapter.save_cell_clm(_mau_payload())

    assert da_gui["url"] == "https://gw-oneoss.vnpt.vn/oss/tts/ticket/ticket-tts-api/ApiCTS/SaveCellClm"


async def test_headers_du_6_header_dung_format(adapter, monkeypatch):
    da_gui = _bat_request(monkeypatch)
    await adapter.save_cell_clm(_mau_payload())
    headers = da_gui["headers"]

    assert set(headers) == {
        "X-Request-Id", "X-Request-Date", "X-Cp-Code", "X-Secure-Code",
        "Content-Type", "X-User-Name", "X-Access-Key",
    }
    assert headers["X-Cp-Code"] == _CP_CODE
    assert headers["X-User-Name"] == "CTS"

    # X-Secure-Code = SHA-512 hex -> 128 ky tu
    assert len(headers["X-Secure-Code"]) == 128
    assert all(c in "0123456789abcdef" for c in headers["X-Secure-Code"])

    # X-Access-Key = SHA-256 hex UPPERCASE -> 64 ky tu
    assert len(headers["X-Access-Key"]) == 64
    assert headers["X-Access-Key"] == headers["X-Access-Key"].upper()
    assert all(c in "0123456789ABCDEF" for c in headers["X-Access-Key"])


async def test_body_du_28_field_dung_ten(adapter, monkeypatch):
    da_gui = _bat_request(monkeypatch)
    await adapter.save_cell_clm(_mau_payload())
    body = da_gui["body"]

    assert set(body) == _EXPECTED_FIELDS
    assert len(_EXPECTED_FIELDS) == 28
    assert body["TenCell"] == "4G-Q0718011-HDG"
    assert body["Nam"] == 2006
    assert body["TrangThai"] == 1  # int theo spec, khac curl mau (string)


async def test_secure_code_ky_bang_key_cua_CPCODE(adapter, monkeypatch):
    # X-Secure-Code PHAI ky bang key cua CPCODE, KHONG phai key user.
    da_gui = _bat_request(monkeypatch)
    await adapter.save_cell_clm(_mau_payload())
    headers = da_gui["headers"]

    raw = f"{headers['X-Request-Id']}|{headers['X-Request-Date']}|{_CP_CODE}|{_FAKE_CP_SECURE_KEY}"
    assert headers["X-Secure-Code"] == hashlib.sha512(raw.encode()).hexdigest()


async def test_access_key_khop_gia_tri_THAT_da_xac_nhan():
    # GIA TRI VANG: X-Access-Key = sha256("CTS|<key user>").upper() KHONG phu thuoc
    # requestId/requestDate (khac X-Secure-Code) nen la hang so - doi chieu THANG voi
    # gia tri lay tu script da POST THAT thanh cong (phieu id=19177).
    #
    # Doc key THAT tu .env (KHONG hardcode vao file test - se lot vao git). Chi
    # HASH duoc viet trong code: hash 1 chieu, an toan de commit. skip neu may
    # chay test khong co .env (vd CI) - khong lam do ca suite.
    real_access_key = os.getenv("SAVE_CELL_CLM_ACCESS_SECURE_KEY")
    if not real_access_key:
        pytest.skip("Khong co SAVE_CELL_CLM_ACCESS_SECURE_KEY trong .env - bo qua doi chieu gia tri vang")

    computed = hashlib.sha256(f"CTS|{real_access_key}".encode()).hexdigest().upper()
    assert computed == "05C618BEA8BBD86F6DEED9A49AD6DC13525B15D57743364F9DB7BC416F8F9B02"


async def test_hai_key_KHONG_duoc_dung_lan_lon(adapter, monkeypatch):
    # Chot chan REGRESSION cho bug that: ban dau R012 dung CHUNG 1 key cho ca 2
    # header -> X-Secure-Code bi ky sai key. Test nay xac nhan 2 header duoc sinh
    # tu 2 key KHAC NHAU: neu ai do gop lai 1 key, 1 trong 2 assert se fail.
    da_gui = _bat_request(monkeypatch)
    await adapter.save_cell_clm(_mau_payload())
    headers = da_gui["headers"]

    # X-Secure-Code ky bang key USER (sai) -> PHAI khac gia tri dung
    raw_sai = f"{headers['X-Request-Id']}|{headers['X-Request-Date']}|{_CP_CODE}|{_FAKE_ACCESS_SECURE_KEY}"
    assert headers["X-Secure-Code"] != hashlib.sha512(raw_sai.encode()).hexdigest()

    # X-Access-Key sinh tu key CPCODE (sai) -> PHAI khac gia tri dung
    assert (
        headers["X-Access-Key"]
        != hashlib.sha256(f"CTS|{_FAKE_CP_SECURE_KEY}".encode()).hexdigest().upper()
    )


# ---- raw_body khi CTS tu choi (VIEC 2) ------------------------------------
# Body 400 duoi day la NGUYEN VAN response THAT da nhan tu CTS ngay 11/08 (da
# lam gon traceId) - dung ban that de test bam sat thuc te, khong tu bia format.
_BODY_400_THAT = (
    '{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.1",'
    '"title":"One or more validation errors occurred.","status":400,'
    '"errors":{"request":["The request field is required."],'
    '"$.SoChiTieuVP":["The JSON value could not be converted to System.String."]},'
    '"traceId":"00-a585b2e1-5fa0f4fd-00"}'
)


def _patch_post(monkeypatch, status_code: int, text: str, content_type: str):
    # Gia lap httpx.Response that (KHONG mock tho bang MagicMock) de di qua
    # DUNG duong resp.json()/resp.text/resp.encoding ma adapter dung.
    async def _fake_post(self, url, json=None, headers=None, **kwargs):
        return httpx.Response(
            status_code=status_code,
            text=text,
            headers={"content-type": content_type},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)


async def test_loi_400_problem_json_GIU_raw_body_khong_nuot(adapter, monkeypatch):
    # BUG THAT: 4 key chuan (isError/code/message/data) deu None voi format .NET
    # problem+json -> truoc day mat sach noi dung loi. Gio phai giu raw_body.
    _patch_post(monkeypatch, 400, _BODY_400_THAT, "application/problem+json; charset=utf-8")

    result = await adapter.save_cell_clm(_mau_payload())

    assert result["status_code"] == 400
    # 4 key chuan van None (CTS khong tra chung o format nay) - KHONG duoc crash
    assert result["isError"] is None
    assert result["message"] is None
    # raw_body PHAI giu nguyen van de doc duoc loi that
    assert "raw_body" in result
    assert "$.SoChiTieuVP" in result["raw_body"]
    assert "could not be converted to System.String" in result["raw_body"]


async def test_loi_400_body_KHONG_phai_json_van_khong_crash(adapter, monkeypatch):
    # Gateway loi ha tang co the tra HTML/text - resp.json() se raise. Truoc day
    # khong bat -> vo thanh 500 khong ro nguyen nhan. Gio phai nuot gon va giu raw.
    _patch_post(monkeypatch, 502, "<html><body>502 Bad Gateway</body></html>", "text/html")

    result = await adapter.save_cell_clm(_mau_payload())

    assert result["status_code"] == 502
    assert result["isError"] is None
    assert "502 Bad Gateway" in result["raw_body"]


async def test_loi_400_tieng_viet_co_dau_khong_hong_encoding(adapter, monkeypatch):
    # Response CTS co tieng Viet CO DAU (chinh ky tu nay tung lam crash script
    # chan doan). Xac nhan doc ra dung chu, khong hong ma.
    _patch_post(monkeypatch, 400, '{"message":"Thiếu trường bắt buộc"}', "application/json; charset=utf-8")

    result = await adapter.save_cell_clm(_mau_payload())

    assert result["message"] == "Thiếu trường bắt buộc"
    assert "Thiếu trường bắt buộc" in result["raw_body"]


async def test_200_thanh_cong_KHONG_co_raw_body_khong_regression(adapter, monkeypatch):
    # Luong THANH CONG phai giu nguyen cau truc cu: data = SO NGUYEN (id phieu),
    # va KHONG co raw_body (chi them khi that bai).
    _patch_post(monkeypatch, 200, '{"isError":false,"code":"200","message":"OK","data":19177}',
                "application/json; charset=utf-8")

    result = await adapter.save_cell_clm(_mau_payload())

    assert result["status_code"] == 200
    assert result["isError"] is False
    assert result["data"] == 19177
    assert "raw_body" not in result
