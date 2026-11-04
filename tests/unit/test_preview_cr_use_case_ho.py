"""
Unit test cho PreviewCrUseCase nhanh HO (BUOC 4b, 08/10/2026, yeu cau truc
tiep user) - xac nhan API preview tra them cac field OPTIONAL (x_co,
quan_he_day_du, %HO/SR/layer/co moi cell) dung tu PlanResult.ho_extra.
Tai su dung fixture tu tests/unit/test_trigger_cr_use_case_ho.py (KHONG
dinh nghia lai HO_ROWS/dn_map/toa do).

SUA 14/10/2026 (yeu cau truc tiep user) - BO field nguon_du_lieu (gia dinh
"7 ngay" sai, NA14 that ra cung gop theo TUAN giong NA09 - xem
docs/BUSINESS_RULES.md) - xoa assert/test rieng cho field nay.
"""

from unittest.mock import AsyncMock

from application.preview_cr_use_case import PreviewCrUseCase
from tests.unit.test_trigger_cr_use_case_ho import (
    _HO_ROWS,
    X_ID,
    _fake_cell_infor_repo,
    _fake_ho_neighbor_repo,
    _make_use_case_ho,
)


async def test_preview_ho_tra_them_x_co_va_quan_he_day_du():
    trigger_uc = _make_use_case_ho()
    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_ids.return_value = []
    preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)

    result = await preview_uc.execute(tram_id=X_ID, tram_name="4G-BDH288M-HNI", action="shutdown")

    assert result.x_co == []  # X khong co co nao (TIN_CAY, khong HO_DI_XA, du du lieu)
    assert result.sectors_it_du_lieu == []  # du du lieu HO (xem test rieng cho truong hop nguoc lai)
    assert len(result.quan_he_day_du) == 2
    # Moi cell_bi_anh_huong/cells_chay_cr duoc enrich %HO/SR/layer tu ho_extra.
    cell_a = next(c for c in result.cells_bi_anh_huong if c.cell_name == "4G-SIA001M13-HNI")
    assert cell_a.pct_ho == 0.6
    assert cell_a.so_ho == 3000
    assert cell_a.sr == 99.0
    assert cell_a.sector == 1
    assert cell_a.sectors_khac == []
    cell_b = next(c for c in result.cells_chay_cr if c.cell_name == "4G-SIA001M13-HNI")
    assert cell_b.pct_ho == 0.6
    assert cell_b.action_type == "rsboost"


async def test_preview_ho_cell_can_ghep_ten_van_tra_ra_de_biet_nhung_khong_co_ten():
    cell_infor_repo_thieu = _fake_cell_infor_repo()
    cell_infor_repo_thieu.get_dn_map_theo_enb_lcr.return_value = {
        (200, 13): {"dn_lncel": "PLMN-PLMN/MRBTS-200/LNBTS-200/LNCEL-13", "cell_name": "4G-SIA001M13-HNI"},
    }
    trigger_uc = _make_use_case_ho(cell_infor_repo=cell_infor_repo_thieu)
    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_ids.return_value = []
    preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)

    result = await preview_uc.execute(tram_id=X_ID, tram_name="4G-BDH288M-HNI", action="shutdown")

    khong_ten = [c for c in result.cells_bi_anh_huong if c.cell_name is None]
    assert len(khong_ten) == 1
    assert khong_ten[0].pct_ho == 0.4
    assert khong_ten[0].tram_id is None


async def test_preview_ho_tra_sectors_it_du_lieu_lay_tu_ho_extra():
    # THEM (yeu cau truc tiep user) - sectors_it_du_lieu da co san o tang
    # application (TriggerCrUseCase._lay_du_lieu_goc_ho(), tu 08/10/2026), NAY
    # lo ra PreviewResult/API. Sector 2 (THEM, attempt=100 << N_MIN_HO_SECTOR
    # 3156) phai bi flag IT_DU_LIEU; sector 1 (goc, attempt lon) thi khong.
    rows = list(_HO_ROWS) + [{
        "source_sector": 2, "target_enb": 202, "target_lcr": 99, "target_eci": 202 * 256 + 99,
        "ho_attempt": 100, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M21-HNI",
        "ngay_du_lieu": "2026-09-28",
    }]
    trigger_uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows))
    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_ids.return_value = []
    preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)

    result = await preview_uc.execute(tram_id=X_ID, tram_name="4G-BDH288M-HNI", action="shutdown")

    assert result.sectors_it_du_lieu == [2]


async def test_preview_ho_cell_o_2_sector_tra_sector_thang_va_sectors_khac():
    # THEM 12/10/2026 (yeu cau truc tiep user, "THEM SECTOR CHO BANG A") -
    # xac nhan sector/sectors_khac toi duoc AffectedCellItem (API thuc su
    # nguoi dung thay), khong chi o ho_extra noi bo (da test rieng o
    # tests/unit/test_trigger_cr_use_case_ho.py).
    rows = [
        {"source_sector": 1, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
         "ho_attempt": 2000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M11-HNI", "ngay_du_lieu": "2026-09-28"},
        {"source_sector": 1, "target_enb": 201, "target_lcr": 11, "target_eci": 201 * 256 + 11,
         "ho_attempt": 3000, "ho_sr": 98.0, "source_lncel_name": "4G-BDH288M11-HNI", "ngay_du_lieu": "2026-09-28"},
        {"source_sector": 2, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
         "ho_attempt": 5000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M12-HNI", "ngay_du_lieu": "2026-09-28"},
    ]
    trigger_uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows))
    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_ids.return_value = []
    preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)

    result = await preview_uc.execute(tram_id=X_ID, tram_name="4G-BDH288M-HNI", action="shutdown")

    cell_a = next(c for c in result.cells_bi_anh_huong if c.cell_name == "4G-SIA001M13-HNI")
    assert cell_a.sector == 2
    assert cell_a.sectors_khac == [1]
    # cells_chay_cr (B) KHONG duoc dung sector tu theo_cell_name - phai GIU
    # sector CUA RIENG B (p.sector, co the KHAC sector cua A neu logic B
    # chon khac - o day trung nhau vi cung 1 cell, nhung field phai den tu
    # dung nguon, khong bi ghi de boi ho_extra).
    cell_b = next(c for c in result.cells_chay_cr if c.cell_name == "4G-SIA001M13-HNI")
    assert cell_b.sector == 2
