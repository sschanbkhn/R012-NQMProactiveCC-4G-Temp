"""
Unit test cho sort_by/order whitelist (Literal) o router - GET /sessions VA
GET /stations (22072026, xac nhan voi user). MOCK use case/repo qua FastAPI
dependency_overrides, KHONG goi DB that - chi kiem tra tang validate cua
FastAPI/Pydantic (422 khi sort_by ngoai whitelist).
"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from domain.ports.inbound.use_case_ports import IGetSessionsUseCase
from domain.ports.outbound.repo_ports import IEnodebRepo, Page
from infrastructure.dependencies import get_enodeb_repo, get_sessions_use_case


def _clear_overrides():
    main.app.dependency_overrides.clear()


class TestSessionsSortWhitelist:
    def _client_with_mock(self):
        mock_use_case = AsyncMock(spec=IGetSessionsUseCase)
        mock_use_case.execute.return_value = Page(items=[], total=0)
        main.app.dependency_overrides[get_sessions_use_case] = lambda: mock_use_case
        return TestClient(main.app), mock_use_case

    def test_sort_by_hop_le_200(self):
        client, mock_use_case = self._client_with_mock()
        try:
            resp = client.get("/api/v1/sessions?sort_by=executed_at&order=asc")
            assert resp.status_code == 200
            filters = mock_use_case.execute.call_args.args[0]
            assert filters.sort_by == "executed_at"
            assert filters.order == "asc"
        finally:
            _clear_overrides()

    def test_sort_by_ngoai_whitelist_422(self):
        # "qoe_before" la cot THAT tren cr_session nhung KHONG nam trong
        # whitelist (BUSINESS_RULES khong coi day la field can sort UI) -
        # phai bi tu choi, KHONG duoc im lang bo qua hay crash 500.
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/sessions?sort_by=qoe_before")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_sort_by_ten_cot_khong_ton_tai_422(self):
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/sessions?sort_by=khong_ton_tai_cot_nay")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_order_ngoai_asc_desc_422(self):
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/sessions?sort_by=id&order=random")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khong_truyen_sort_by_van_200_khong_regression(self):
        client, mock_use_case = self._client_with_mock()
        try:
            resp = client.get("/api/v1/sessions")
            assert resp.status_code == 200
            filters = mock_use_case.execute.call_args.args[0]
            assert filters.sort_by is None
            assert filters.order == "desc"  # default
        finally:
            _clear_overrides()


class TestStationsSortWhitelist:
    def _client_with_mock(self):
        mock_repo = AsyncMock(spec=IEnodebRepo)
        mock_repo.count_stations.return_value = 0
        mock_repo.find_stations.return_value = []
        main.app.dependency_overrides[get_enodeb_repo] = lambda: mock_repo
        return TestClient(main.app), mock_repo

    def test_sort_by_hop_le_200(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?sort_by=tram_name&order=asc")
            assert resp.status_code == 200
            call_args = mock_repo.find_stations.call_args.args
            assert call_args[4] == "tram_name"
            assert call_args[5] == "asc"
        finally:
            _clear_overrides()

    def test_sort_by_id_ngoai_whitelist_422(self):
        # "id" hop le cho /sessions nhung KHONG hop le cho /stations (whitelist
        # rieng biet moi endpoint - Tram khong co PK "id" y nghia nghiep vu
        # nhu cr_session.id, tram_id moi la khoa nghiep vu).
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?sort_by=id")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_sort_by_trang_thai_ngoai_whitelist_422(self):
        # trang_thai la cot THAT tren Tram nhung khong nam trong whitelist
        # duoc liet ke cho /stations - van phai 422, khong duoc "linh dong"
        # cho qua vi cot co ton tai.
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?sort_by=trang_thai")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khong_truyen_sort_by_van_200_khong_regression(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations")
            assert resp.status_code == 200
            call_args = mock_repo.find_stations.call_args.args
            assert call_args[4] is None
            assert call_args[5] == "desc"  # default
        finally:
            _clear_overrides()


class TestStationsVendorFilter:
    # THEM 04/10/2026 (yeu cau truc tiep user) - loc vendor cho GET /stations.
    # Dung CHUNG mock pattern voi TestStationsSortWhitelist o tren (MOCK repo,
    # KHONG goi DB that - chi kiem tang validate Literal cua FastAPI/Pydantic).
    def _client_with_mock(self):
        mock_repo = AsyncMock(spec=IEnodebRepo)
        mock_repo.count_stations.return_value = 0
        mock_repo.find_stations.return_value = []
        main.app.dependency_overrides[get_enodeb_repo] = lambda: mock_repo
        return TestClient(main.app), mock_repo

    def test_1_vendor_truyen_dung_xuong_repo(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?vendor=NOKIA")
            assert resp.status_code == 200
            # vendor la tham so CUOI (them 04/10/2026, vi tri 6 - sau order)
            # cua find_stations(q, status, offset, size, sort_by, order, vendor).
            assert mock_repo.find_stations.call_args.args[6] == ["NOKIA"]
            assert mock_repo.count_stations.call_args.args[2] == ["NOKIA"]
        finally:
            _clear_overrides()

    def test_2_vendor_lap_lai_tham_so_truyen_dung_list(self):
        # ?vendor=NOKIA&vendor=HUAWEI - quy uoc FastAPI cho "1 tham so nhieu
        # gia tri" (KHONG phai "NOKIA,HUAWEI" 1 chuoi phan cach dau phay).
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?vendor=NOKIA&vendor=HUAWEI")
            assert resp.status_code == 200
            assert mock_repo.find_stations.call_args.args[6] == ["NOKIA", "HUAWEI"]
        finally:
            _clear_overrides()

    def test_vendor_gia_tri_sai_422(self):
        # "SAMSUNG" khong nam trong 4 vendor THAT dang chay tren mang (khao
        # sat 04/10/2026: NOKIA/ERICSSON/HUAWEI/ZTE) - phai bi tu choi o tang
        # validate, KHONG duoc tham gia truy van roi am tham tra danh sach rong.
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?vendor=SAMSUNG")
            assert resp.status_code == 422
            mock_repo.find_stations.assert_not_called()
        finally:
            _clear_overrides()

    def test_vendor_chu_thuong_422(self):
        # Literal phan biet hoa/thuong - "nokia" KHONG tu dong duoc chuan hoa
        # thanh "NOKIA" o tang validate nay (chuan hoa la viec cua
        # chuan_hoa_vendor(), dung cho HIEN THI, khong phai cho THAM SO loc).
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?vendor=nokia")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khong_truyen_vendor_khong_loc(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations")
            assert resp.status_code == 200
            assert mock_repo.find_stations.call_args.args[6] is None
            assert mock_repo.count_stations.call_args.args[2] is None
        finally:
            _clear_overrides()


class TestStationsKhuVucFilter:
    # THEM 04/10/2026 (yeu cau truc tiep user) - loc khu_vuc (KV1/KV2/KV3) cho
    # GET /stations. Dung CHUNG mock pattern voi TestStationsVendorFilter o
    # tren - KHONG goi DB that, chi kiem tang validate Literal.
    def _client_with_mock(self):
        mock_repo = AsyncMock(spec=IEnodebRepo)
        mock_repo.count_stations.return_value = 0
        mock_repo.find_stations.return_value = []
        main.app.dependency_overrides[get_enodeb_repo] = lambda: mock_repo
        return TestClient(main.app), mock_repo

    def test_1_khu_vuc_truyen_dung_xuong_repo(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?khu_vuc=KV1")
            assert resp.status_code == 200
            # khu_vuc la tham so CUOI (them 04/10/2026, vi tri 7 - sau vendor)
            # cua find_stations(q, status, offset, size, sort_by, order, vendor, khu_vuc).
            assert mock_repo.find_stations.call_args.args[7] == ["KV1"]
            assert mock_repo.count_stations.call_args.args[3] == ["KV1"]
        finally:
            _clear_overrides()

    def test_2_khu_vuc_lap_lai_tham_so_truyen_dung_list(self):
        # ?khu_vuc=KV1&khu_vuc=KV3 - cung quy uoc "1 tham so nhieu gia tri"
        # voi vendor o tren.
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?khu_vuc=KV1&khu_vuc=KV3")
            assert resp.status_code == 200
            assert mock_repo.find_stations.call_args.args[7] == ["KV1", "KV3"]
        finally:
            _clear_overrides()

    def test_khu_vuc_gia_tri_sai_422(self):
        # "KV4" khong nam trong 3 KV da xac nhan (domain/value_objects/khu_vuc.py)
        # - phai bi tu choi o tang validate, khong duoc am tham tra danh sach rong.
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?khu_vuc=KV4")
            assert resp.status_code == 422
            mock_repo.find_stations.assert_not_called()
        finally:
            _clear_overrides()

    def test_khu_vuc_chu_thuong_422(self):
        client, _ = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations?khu_vuc=kv1")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_khong_truyen_khu_vuc_khong_loc(self):
        client, mock_repo = self._client_with_mock()
        try:
            resp = client.get("/api/v1/stations")
            assert resp.status_code == 200
            assert mock_repo.find_stations.call_args.args[7] is None
            assert mock_repo.count_stations.call_args.args[3] is None
        finally:
            _clear_overrides()


class TestStationsMapEndpoint:
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - GET /stations/map?ma_tinh=...
    # MOCK IEnodebRepo.get_all_with_coords() (KHONG goi DB that), domain
    # phan_loai_toa_do() la HAM THUAN nen chay THAT (khong mock) tren du lieu
    # gia lap - cung triet ly voi cac test unit khac trong file nay.
    def _client_with_mock(self, rows):
        mock_repo = AsyncMock(spec=IEnodebRepo)
        mock_repo.get_all_with_coords.return_value = rows
        main.app.dependency_overrides[get_enodeb_repo] = lambda: mock_repo
        return TestClient(main.app), mock_repo

    def test_tra_dang_gon_cot_rows_loc_dung_tinh(self):
        rows = [
            {"tram_id": "1", "tram_name": "4G-AAA001M-HNI", "latitude": 21.0, "longitude": 105.8, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
            {"tram_id": "2", "tram_name": "4G-BBB001M-HPG", "latitude": 20.8, "longitude": 106.6, "ten_thiet_bi": "HUAWEI", "ma_tinh": "HPG"},
        ]
        client, _ = self._client_with_mock(rows)
        try:
            resp = client.get("/api/v1/stations/map?ma_tinh=HNI")
            assert resp.status_code == 200
            body = resp.json()
            assert body["columns"] == ["tram_id", "ten", "lat", "lon", "vendor", "toa_do_dung_chung", "loai_tram"]
            assert len(body["rows"]) == 1  # chi HNI, bo HPG
            # loai_tram THEM (11-12/10/2026) - "AAA001M" -> chu cai loai "M" -> MACRO.
            assert body["rows"][0] == ["1", "4G-AAA001M-HNI", 21.0, 105.8, "NOKIA", False, "MACRO"]
        finally:
            _clear_overrides()

    def test_tram_trung_toa_do_khac_so_site_co_toa_do_dung_chung_true(self):
        # 2 tram CUNG toa do nhung KHAC so site (001 vs 002) -> ca 2 thanh
        # TOA_DO_DUNG_CHUNG (xem domain/services/ho_delaunay.py::phan_loai_toa_do()).
        rows = [
            {"tram_id": "1", "tram_name": "4G-AAA001M-HNI", "latitude": 21.0, "longitude": 105.8, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
            {"tram_id": "2", "tram_name": "4G-AAA002M-HNI", "latitude": 21.0, "longitude": 105.8, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
        ]
        client, _ = self._client_with_mock(rows)
        try:
            resp = client.get("/api/v1/stations/map?ma_tinh=HNI")
            assert resp.status_code == 200
            rows_tra_ve = resp.json()["rows"]
            assert all(r[5] is True for r in rows_tra_ve)
        finally:
            _clear_overrides()

    def test_loai_tram_dung_cho_moi_nhom(self):
        # THEM 11-12/10/2026 (yeu cau truc tiep user) - cot loai_tram o cuoi
        # (index 6), xem domain/services/loai_tram.py.
        rows = [
            {"tram_id": "1", "tram_name": "4G-AAA001M-HNI", "latitude": 21.0, "longitude": 105.8, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
            {"tram_id": "2", "tram_name": "4G-AAA002F-HNI", "latitude": 21.1, "longitude": 105.9, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
            {"tram_id": "3", "tram_name": "4G-AAA003S-HNI", "latitude": 21.2, "longitude": 106.0, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
            {"tram_id": "4", "tram_name": "TEN LA KHONG DUNG MAU", "latitude": 21.3, "longitude": 106.1, "ten_thiet_bi": "NOKIA", "ma_tinh": "HNI"},
        ]
        client, _ = self._client_with_mock(rows)
        try:
            resp = client.get("/api/v1/stations/map?ma_tinh=HNI")
            loai_theo_tram = {r[0]: r[6] for r in resp.json()["rows"]}
            assert loai_theo_tram == {"1": "MACRO", "2": "IBS", "3": "SMALL_CELL", "4": "KHAC"}
        finally:
            _clear_overrides()

    def test_thieu_ma_tinh_422(self):
        client, _ = self._client_with_mock([])
        try:
            resp = client.get("/api/v1/stations/map")
            assert resp.status_code == 422
        finally:
            _clear_overrides()

    def test_ma_tinh_sai_do_dai_422(self):
        client, _ = self._client_with_mock([])
        try:
            resp = client.get("/api/v1/stations/map?ma_tinh=HN")
            assert resp.status_code == 422
        finally:
            _clear_overrides()
