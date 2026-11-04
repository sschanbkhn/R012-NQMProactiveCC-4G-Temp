"""
Unit test cho RsboostCalculator — tinh rsboost_new cho cell action_type=rsboost.
Tu: BUSINESS_RULES.md Section 5; WORKFLOW.md Step 8; TASK_LIST.md B3.4

12072026: calculate() doi tu 3 tham so (tram_id, cells,
current_rsboost keyed by cell_name) sang 2 tham so (cells, current_rsboost
keyed by dist_name) - tram_id gio tu parse tu Cell.dist_name (fix dut diem bug
cu: 1 CR co the co cell lan gieng thuoc nhieu tram vat ly khac nhau, khong the
dung chung 1 tram_id truyen vao).

21072026: doi nguon parse tu MRBTS sang LNBTS (domain/services/dist_name.py::
extract_lnbts(), xem tests/domain/test_dist_name.py cho test rieng cua ham
nay) - bang tram khoa theo LNBTS, MRBTS co the khac (da verify DB that).
"""

import pytest

from domain.entities.cell import Cell
from domain.services.rsboost_calculator import RsboostCalculator
from domain.value_objects.rsboost_level import RsboostLevel


def make_cell(cell_name: str, action_type: str, tram_id: str = "160000") -> Cell:
    dist_name = f"PLMN-PLMN/MRBTS-{tram_id}/LNBTS-{tram_id}/LNCEL-11"
    return Cell(
        cell_id=dist_name,
        cell_name=cell_name,
        dist_name=dist_name,
        priority=1,
        huong_id="11",
        action_type=action_type,
        status="active",
    )


def test_cell_khong_phai_rsboost_bi_skip_khoi_output():
    cell = make_cell("c1", "qrxlevmin")
    result = RsboostCalculator().calculate([cell], {})
    assert result == []


def test_cell_rsboost_chua_o_cap_tinh_dung_next_level():
    cell = make_cell("c1", "rsboost")
    current = RsboostLevel(0.0)
    result = RsboostCalculator().calculate([cell], {cell.dist_name: current})
    assert len(result) == 1
    param = result[0]
    assert param.action_type == "rsboost"
    assert param.rsboost_new == RsboostLevel(3.0)
    assert param.rsboost_current == current
    assert param.tram_id == "160000"  # parse tu dist_name, khong truyen ngoai vao nua


def test_cell_rsboost_current_gia_tri_lien_tuc_khong_crash():
    # C1.4-fix12 (21072026) - bug that: session #198/tram 111139,
    # rsboost_current=1.77 (dB THAT ngoai RSBOOST_SCALE) crash ValueError
    # tai RsboostLevel.next_level(). calculate() PHAI chay dung, snap gia
    # tri MOI len buoc chuan gan nhat, giu gia tri CU nguyen ban khong doi.
    cell = make_cell("c1", "rsboost")
    current = RsboostLevel(1.77)
    result = RsboostCalculator().calculate([cell], {cell.dist_name: current})
    param = result[0]
    assert param.action_type == "rsboost"
    assert param.rsboost_current == RsboostLevel(1.77)  # gia tri cu giu nguyen, khong snap
    assert param.rsboost_new == RsboostLevel(3.0)  # gia tri moi snap len buoc chuan


def test_cell_rsboost_da_o_cap_thanh_skip_khong_doi_gia_tri():
    cell = make_cell("c1", "rsboost")
    current = RsboostLevel(6.0)
    result = RsboostCalculator().calculate([cell], {cell.dist_name: current})
    param = result[0]
    assert param.action_type == "skip"
    assert param.rsboost_new == current


def test_cell_khac_tram_id_deu_parse_dung_tram_id_rieng():
    # Cell lan gieng thuoc 2 tram vat ly khac nhau trong CUNG 1 CR - bug cu
    # (tram_id hardcode) se gan sai tram_id cho 1 trong 2 cell nay.
    cell_a = make_cell("cA", "rsboost", tram_id="160000")
    cell_b = make_cell("cB", "rsboost", tram_id="115750")
    current = RsboostLevel(0.0)
    result = RsboostCalculator().calculate(
        [cell_a, cell_b], {cell_a.dist_name: current, cell_b.dist_name: current}
    )
    by_name = {p.cell_name: p for p in result}
    assert by_name["cA"].tram_id == "160000"
    assert by_name["cB"].tram_id == "115750"


def test_mrbts_khac_lnbts_tram_id_lay_theo_lnbts():
    # 21072026 - mo phong 1 trong 12 nhom MRBTS != LNBTS da verify tren
    # cell_infor that (57 dong). tram_id PHAI la LNBTS (110105), KHONG duoc la
    # MRBTS (1100105) - bang tram khoa theo LNBTS, dung MRBTS se sinh tram_id
    # khong ton tai trong bang tram (FK violation neu ghi that vao cell_params).
    cell = Cell(
        cell_id="PLMN-PLMN/MRBTS-1100105/LNBTS-110105/LNCEL-11",
        cell_name="c1",
        dist_name="PLMN-PLMN/MRBTS-1100105/LNBTS-110105/LNCEL-11",
        priority=1,
        huong_id="11",
        action_type="rsboost",
        status="active",
    )
    result = RsboostCalculator().calculate([cell], {cell.dist_name: RsboostLevel(0.0)})
    assert result[0].tram_id == "110105"


def test_dist_name_khong_parse_duoc_tram_id_raise_value_error():
    cell = Cell(
        cell_id="c1", cell_name="c1", dist_name="dist-name-khong-hop-le",
        priority=1, huong_id="11", action_type="rsboost", status="active",
    )
    with pytest.raises(ValueError):
        RsboostCalculator().calculate([cell], {cell.dist_name: RsboostLevel(0.0)})


def test_dist_name_thieu_trong_current_rsboost_raise_keyerror():
    cell = make_cell("c1", "rsboost")
    with pytest.raises(KeyError):
        RsboostCalculator().calculate([cell], {})


def test_before_cr_va_cr_session_id_deu_none():
    cell = make_cell("c1", "rsboost")
    result = RsboostCalculator().calculate([cell], {cell.dist_name: RsboostLevel(0.0)})
    param = result[0]
    assert param.rsboost_before_cr is None
    assert param.cr_session_id is None
