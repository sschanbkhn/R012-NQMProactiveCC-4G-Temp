"""
Unit test nhom trang thai phieu + GET /phieu/excel + field moi cua GET /phieu
(19/10/2026, duyet PHAN B). MOCK ICrPhieuRepo, KHONG cham DB - so lieu that
doi chieu o tests/integration/test_phieu_excel_db.py.
"""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from openpyxl import load_workbook

import main
from adapters.excel.phieu_xlsx import TIEU_DE, gia_tri_dong, ve_excel_phieu
from domain.ports.outbound.repo_ports import ICrPhieuRepo
from domain.value_objects.ten_tinh import ten_tinh_tu_ma
from domain.value_objects.trang_thai_phieu import (
    CHO_XUAT_TAY,
    TRANG_THAI_CHO_XUAT_TAY,
    TRANG_THAI_LOC,
    nhom_trang_thai,
    ten_phuong_an,
)
from infrastructure.dependencies import get_cr_phieu_repo, get_qoe_snapshot_repo, get_qos_snapshot_repo


def _dong(**kw):
    r = {
        "id": 7, "phieu_id": "32166", "cell_name": "4G-A-HNI", "tram_cell_id": "111", "tram_cell_name": None,
        "ma_tinh": "HNI", "vendor": "NOKIA", "cr_session_id": 10707, "tram_tat_id": "114664",
        "tram_tat_name": "4G-TXN250M-HNI", "created_at": datetime(2026, 10, 12, 1, 5, tzinfo=timezone.utc),
        "gui_lan_cuoi": None, "so_lan_thu": 1, "trang_thai": "SUCCESS", "nguon_khong_dat": "QOS",
        "phuong_an": "2", "qos_gui": "2", "qoe_gui": "4", "so_chi_tieu_vp": "1", "noi_dung": "nd",
        "http_status": None, "ma_loi_cts": None, "error_message": None,
    }
    r.update(kw)
    return r


def test_nhom_trang_thai_va_phuong_an():
    assert nhom_trang_thai("SUCCESS") == "THANH_CONG" and nhom_trang_thai("FAILED") == "LOI"
    assert all(nhom_trang_thai(t) == CHO_XUAT_TAY for t in TRANG_THAI_CHO_XUAT_TAY)
    assert len(TRANG_THAI_CHO_XUAT_TAY) == 4 and "KHONG_XUAT_DA_CO_PHIEU_THANG" in TRANG_THAI_CHO_XUAT_TAY
    assert nhom_trang_thai("PENDING") is None and "PENDING" in TRANG_THAI_LOC
    assert (ten_phuong_an("1"), ten_phuong_an("2"), ten_phuong_an(None)) == ("He thong", "Hien truong", None)


def test_gia_tri_dong_gio_gmt7_ma_loi_va_ten_tram_du_phong():
    v = dict(zip(TIEU_DE, gia_tri_dong(_dong(trang_thai="FAILED", http_status="400", ma_loi_cts="E01"))))
    assert v["Tao luc"] == "12/10/2026 08:05"  # UTC 01:05 -> GMT+7
    assert v["Ma loi"] == "HTTP 400 / E01"
    assert v["Tram cua cell"] == "111"  # chua sync RIMS -> ghi ma
    assert (v["Nhom trang thai"], v["Phuong an"]) == ("LOI", "Hien truong")
    assert v["Tinh"] == (ten_tinh_tu_ma("HNI") or "HNI")  # ten tinh neu co, khong thi ma


def test_ve_excel_phieu_to_mau_ca_dong_theo_nhom():
    rows = [_dong(), _dong(id=8, trang_thai="FAILED"), _dong(id=9, trang_thai="KHONG_XUAT_THIEU_DU_LIEU",
                                                          phuong_an=None), _dong(id=10, trang_thai="PENDING")]
    wb = load_workbook(BytesIO(ve_excel_phieu(rows)))
    ws = wb["Phieu"]
    mau = [ws.cell(row=r, column=3).fill.start_color.rgb[-6:] for r in range(2, 6)]
    assert mau == ["E8F5E9", "FDECEA", "FFF2CC", "000000"]
    assert ws.cell(row=4, column=TIEU_DE.index("Phuong an") + 1).value is None
    assert wb.sheetnames == ["Phieu", "Chu giai"]
    chu_giai = " ".join(str(c.value) for row in wb["Chu giai"].iter_rows() for c in row)
    assert "KHAC TB trong file hau kiem" in chu_giai


class TestRouter:
    def _client(self, rows=None):
        repo = AsyncMock(spec=ICrPhieuRepo)
        repo.dong_excel.return_value = rows or []
        repo.list_phieu.return_value = rows or []
        repo.count_phieu.return_value = len(rows or [])
        snap = AsyncMock()
        snap.get_by_session_id.return_value = []
        main.app.dependency_overrides[get_cr_phieu_repo] = lambda: repo
        main.app.dependency_overrides[get_qos_snapshot_repo] = lambda: snap
        main.app.dependency_overrides[get_qoe_snapshot_repo] = lambda: snap
        return TestClient(main.app), repo

    def teardown_method(self):
        main.app.dependency_overrides.clear()

    def test_loc_da_co_phieu_thang_khong_con_422(self):
        client, _ = self._client()
        assert client.get("/api/v1/phieu?trang_thai=KHONG_XUAT_DA_CO_PHIEU_THANG").status_code == 200

    def test_list_tra_phuong_an_va_nhom(self):
        row = {"id": 1, "cr_session_id": 1, "cell_name": "C", "trang_thai": "SUCCESS",
               "request_payload": {"PhuongAnXuLyDuKien": "1"}}
        client, _ = self._client([row])
        item = client.get("/api/v1/phieu").json()["data"][0]
        assert (item["phuong_an"], item["nhom_trang_thai"]) == ("He thong", "THANH_CONG")

    def test_excel_ten_file_va_giao_khu_vuc_tinh(self):
        client, repo = self._client([_dong()])
        r = client.get("/api/v1/phieu/excel?tu_ngay=2026-10-01&den_ngay=2026-10-18"
                       "&khu_vuc=KV1&ma_tinh=HNI&ma_tinh=HCM&vendor=NOKIA&phuong_an=2")
        assert r.status_code == 200
        assert 'filename="phieu_20261001_den_20261018_' in r.headers["content-disposition"]
        kw = repo.dong_excel.call_args.kwargs
        assert kw["ma_tinh"] == ["HNI"] and kw["vendor"] == ["NOKIA"] and kw["phuong_an"] == ["2"]

    def test_list_loc_tram_cell_giong_excel(self):
        client, repo = self._client()
        qs = "khu_vuc=KV1&ma_tinh=HNI&ma_tinh=HCM&vendor=NOKIA&phuong_an=2"
        assert client.get(f"/api/v1/phieu?{qs}").status_code == 200
        client.get(f"/api/v1/phieu/excel?tu_ngay=2026-10-01&den_ngay=2026-10-18&{qs}")
        loc = {"ma_tinh": ["HNI"], "vendor": ["NOKIA"], "phuong_an": ["2"]}
        for goi in (repo.list_phieu, repo.count_phieu, repo.dong_excel):
            assert {k: goi.call_args.kwargs[k] for k in loc} == loc, goi

    def test_excel_thieu_ca_session_lan_ngay_422(self):
        client, _ = self._client()
        assert client.get("/api/v1/phieu/excel?tu_ngay=2026-10-01").status_code == 422
