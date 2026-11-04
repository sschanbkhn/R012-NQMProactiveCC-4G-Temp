"""
Unit test cho GET /sessions - 6 truong tien trinh o tang ROUTER (16082026).
MOCK use case qua dependency_overrides, KHONG goi DB.

Kiem 2 thu router chiu trach nhiem:
  1. Anh xa DU 6 truong ra JSON (thieu 1 truong la FE mat 1 o tren man hinh).
  2. Validate query param buoc/qua_han truoc khi xuong duoi.
Con LOGIC tinh 6 truong da co test rieng o test_get_sessions_use_case.py.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from application.get_sessions_use_case import SessionTienTrinh
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.inbound.use_case_ports import IGetSessionsUseCase
from domain.ports.outbound.repo_ports import Page
from infrastructure.dependencies import get_sessions_use_case


def _row() -> SessionTienTrinh:
    return SessionTienTrinh(
        session=CrSession(
            id=42,
            tram_id="110548",
            action="shutdown",
            status=CrStatus.DONE,
            plan_name="plan_test",
            executed_at=datetime(2026, 8, 1, 2, 15, tzinfo=timezone.utc),
            xuat_phieu_at=None,
            so_cell_anh_huong=17,
            so_phieu_da_xuat=4,
            so_cell_cho_xuat_tay=2,
        ),
        ngay_du_kien_xuat_phieu=date(2026, 8, 9),
        con_bao_nhieu_ngay=-3,
        buoc_hien_tai=2,
    )


def _client(items=None):
    uc = AsyncMock(spec=IGetSessionsUseCase)
    uc.execute.return_value = Page(items=items if items is not None else [_row()], total=1)
    main.app.dependency_overrides[get_sessions_use_case] = lambda: uc
    return TestClient(main.app), uc


def test_tra_du_6_truong_tien_trinh():
    client, _ = _client()
    try:
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        item = resp.json()["data"][0]

        assert item["so_cell_anh_huong"] == 17
        assert item["so_phieu_da_xuat"] == 4
        assert item["so_cell_cho_xuat_tay"] == 2
        assert item["ngay_du_kien_xuat_phieu"] == "2026-08-09"
        assert item["con_bao_nhieu_ngay"] == -3  # AM = qua han
        assert item["buoc_hien_tai"] == 2
    finally:
        main.app.dependency_overrides.clear()


def test_giu_nguyen_cac_truong_cu_khong_regression():
    client, _ = _client()
    try:
        item = client.get("/api/v1/sessions").json()["data"][0]
        assert item["id"] == 42
        assert item["tram_id"] == "110548"
        assert item["status"] == "DONE"
    finally:
        main.app.dependency_overrides.clear()


def test_buoc_va_qua_han_duoc_chuyen_xuong_use_case():
    client, uc = _client()
    try:
        resp = client.get("/api/v1/sessions?buoc=4&qua_han=true")
        assert resp.status_code == 200
        filters = uc.execute.call_args.args[0]
        assert filters.buoc == 4
        assert filters.qua_han is True
    finally:
        main.app.dependency_overrides.clear()


def test_buoc_3_bi_tu_choi_422():
    # Buoc 3 la trang thai thoang qua, KHONG session nao o do. Cho qua se tra
    # ve danh sach rong - nguoi dung tuong "khong con session nao dang danh
    # gia" thay vi hieu la buoc nay khong ton tai.
    client, _ = _client()
    try:
        assert client.get("/api/v1/sessions?buoc=3").status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_buoc_ngoai_1_2_4_bi_tu_choi_422():
    client, _ = _client()
    try:
        assert client.get("/api/v1/sessions?buoc=9").status_code == 422
        assert client.get("/api/v1/sessions?buoc=abc").status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_khong_truyen_buoc_qua_han_van_200():
    # Khong regression cho FE cu (chua biet 2 param nay).
    client, uc = _client()
    try:
        assert client.get("/api/v1/sessions").status_code == 200
        filters = uc.execute.call_args.args[0]
        assert filters.buoc is None
        assert filters.qua_han is False
    finally:
        main.app.dependency_overrides.clear()


def test_ngay_du_kien_null_ra_json_null():
    row = _row()
    row.ngay_du_kien_xuat_phieu = None
    row.con_bao_nhieu_ngay = None
    client, _ = _client(items=[row])
    try:
        item = client.get("/api/v1/sessions").json()["data"][0]
        assert item["ngay_du_kien_xuat_phieu"] is None
        # None chu KHONG phai 0 - 0 mang nghia "dung hom nay".
        assert item["con_bao_nhieu_ngay"] is None
    finally:
        main.app.dependency_overrides.clear()
