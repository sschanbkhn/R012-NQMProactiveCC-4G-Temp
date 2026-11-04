"""
Unit test cho CemHttpAdapter (16082026) - MOCK httpx, KHONG goi API that.

Mau JSON trong file nay CHEP TU response THAT cua CEM (goi that 15/08 qua
scripts/test_cem_qoe.py, date=20260814), da cat bot cac truong khong dung toi.
Giu nguyen ten truong camelCase/snake_case y het ban that - doi 1 ky tu la test
khong con bao ve duoc gi.
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from adapters.http.cem_http_adapter import CemHttpAdapter
from domain.errors import CemApiError

CELL_A = "4G-SSN087M43-HNI"
CELL_B = "4G-SSN104M12-HNI"
CELL_C = "4G-SSN019M41-HNI"

ENV_DU = {
    "CEM_ACCOUNT": "NET_KTM_TEST",
    "CEM_HASH_KEY": "KEY_TEST_KHONG_THAT",
    "CEM_BASE_URL": "https://cem-test.local",
}


def _ban_ghi(cell_name: str, ux_final: float, cell_id: str = "1166-29537579") -> dict:
    # Rut gon tu response THAT - giu lai dung cac truong co y nghia cho test:
    # cellName (ten that), cell_id (bay: cung la "id" nhung dang so), ux_final
    # (thang 1-5), ux_final_idx_value (thang 0-100 - KHONG duoc lay nham).
    return {
        "date": "20260814",
        "cell_id": cell_id,
        "cellName": cell_name,
        "ux_final": ux_final,
        "ux_final_idx_value": 98.25,
        "ux_1": 5.0,
        "vol_downlink": 2.544786843e9,
    }


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def _client_gia(responses: list[_FakeResponse]):
    """AsyncClient gia - tra lan luot cac response da chuan bi.

    patch vao httpx.AsyncClient nen KHONG co ket noi mang nao duoc mo, ke ca khi
    test chay tren may co internet.
    """
    client = AsyncMock()
    client.post = AsyncMock(side_effect=responses)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _adapter() -> CemHttpAdapter:
    with patch.dict("os.environ", ENV_DU, clear=False):
        return CemHttpAdapter()


# === Khoi tao / cau hinh ===


class TestKhoiTao:
    def test_thieu_account_raise_ngay_luc_khoi_tao(self):
        # KHONG duoc de den luc goi API moi 401 - 401 cua CEM chi noi
        # "SecureCode is not valid!", nguoi doc log se di do cong thuc hash.
        with patch.dict("os.environ", {"CEM_ACCOUNT": "", "CEM_HASH_KEY": "K"}, clear=False):
            with pytest.raises(ValueError, match="CEM_ACCOUNT"):
                CemHttpAdapter()

    def test_thieu_hash_key_raise_ngay_luc_khoi_tao(self):
        with patch.dict("os.environ", {"CEM_ACCOUNT": "A", "CEM_HASH_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="CEM_HASH_KEY"):
                CemHttpAdapter()

    def test_thieu_ca_hai_bao_ten_ca_hai_bien(self):
        with patch.dict("os.environ", {"CEM_ACCOUNT": "", "CEM_HASH_KEY": ""}, clear=False):
            with pytest.raises(ValueError) as exc:
                CemHttpAdapter()
        assert "CEM_ACCOUNT" in str(exc.value)
        assert "CEM_HASH_KEY" in str(exc.value)

    def test_thieu_base_url_thi_dung_mac_dinh_khong_raise(self):
        # base_url co gia tri mac dinh hop ly - KHONG phai credential nen khong
        # bat buoc dien.
        with patch.dict(
            "os.environ", {"CEM_ACCOUNT": "A", "CEM_HASH_KEY": "K", "CEM_BASE_URL": ""}, clear=False
        ):
            adapter = CemHttpAdapter()
        assert adapter._base_url == "https://api-cem.vnptmedia.vn"


# === Auth ===


class TestSecureCode:
    def test_cong_thuc_noi_thang_sha256_co_salt_2022(self):
        adapter = _adapter()
        mong_doi = hashlib.sha256(
            f"req-1{ENV_DU['CEM_ACCOUNT']}{ENV_DU['CEM_HASH_KEY']}@202220260814120000".encode()
        ).hexdigest()
        assert adapter._secure_code("req-1", "20260814120000") == mong_doi

    def test_khong_dung_sha512_nhu_cds(self):
        # CDS/CTS dung SHA-512 + pipe - lay nham se ra 401 kho doan.
        adapter = _adapter()
        assert len(adapter._secure_code("req-1", "20260814120000")) == 64  # sha256 hex

    def test_moi_request_sinh_request_id_va_timestamp_moi(self):
        # timestamp phai lech <= 30 phut so voi server -> khong duoc tai dung
        # giua cac ngay trong vong lap 7 request.
        adapter = _adapter()
        b1 = adapter._body([CELL_A], datetime(2026, 8, 14).date())
        b2 = adapter._body([CELL_A], datetime(2026, 8, 14).date())
        assert b1["request_id"] != b2["request_id"]
        assert b1["secure_code"] != b2["secure_code"]

    def test_body_du_6_truong_theo_spec(self):
        adapter = _adapter()
        body = adapter._body([CELL_A, CELL_B], datetime(2026, 8, 14).date())
        assert set(body) == {"request_id", "timestamp", "account", "secure_code", "date", "cells"}
        assert body["date"] == "20260814"  # yyyyMMdd
        assert body["cells"] == [CELL_A, CELL_B]  # gui CA danh sach cell trong 1 request


# === Map ket qua ===


class TestMapKetQua:
    async def test_lay_dung_ux_final_theo_cellName(self):
        resp = _FakeResponse({"message": "Success", "data": [_ban_ghi(CELL_A, 5.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )

        assert ket_qua == [
            {"cell_name": CELL_A, "metrics": [{"time": "2026-08-14T00:00:00", "qoe": 5.0}]}
        ]

    async def test_KHONG_lay_nham_ux_final_idx_value(self):
        # ux_final_idx_value la thang 0-100 - lay nham thi nguong chenh lech 0.2
        # cua BUSINESS_RULES thanh vo nghia.
        resp = _FakeResponse({"data": [_ban_ghi(CELL_A, 3.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )
        assert ket_qua[0]["metrics"][0]["qoe"] == 3.0  # ux_final, KHONG phai 98.25

    async def test_KHONG_lay_nham_cell_id_dang_so(self):
        # Response co ca "cell_id" ("1166-29537579") - lay nham la khong khop
        # cell nao va toan bo ket qua rong.
        resp = _FakeResponse({"data": [_ban_ghi(CELL_A, 5.0, cell_id="1166-29537579")]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )
        assert ket_qua[0]["cell_name"] == CELL_A
        assert ket_qua[0]["metrics"], "phai map duoc theo cellName, khong phu thuoc cell_id"

    async def test_time_bat_dau_bang_YYYY_MM_DD(self):
        # EvaluateCrUseCase._daily_averages_dict() cat 10 ky tu dau lam khoa ngay
        # - sai dinh dang la toan bo ngay bi loai khoi allowed_dates.
        resp = _FakeResponse({"data": [_ban_ghi(CELL_A, 4.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )
        assert ket_qua[0]["metrics"][0]["time"][:10] == "2026-08-14"


class TestCellThieu:
    async def test_cell_khong_co_trong_response_van_co_entry_metrics_rong(self):
        # API BO QUA cell khong co du lieu (gui 3 tra 2). KHONG duoc crash,
        # KHONG duoc lam lech thu tu cac cell con lai.
        resp = _FakeResponse({"data": [_ban_ghi(CELL_A, 5.0), _ban_ghi(CELL_C, 3.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A, CELL_B, CELL_C],
                datetime(2026, 8, 14, tzinfo=timezone.utc),
                datetime(2026, 8, 14, tzinfo=timezone.utc),
            )

        theo_ten = {r["cell_name"]: r["metrics"] for r in ket_qua}
        assert set(theo_ten) == {CELL_A, CELL_B, CELL_C}, "phai giu du 3 cell da hoi"
        assert theo_ten[CELL_A][0]["qoe"] == 5.0
        assert theo_ten[CELL_C][0]["qoe"] == 3.0
        assert theo_ten[CELL_B] == [], "cell khong co du lieu -> metrics rong"

    async def test_KHONG_zip_theo_thu_tu(self):
        # Bay chinh: response tra ve THEO THU TU KHAC voi thu tu gui di. Zip
        # theo index se gan diem cua CELL_C cho CELL_A.
        resp = _FakeResponse({"data": [_ban_ghi(CELL_C, 3.0), _ban_ghi(CELL_A, 5.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A, CELL_C],
                datetime(2026, 8, 14, tzinfo=timezone.utc),
                datetime(2026, 8, 14, tzinfo=timezone.utc),
            )
        theo_ten = {r["cell_name"]: r["metrics"][0]["qoe"] for r in ket_qua}
        assert theo_ten[CELL_A] == 5.0
        assert theo_ten[CELL_C] == 3.0

    async def test_data_rong_hoan_toan_khong_crash(self):
        # CEM tra 200 + data:[] khi ngay chua chot so lieu - BINH THUONG.
        resp = _FakeResponse({"message": "Success", "data": [], "response_code": "200"})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )
        assert ket_qua == [{"cell_name": CELL_A, "metrics": []}]

    async def test_cell_la_trong_response_bi_bo_qua(self):
        resp = _FakeResponse({"data": [_ban_ghi("4G-KHONG-HOI-HNI", 5.0), _ban_ghi(CELL_A, 4.0)]})
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            ket_qua = await adapter.get_qoe(
                [CELL_A], datetime(2026, 8, 14, tzinfo=timezone.utc), datetime(2026, 8, 14, tzinfo=timezone.utc)
            )
        assert {r["cell_name"] for r in ket_qua} == {CELL_A}


class TestNhieuNgay:
    async def test_7_ngay_gui_dung_7_request(self):
        # 1 request = 1 NGAY (rang buoc cua CEM).
        responses = [_FakeResponse({"data": [_ban_ghi(CELL_A, 5.0)]}) for _ in range(7)]
        client = _client_gia(responses)
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client):
            await adapter.get_qoe(
                [CELL_A],
                datetime(2026, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 8, 7, tzinfo=timezone.utc),  # 01..07 = 7 ngay (CA 2 dau mut)
            )
        assert client.post.await_count == 7

    async def test_moi_request_gui_ca_danh_sach_cell(self):
        responses = [_FakeResponse({"data": []}) for _ in range(3)]
        client = _client_gia(responses)
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client):
            await adapter.get_qoe(
                [CELL_A, CELL_B],
                datetime(2026, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )
        for call in client.post.await_args_list:
            assert call.kwargs["json"]["cells"] == [CELL_A, CELL_B]

    async def test_gom_diem_cua_nhieu_ngay_vao_1_cell(self):
        responses = [
            _FakeResponse({"data": [_ban_ghi(CELL_A, 5.0)]}),
            _FakeResponse({"data": [_ban_ghi(CELL_A, 3.0)]}),
            _FakeResponse({"data": []}),  # ngay giua thieu data - binh thuong
        ]
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia(responses)):
            ket_qua = await adapter.get_qoe(
                [CELL_A],
                datetime(2026, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )
        metrics = ket_qua[0]["metrics"]
        assert len(metrics) == 2, "chi 2/3 ngay co data"
        assert [m["time"][:10] for m in metrics] == ["2026-08-01", "2026-08-02"]
        assert [m["qoe"] for m in metrics] == [5.0, 3.0]

    async def test_ngay_gui_di_dung_dinh_dang_yyyyMMdd_va_dung_thu_tu(self):
        responses = [_FakeResponse({"data": []}) for _ in range(3)]
        client = _client_gia(responses)
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client):
            await adapter.get_qoe(
                [CELL_A],
                datetime(2026, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )
        ngay_da_gui = [c.kwargs["json"]["date"] for c in client.post.await_args_list]
        assert ngay_da_gui == ["20260801", "20260802", "20260803"]

    async def test_cell_names_rong_khong_goi_request_nao(self):
        client = _client_gia([])
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client):
            ket_qua = await adapter.get_qoe(
                [], datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 7, tzinfo=timezone.utc)
            )
        assert ket_qua == []
        assert client.post.await_count == 0


class TestLoi:
    async def test_http_401_raise_CemApiError_khong_retry(self):
        # 401 (sai credential) thu lai bao nhieu lan cung y het - phai nem luon.
        resp = _FakeResponse({}, status_code=401, text='{"message":"SecureCode is not valid!"}')
        client = _client_gia([resp])
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(CemApiError, match="401"):
                await adapter.get_qoe(
                    [CELL_A],
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                )
        assert client.post.await_count == 1, "KHONG duoc retry loi credential"

    async def test_http_500_raise_CemApiError(self):
        resp = _FakeResponse({}, status_code=500, text="Internal Server Error")
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=_client_gia([resp])):
            with pytest.raises(CemApiError):
                await adapter.get_qoe(
                    [CELL_A],
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                )

    async def test_timeout_duoc_retry_3_lan_roi_moi_raise(self):
        import httpx as _httpx

        client = _client_gia([_httpx.ConnectTimeout("timeout")] * 3)
        adapter = _adapter()
        with patch("httpx.AsyncClient", return_value=client), patch(
            "asyncio.sleep", new=AsyncMock()
        ):
            with pytest.raises(CemApiError, match="timeout"):
                await adapter.get_qoe(
                    [CELL_A],
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                    datetime(2026, 8, 14, tzinfo=timezone.utc),
                )
        assert client.post.await_count == 3
