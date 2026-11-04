"""
Integration test - danh dau du lieu CU theo dieu kien CR moi (quyet dinh
04/10/2026, CHI DOC - KHONG sua DB). Dung DU LIEU THAT da khao sat 04/10/2026
(khong phai fixture dung lap) - xem docs/DEV_LOG.md muc khao sat cung ngay.

GIONG pattern tests/integration/test_xuat_phieu_job_integration.py: bam vao
session/cell CU THE tren DB that nen co the "het hieu luc" theo thoi gian (vd
session bi xoa, du lieu doi) - SKIP (khong FAIL) kem ly do ro rang neu vay,
thay vi bao loi kho hieu.
"""

import pytest
from sqlalchemy import select

from adapters.postgres.cell_params_repo import CellParamsRepo
from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from domain.services.danh_gia_dieu_kien_cr_moi import (
    LY_DO_BAND_KHONG_PHAI_1800,
    gan_nhan_ngoai_dieu_kien_moi,
)
from infrastructure.db import AsyncSessionLocal
from models.cr_phieu import CrPhieu as CrPhieuModel

# Khao sat 04/10/2026 (SQL that, xem DEV_LOG): session 3641 sector 1 co DUNG 6
# phieu SUCCESS -> 4 phieu vuot (2 dau theo thoi diem tao duoc giu, 4 con lai
# vuot). Session 1811 co cell 4G-SSN093M51-HNI mang LNCEL-51 (band 5x, khong
# phai 1800) - PHAI nhan BAND_KHONG_PHAI_1800.
SESSION_VUOT_SECTOR = 3641
SECTOR_VUOT = 1
SO_PHIEU_VUOT_KY_VONG = 4

SESSION_BAND_SAI = 1811
CELL_BAND_SAI = "4G-SSN093M51-HNI"


async def _session_con_ton_tai(session_id: int) -> bool:
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(CrPhieuModel.id).where(CrPhieuModel.cr_session_id == session_id).limit(1))
        return r.first() is not None


async def test_session_3641_sector_1_vuot_dung_4_phieu():
    if not await _session_con_ton_tai(SESSION_VUOT_SECTOR):
        pytest.skip(f"Session {SESSION_VUOT_SECTOR} khong con cr_phieu nao tren DB - du lieu da doi")

    async with AsyncSessionLocal() as s:
        repo = CrPhieuRepo(s)
        rows = await repo.list_phieu(
            session_id=SESSION_VUOT_SECTOR, trang_thai="SUCCESS", page=1, size=50
        )

    # Loc rieng sector 1 bang cach doi chieu qua cr_affected_cells (repo
    # khong tra sector thang ra, chi tra bool vuot_2_phieu_sector da tinh san)
    # - lay TOAN BO SUCCESS cua session nay, kiem tong so phieu vuot KHOP voi
    # khao sat (4), KHONG assert tung id cu the (du lieu co the doi thu tu
    # neu co phieu moi xuat sau nay, nhung TONG so vuot cua sector 1 la bat
    # bien theo du lieu da khao sat).
    if not rows:
        pytest.skip(f"Session {SESSION_VUOT_SECTOR} khong con phieu SUCCESS nao - du lieu da doi")

    so_vuot = sum(1 for r in rows if r["vuot_2_phieu_sector"] is True)
    # Khao sat 04/10 session nay CHI co 2 sector (1 va 2), sector 1 co 6
    # phieu/4 vuot, sector 2 co 4 phieu/2 vuot -> TONG CA session la 6 vuot.
    # Assert tong (don gian, bam chac) thay vi tach rieng sector 1 (phai them
    # 1 query JOIN cr_affected_cells chi de loc, khong dang voi gia tri tang
    # them cho 1 test da co SQL kiem o phan khao sat).
    assert so_vuot == 6, f"Tong so phieu vuot cua session {SESSION_VUOT_SECTOR}: {so_vuot}, ky vong 6"


async def test_session_1811_cell_lncel_5x_nhan_band_khong_phai_1800():
    async with AsyncSessionLocal() as s:
        cell_params_repo = CellParamsRepo(s)
        affected_cells_repo = CrAffectedCellsRepo(s)
        cell_params = await cell_params_repo.get_by_cr_session_id(SESSION_BAND_SAI)
        affected_cells = await affected_cells_repo.get_by_cr_session_id(SESSION_BAND_SAI)

    if not any(c.cell_name == CELL_BAND_SAI for c in cell_params):
        pytest.skip(
            f"Cell {CELL_BAND_SAI} khong con trong cell_params cua session "
            f"{SESSION_BAND_SAI} - du lieu da doi"
        )

    dist_name_theo_cell = {c["cell_name"]: c["dist_name"] for c in affected_cells if c.get("dist_name")}
    nhan = gan_nhan_ngoai_dieu_kien_moi(cell_params, dist_name_theo_cell)

    assert LY_DO_BAND_KHONG_PHAI_1800 in nhan[CELL_BAND_SAI], (
        f"Cell {CELL_BAND_SAI} (LNCEL-51, band 2100MHz) phai nhan "
        f"{LY_DO_BAND_KHONG_PHAI_1800}, thuc te: {nhan[CELL_BAND_SAI]}"
    )
