"""
GET /phieu/excel + dashboard cho xuat tay tren DU LIEU THAT (19/10/2026).
CHI DOC - khong insert/update (yeu cau user: KHONG ghi DB).

So mong doi KHONG go cung (DB thay doi theo ngay): doi chieu voi SELECT dem
truc tiep tren cr_phieu. Luc viet (19/10/2026): SUCCESS 145, FAILED 5,
KHONG_XUAT_* 28, tong 178.
"""

from collections import Counter
from io import BytesIO

import httpx
from openpyxl import load_workbook
from sqlalchemy import text

import main
from adapters.excel.phieu_xlsx import TIEU_DE
from domain.value_objects.trang_thai_phieu import TRANG_THAI_CHO_XUAT_TAY
from infrastructure.db import AsyncSessionLocal

_S = "system_nsn_nqmproactivecc"
# Khoang rong bao trum toan bo du lieu that.
_TU, _DEN = "2025-01-01", "2026-12-31"


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")


async def _dem_db(sql: str) -> dict:
    async with AsyncSessionLocal() as s:
        return {r[0]: r[1] for r in (await s.execute(text(sql))).all()}


async def test_excel_phieu_dem_theo_trang_thai_khop_select():
    async with _client() as c:
        res = await c.get(f"/api/v1/phieu/excel?tu_ngay={_TU}&den_ngay={_DEN}")
    assert res.status_code == 200
    assert 'filename="phieu_20250101_den_20261231_' in res.headers["content-disposition"]

    ws = load_workbook(BytesIO(res.content))["Phieu"]
    assert [c.value for c in ws[1]] == TIEU_DE
    i_tt = TIEU_DE.index("Trang thai")
    excel = Counter(r[i_tt] for r in ws.iter_rows(min_row=2, values_only=True))

    db = await _dem_db(f"SELECT trang_thai, count(*) FROM {_S}.cr_phieu WHERE deleted_at IS NULL GROUP BY 1")
    assert dict(excel) == db
    cho = sum(n for t, n in db.items() if t in TRANG_THAI_CHO_XUAT_TAY)
    print(f"SUCCESS={db.get('SUCCESS')} FAILED={db.get('FAILED')} CHO_XUAT_TAY={cho}")


async def test_excel_phieu_loc_phuong_an_va_vendor_theo_tram_cell():
    async with _client() as c:
        res = await c.get(f"/api/v1/phieu/excel?tu_ngay={_TU}&den_ngay={_DEN}&phuong_an=1&vendor=NOKIA")
    rows = list(load_workbook(BytesIO(res.content))["Phieu"].iter_rows(min_row=2, values_only=True))
    db = await _dem_db(f"""
        SELECT 'n', count(*) FROM {_S}.cr_phieu p
        JOIN {_S}.cr_affected_cells a ON a.cr_session_id = p.cr_session_id AND a.cell_name = p.cell_name
        JOIN {_S}.tram t ON t.tram_id = a.tram_id
        WHERE p.deleted_at IS NULL AND p.request_payload->>'PhuongAnXuLyDuKien' = '1'
          AND upper(trim(t.ten_thiet_bi)) = 'NOKIA'""")
    assert len(rows) == db.get("n", 0)
    assert all(r[TIEU_DE.index("Phuong an")] == "He thong" and r[TIEU_DE.index("Vendor")] == "NOKIA" for r in rows)


async def test_danh_sach_va_excel_cung_bo_loc_cung_so_dong():
    # Cung bo loc -> total cua GET /phieu = so dong /phieu/excel (cung
    # _filter_conditions). Gom ca to hop giao rong (KV2 x HNI -> 0 dong).
    bo_loc = [
        "",
        "&vendor=NOKIA",
        "&phuong_an=2",
        "&khu_vuc=KV1",
        "&ma_tinh=HNI&vendor=NOKIA&phuong_an=1",
        "&khu_vuc=KV2&ma_tinh=HNI",
        "&trang_thai=KHONG_XUAT_DA_CO_PHIEU_THANG",
        "&nguon=QOS&vendor=ERICSSON&vendor=NOKIA",
    ]
    async with _client() as c:
        for bl in bo_loc:
            qs = f"tu_ngay={_TU}&den_ngay={_DEN}{bl}"
            lst = (await c.get(f"/api/v1/phieu?{qs}&size=1")).json()
            xl = await c.get(f"/api/v1/phieu/excel?{qs}")
            n_excel = sum(1 for _ in load_workbook(BytesIO(xl.content))["Phieu"].iter_rows(min_row=2))
            assert lst["total"] == n_excel, bl
            print(f"[{bl or 'khong loc'}] {n_excel}")


async def test_lich_su_cr_cho_xuat_tay_nhu_cu():
    # Lich su CR doi sang danh sach chung - tong so_cell_cho_xuat_tay moi
    # session phai = cach dem cu LIKE 'KHONG_XUAT_%'.
    tong, trang = 0, 1
    async with _client() as c:
        while True:
            j = (await c.get(f"/api/v1/sessions?page={trang}&size=200")).json()
            tong += sum(s.get("so_cell_cho_xuat_tay") or 0 for s in j["data"])
            if trang * 200 >= j["total"]:
                break
            trang += 1
    db = await _dem_db(f"""SELECT 'n', count(*) FROM {_S}.cr_phieu
        WHERE deleted_at IS NULL AND trang_thai LIKE 'KHONG_XUAT_%'""")
    assert tong == db["n"]
    print(f"lich su CR cho_xuat_tay={tong}")


async def test_dashboard_cho_xuat_tay_dung_danh_sach_chung():
    async with _client() as c:
        phieu = (await c.get(f"/api/v1/dashboard/tong-quan?tu_ngay={_TU}&den_ngay={_DEN}")).json()["phieu"]
    # CACH DEM CU (LIKE 'KHONG_XUAT_%', session trong khoang) phai ra CUNG so.
    db = await _dem_db(f"""
        SELECT 'n', count(*) FROM {_S}.cr_phieu p JOIN {_S}.cr_session cs ON cs.id = p.cr_session_id
        WHERE p.deleted_at IS NULL AND p.trang_thai LIKE 'KHONG_XUAT_%'
          AND timezone('Asia/Ho_Chi_Minh', cs.created_at)::date BETWEEN '{_TU}' AND '{_DEN}'""")
    assert phieu["cho_xuat_tay"] == db["n"]
    print(f"dashboard cho_xuat_tay={phieu['cho_xuat_tay']}")
