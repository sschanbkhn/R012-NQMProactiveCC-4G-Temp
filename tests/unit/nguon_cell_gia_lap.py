"""
Nguon cell GIA LAP cho test DIEU PHOI cua TriggerCrUseCase/PreviewCrUseCase
(SUA 18/10/2026 - BO CDS).

=== VI SAO CO FILE NAY ===
Tu 18/10/2026 code san pham CHI con nhanh HO (_lay_du_lieu_goc_ho), nhanh CDS
da xoa. test_trigger_cr_use_case.py / test_preview_cr_use_case.py kiem phan
DIEU PHOI (18 buoc SSE, guard, loi giua chung, dinh tuyen OSS, rsboost/
qrxlevmin, ghi cr_affected_cells...) - KHONG kiem thuat toan chon cell. Fixture
cu cua 2 file viet theo dang du lieu CDS (_RAW_HUONGS); viet lai sang du lieu
HO (toa do + Delaunay) chi de doi cach SINH danh sach cell la ton cong ma khong
kiem them gi.

Nen o day thay _lay_du_lieu_goc_ho() cua use case bang 1 ham gia: doc
network_gw.get_cell_neighbors (mock) roi chuyen thanh Cell bang
NeighborCellFilter + PriorityAssigner (2 domain service van con, co test rieng).
Thuat toan HO THAT duoc kiem o test_trigger_cr_use_case_ho.py/
test_preview_cr_use_case_ho.py.
"""

from domain.services.neighbor_cell_filter import NeighborCellFilter
from domain.services.priority_assigner import PriorityAssigner


def gan_nguon_gia_lap(uc, network_gw) -> None:
    async def _lay(tram_id: str):
        raw_huongs = await network_gw.get_cell_neighbors(tram_id)
        ngoai: list[str] = []
        ngoai_chi_tiet: list[dict] = []
        f = NeighborCellFilter()
        affected = f.filter_affected(
            raw_huongs, tram_id, ngoai_pham_vi=ngoai, ngoai_pham_vi_chi_tiet=ngoai_chi_tiet
        )
        cells = f.filter_for_cr(
            raw_huongs, tram_id, affected_cells=affected,
            cell_ngoai_pham_vi=ngoai, cell_ngoai_pham_vi_chi_tiet=ngoai_chi_tiet,
        )
        # Nhanh HO that tu gan action_type truoc dinh tuyen OSS - lam tuong tu.
        PriorityAssigner().assign(cells)
        n_cell_goc = sum(len(h.get("cells", [])) for h in raw_huongs)
        return affected, cells, len(raw_huongs), n_cell_goc, ngoai, ngoai_chi_tiet, None

    uc._lay_du_lieu_goc_ho = _lay  # noqa: SLF001 - seam test, xem docstring
