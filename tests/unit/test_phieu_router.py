"""
Unit test cho api/routers/phieu.py:
- POST /phieu (KHOI 4a/5) - MOCK XuatPhieuUseCase, KHONG POST that len CTS/TTS.
- GET /phieu (UI lich su phieu, 11/08) - MOCK ICrPhieuRepo, KHONG cham DB.
  Query THAT tren DB nam o tests/integration/test_cr_phieu_repo.py.
Tu: yeu cau truc tiep user (KHOI 4a/5 SaveCellClm; UI lich su phieu 11/08).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from domain.errors import CrSessionNotFoundError, QoeDataInsufficientError, TramNotFoundError
from domain.ports.inbound.use_case_ports import IXuatPhieuUseCase, XuatPhieuResult
from domain.ports.outbound.repo_ports import ICrPhieuRepo
from infrastructure.dependencies import (
    get_cr_phieu_repo,
    get_qoe_snapshot_repo,
    get_qos_snapshot_repo,
    get_xuat_phieu_use_case,
)

SESSION_ID = 42
CELL_NAME = "4G-TEST-HNI"

# Tu dinh nghia (KHONG import api.routers.loc_ngay.GMT7): test loc ngay o duoi
# la KHOA HOP DONG - phai doi chieu voi mot moc VIET DOC LAP. Import chinh hang
# so ma code dang dung thi neu ai do sua offset thanh +8h, test van xanh.
_GMT7_PHIEU = timezone(timedelta(hours=7))


def _client_with_mock_use_case():
    mock_use_case = AsyncMock(spec=IXuatPhieuUseCase)
    main.app.dependency_overrides[get_xuat_phieu_use_case] = lambda: mock_use_case
    client = TestClient(main.app)
    return client, mock_use_case


def _clear_overrides():
    main.app.dependency_overrides.clear()


def _post(client):
    return client.post("/api/v1/phieu", json={"session_id": SESSION_ID, "cell_name": CELL_NAME})


def test_cell_khong_dat_200_kem_phieu_id():
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.return_value = XuatPhieuResult(
            cr_phieu_id=1,
            trang_thai="SUCCESS",
            phieu_id="TTS-000123",
            already_exists=False,
            # data = SO NGUYEN (id phieu that tren TTS) - hinh dang DA XAC NHAN
            # qua 1 lan POST that thanh cong, khong con la dict boc ngoai
            cts_response={"isError": False, "code": "200", "message": "OK", "data": 19177},
            db_save_warning=None,
        )

        resp = _post(client)

        assert resp.status_code == 200
        body = resp.json()
        assert body["trang_thai"] == "SUCCESS"
        assert body["phieu_id"] == "TTS-000123"
        assert body["cts_response"]["isError"] is False
        assert body["message"] is None

        # V2 (12/08): use case da bo dry_run - router goi DUNG 2 tham so, khong
        # con kwarg nao. (Goi execute() gio LUON la POST that.)
        call_args = mock_use_case.execute.call_args
        assert call_args.args == (SESSION_ID, CELL_NAME)
        assert call_args.kwargs == {}
    finally:
        _clear_overrides()


def test_cell_dat_tra_dat_khong_xuat():
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.return_value = XuatPhieuResult(
            cr_phieu_id=None, trang_thai="DAT_KHONG_XUAT", phieu_id=None, already_exists=False
        )

        resp = _post(client)

        assert resp.status_code == 200
        body = resp.json()
        assert body["trang_thai"] == "DAT_KHONG_XUAT"
        assert body["phieu_id"] is None
        assert body["cts_response"] is None
        assert "khong can xuat phieu" in body["message"]
    finally:
        _clear_overrides()


def test_cell_da_xuat_truoc_tra_phieu_cu():
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.return_value = XuatPhieuResult(
            cr_phieu_id=99, trang_thai="SUCCESS", phieu_id="TTS-OLD-001", already_exists=True
        )

        resp = _post(client)

        assert resp.status_code == 200
        body = resp.json()
        assert body["trang_thai"] == "SUCCESS"
        assert body["phieu_id"] == "TTS-OLD-001"
        assert "da duoc xuat phieu" in body["message"]
        # already_exists=True -> KHONG can echo cts_response (khong goi CTS lai)
        assert body["cts_response"] is None
    finally:
        _clear_overrides()


def test_thieu_du_lieu_qos_422():
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.side_effect = QoeDataInsufficientError(
            "Chua du du lieu QoS 7 ngay truoc/sau CR", cr_session_id=SESSION_ID, cell_name=CELL_NAME
        )

        resp = _post(client)

        assert resp.status_code == 422
        assert "chua du du lieu" in resp.json()["detail"].lower()
    finally:
        _clear_overrides()


def test_cts_tra_loi_iserror_van_200_khong_nuot_loi():
    # BUOC 1 dac ta - CTS tra ve isError=true (business-level failure) van la
    # response HOP LE nhan duoc, KHONG phai loi he thong -> endpoint van 200,
    # kem nguyen cts_response de FE hien DUNG message loi tu CTS.
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.return_value = XuatPhieuResult(
            cr_phieu_id=1,
            trang_thai="FAILED",
            phieu_id=None,
            already_exists=False,
            cts_response={"isError": True, "code": "400", "message": "TenCell khong hop le", "data": None},
            db_save_warning=None,
        )

        resp = _post(client)

        assert resp.status_code == 200
        body = resp.json()
        assert body["trang_thai"] == "FAILED"
        assert body["phieu_id"] is None
        assert body["cts_response"]["isError"] is True
        assert body["cts_response"]["message"] == "TenCell khong hop le"
    finally:
        _clear_overrides()


def test_db_save_warning_van_tra_phieu_id_da_post_thanh_cong():
    # BUOC 2 dac ta - loi ghi cr_phieu SAU KHI POST thanh cong KHONG duoc lam
    # mat phieu_id that da tao tren TTS, chi kem canh bao trong "message".
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.return_value = XuatPhieuResult(
            cr_phieu_id=1,
            trang_thai="SUCCESS",
            phieu_id="TTS-000999",
            already_exists=False,
            cts_response={"isError": False, "code": "200", "message": "OK", "data": 19177},
            db_save_warning="Da goi SaveCellClm xong (trang_thai=SUCCESS) nhung LUU DB THAT BAI: timeout",
        )

        resp = _post(client)

        assert resp.status_code == 200
        body = resp.json()
        assert body["phieu_id"] == "TTS-000999"  # KHONG bi mat du DB loi
        assert "LUU DB THAT BAI" in body["message"]
    finally:
        _clear_overrides()


def test_session_khong_ton_tai_404_bubble_global_handler():
    # KHONG try/except rieng trong router - DomainError khac bubble tu nhien
    # len global handler (da dang ky san 404 cho CR_SESSION_NOT_FOUND).
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.side_effect = CrSessionNotFoundError(
            f"cr_session id={SESSION_ID} khong ton tai", session_id=SESSION_ID
        )

        resp = _post(client)

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "CR_SESSION_NOT_FOUND"
    finally:
        _clear_overrides()


def test_tram_khong_xac_dinh_duoc_404_bubble_global_handler():
    client, mock_use_case = _client_with_mock_use_case()
    try:
        mock_use_case.execute.side_effect = TramNotFoundError(
            f"Khong xac dinh duoc tram cho cell_name={CELL_NAME}", cell_name=CELL_NAME
        )

        resp = _post(client)

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "TRAM_NOT_FOUND"
    finally:
        _clear_overrides()


# === GET /phieu (UI lich su phieu, 11/08) ===

_PHIEU_MAU = {
    "id": 7,
    "cr_session_id": SESSION_ID,
    "cell_name": CELL_NAME,
    "trang_thai": "SUCCESS",
    "phieu_id": "19207",
    "created_at": datetime(2026, 8, 11, 3, 20, tzinfo=timezone.utc),
    "request_payload": {"TenCell": CELL_NAME, "SoChiTieuVP": "1"},
    "response_body": {"isError": False, "code": "200", "message": "OK", "data": 19207},
    "error_message": None,
}


class TestGetPhieu:
    def _client_with_mock_repo(self, rows=None, total=0):
        mock_repo = AsyncMock(spec=ICrPhieuRepo)
        mock_repo.list_phieu.return_value = rows if rows is not None else []
        mock_repo.count_phieu.return_value = total
        main.app.dependency_overrides[get_cr_phieu_repo] = lambda: mock_repo
        # THEM 18/10/2026 - GET /phieu doc snapshot de gan vuot_luat_lam_tron;
        # mock rong (khong co snapshot -> co = False) de unit test khong cham DB.
        snap = AsyncMock()
        snap.get_by_session_id.return_value = []
        main.app.dependency_overrides[get_qos_snapshot_repo] = lambda: snap
        main.app.dependency_overrides[get_qoe_snapshot_repo] = lambda: snap
        return TestClient(main.app), mock_repo

    def test_khong_filter_tra_tat_ca_mac_dinh_page1_size20_created_at_desc(self):
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu")

            assert resp.status_code == 200
            args = mock_repo.list_phieu.call_args.args
            # (session_id, trang_thai, page, size, sort_by, order, q, tu_ngay,
            #  den_ngay, nguon) - nguon them 17082026 (QOS/QOE/CA_HAI)
            assert args == (None, None, 1, 20, None, "desc", None, None, None, None)
            # count_phieu dung CHUNG filter voi list_phieu (khong lech)
            assert mock_repo.count_phieu.call_args.args == (None, None, None, None, None, None)
        finally:
            _clear_overrides()

    def test_loc_session_id_va_trang_thai_truyen_dung_xuong_repo(self):
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?session_id=42&trang_thai=FAILED&page=2&size=5")

            assert resp.status_code == 200
            assert mock_repo.list_phieu.call_args.args == (
                42, "FAILED", 2, 5, None, "desc", None, None, None, None
            )
            assert mock_repo.count_phieu.call_args.args == (42, "FAILED", None, None, None, None)
        finally:
            _clear_overrides()

    def test_trang_thai_sai_422(self):
        # Literal whitelist - "DA_XUAT" khong phai gia tri hop le cua cot
        # trang_thai, PHAI bi tu choi o tang validate (khong im lang tra rong).
        client, _ = self._client_with_mock_repo()
        try:
            assert client.get("/api/v1/phieu?trang_thai=DA_XUAT").status_code == 422
            assert client.get("/api/v1/phieu?trang_thai=success").status_code == 422  # phan biet hoa/thuong
        finally:
            _clear_overrides()

    def test_v2_trang_thai_DRY_RUN_da_bi_bo_khoi_whitelist(self):
        # V2 (12/08): khong con dong nao mang trang_thai DRY_RUN -> hoi toi phai
        # bi tu choi o tang validate, khong tra ve 1 danh sach rong gay hieu nham
        # "co endpoint nhung khong co du lieu".
        client, _ = self._client_with_mock_repo()
        try:
            assert client.get("/api/v1/phieu?trang_thai=DRY_RUN").status_code == 422
        finally:
            _clear_overrides()

    def test_v4_loc_duoc_2_trang_thai_khong_xuat(self):
        # V4 (12/08) - muc dich cua viec ghi dong cr_phieu cho cell chua xuat la
        # de nguoi van hanh LOC RA duoc danh sach can lam tay.
        client, mock_repo = self._client_with_mock_repo()
        try:
            for gia_tri in ("KHONG_XUAT_VUOT_GIOI_HAN", "KHONG_XUAT_HET_LUOT_THU"):
                resp = client.get(f"/api/v1/phieu?trang_thai={gia_tri}")
                assert resp.status_code == 200, gia_tri
                assert mock_repo.list_phieu.call_args.args[1] == gia_tri
        finally:
            _clear_overrides()

    def test_sort_by_hop_le_va_ngoai_whitelist_422(self):
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?sort_by=cell_name&order=asc")
            assert resp.status_code == 200
            # [4:6] chu KHONG [4:] - tu 13/08 con 3 tham so loc (q/tu_ngay/
            # den_ngay) o SAU order, [4:] se nuot ca chung vao phep so sanh.
            assert mock_repo.list_phieu.call_args.args[4:6] == ("cell_name", "asc")

            # request_payload la cot THAT nhung khong co nghia khi sort (JSONB)
            assert client.get("/api/v1/phieu?sort_by=request_payload").status_code == 422
            assert client.get("/api/v1/phieu?sort_by=khong_ton_tai").status_code == 422
            assert client.get("/api/v1/phieu?sort_by=id&order=random").status_code == 422
        finally:
            _clear_overrides()

    def test_page_size_ngoai_gioi_han_422(self):
        client, _ = self._client_with_mock_repo()
        try:
            assert client.get("/api/v1/phieu?page=0").status_code == 422
            assert client.get("/api/v1/phieu?size=0").status_code == 422
            assert client.get("/api/v1/phieu?size=201").status_code == 422
        finally:
            _clear_overrides()

    def test_response_co_total_va_chi_tiet_cho_modal(self):
        # total lay tu count_phieu() (tong toan bo), KHONG phai len(data)
        client, _ = self._client_with_mock_repo(rows=[_PHIEU_MAU], total=137)
        try:
            resp = client.get("/api/v1/phieu?size=1")

            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 137
            assert body["page"] == 1
            assert body["size"] == 1
            assert len(body["data"]) == 1

            item = body["data"][0]
            assert item["phieu_id"] == "19207"
            assert item["trang_thai"] == "SUCCESS"
            # created_at co "Z" (timestamptz - C1.4-fix9/fix10)
            assert item["created_at"].endswith("Z")
            # chi tiet di kem list -> modal FE khong can goi them endpoint
            assert item["request_payload"]["SoChiTieuVP"] == "1"
            assert item["response_body"]["data"] == 19207
            assert item["error_message"] is None
        finally:
            _clear_overrides()

    def test_khong_co_phieu_tra_rong_khong_loi(self):
        client, _ = self._client_with_mock_repo(rows=[], total=0)
        try:
            resp = client.get("/api/v1/phieu?session_id=999999")

            assert resp.status_code == 200
            assert resp.json() == {"total": 0, "page": 1, "size": 20, "data": []}
        finally:
            _clear_overrides()


    # === 13/08: tim kiem (q) + loc khoang ngay ===

    def test_q_truyen_nguyen_van_xuong_repo(self):
        # q di THANG xuong repo (khong bi router cat/upper/lower) - viec khop
        # gan dung la cua tang SQL, router chi chuyen tiep.
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?q=SSN104")

            assert resp.status_code == 200
            assert mock_repo.list_phieu.call_args.args[6] == "SSN104"
            assert mock_repo.count_phieu.call_args.args[2] == "SSN104"
        finally:
            _clear_overrides()

    def test_loc_ngay_quy_doi_GMT7_va_cong_1_ngay_vao_den_ngay(self):
        # KHOA HOP DONG MUI GIO o tang router: den_ngay 20/08 phai thanh moc
        # 00:00 ngay 21/08 GMT+7, neu khong dong tao luc 09:30 ngay 20/08 se bi
        # loai khoi ket qua (loi im lang - man hinh van co du lieu).
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?tu_ngay=2026-08-15&den_ngay=2026-08-20")

            assert resp.status_code == 200
            tu_moc, den_moc = mock_repo.list_phieu.call_args.args[7:9]
            assert tu_moc == datetime(2026, 8, 15, tzinfo=_GMT7_PHIEU)
            assert den_moc == datetime(2026, 8, 21, tzinfo=_GMT7_PHIEU)
            # count_phieu nhan Y HET cap moc - lech thi total sai so trang
            assert mock_repo.count_phieu.call_args.args[3:5] == (tu_moc, den_moc)
        finally:
            _clear_overrides()

    def test_chi_truyen_1_dau_mut_van_hop_le(self):
        # 2 dau mut DOC LAP: "tu 01/08 den nay" la cach loc tu nhien, khong duoc
        # ep FE bia not con lai.
        client, mock_repo = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?tu_ngay=2026-08-01")

            assert resp.status_code == 200
            tu_moc, den_moc = mock_repo.list_phieu.call_args.args[7:9]
            assert tu_moc == datetime(2026, 8, 1, tzinfo=_GMT7_PHIEU)
            assert den_moc is None
        finally:
            _clear_overrides()

    def test_tu_ngay_lon_hon_den_ngay_tra_422(self):
        # Khoang ngay nguoc la LOI CUA REQUEST - tra rong se lam nguoi dung
        # tuong "khong co du lieu" va di tim nham cho.
        client, _ = self._client_with_mock_repo()
        try:
            resp = client.get("/api/v1/phieu?tu_ngay=2026-08-20&den_ngay=2026-08-15")

            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_ngay_sai_dinh_dang_tra_422(self):
        client, _ = self._client_with_mock_repo()
        try:
            assert client.get("/api/v1/phieu?tu_ngay=20-08-2026").status_code == 422
        finally:
            _clear_overrides()
