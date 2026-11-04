"""
Unit test cho QrxlevminCalculator — tinh qrxlevmin_new cho cell action_type=qrxlevmin.
Tu: BUSINESS_RULES.md Section 6; WORKFLOW.md Step 10; TASK_LIST.md B3.5

12072026: calculate() doi tu 3 tham so (tram_id, cells,
current_qrxlevmin keyed by cell_name) sang 2 tham so (cells, current_qrxlevmin
keyed by dist_name) - cung ly do RsboostCalculator (xem test_rsboost_calculator.py).

21072026: doi nguon parse tu MRBTS sang LNBTS - cung ly do RsboostCalculator,
xem test_rsboost_calculator.py va tests/domain/test_dist_name.py.
"""

import pytest

from domain.entities.cell import Cell
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.value_objects.qrxlevmin import Qrxlevmin


def make_cell(cell_name: str, action_type: str, tram_id: str = "160000") -> Cell:
    dist_name = f"PLMN-PLMN/MRBTS-{tram_id}/LNBTS-{tram_id}/LNCEL-11"
    return Cell(
        cell_id=dist_name,
        cell_name=cell_name,
        dist_name=dist_name,
        priority=3,
        huong_id="11",
        action_type=action_type,
        status="active",
    )


def test_cell_khong_phai_qrxlevmin_bi_skip_khoi_output():
    cell = make_cell("c1", "rsboost")
    result = QrxlevminCalculator().calculate([cell], {})
    assert result == []


def test_cell_qrxlevmin_chua_o_floor_tinh_dung_decrease():
    cell = make_cell("c1", "qrxlevmin")
    current = Qrxlevmin(-120)
    result = QrxlevminCalculator().calculate([cell], {cell.dist_name: current})
    assert len(result) == 1
    param = result[0]
    assert param.action_type == "qrxlevmin"
    assert param.qrxlevmin_new == Qrxlevmin(-124)
    assert param.qrxlevmin_current == current
    assert param.tram_id == "160000"


def test_cell_qrxlevmin_da_o_floor_thanh_skip_khong_doi_gia_tri():
    cell = make_cell("c1", "qrxlevmin")
    current = Qrxlevmin(-144)
    result = QrxlevminCalculator().calculate([cell], {cell.dist_name: current})
    param = result[0]
    assert param.action_type == "skip"
    assert param.qrxlevmin_new == current


def test_cell_khac_tram_id_deu_parse_dung_tram_id_rieng():
    cell_a = make_cell("cA", "qrxlevmin", tram_id="160000")
    cell_b = make_cell("cB", "qrxlevmin", tram_id="115750")
    current = Qrxlevmin(-120)
    result = QrxlevminCalculator().calculate(
        [cell_a, cell_b], {cell_a.dist_name: current, cell_b.dist_name: current}
    )
    by_name = {p.cell_name: p for p in result}
    assert by_name["cA"].tram_id == "160000"
    assert by_name["cB"].tram_id == "115750"


def test_mrbts_khac_lnbts_tram_id_lay_theo_lnbts():
    # 21072026 - cung ly do test_rsboost_calculator.py, xem chu thich o do.
    cell = Cell(
        cell_id="PLMN-PLMN/MRBTS-1100105/LNBTS-110105/LNCEL-11",
        cell_name="c1",
        dist_name="PLMN-PLMN/MRBTS-1100105/LNBTS-110105/LNCEL-11",
        priority=1,
        huong_id="11",
        action_type="qrxlevmin",
        status="active",
    )
    result = QrxlevminCalculator().calculate([cell], {cell.dist_name: Qrxlevmin(-120)})
    assert result[0].tram_id == "110105"


def test_dist_name_khong_parse_duoc_tram_id_raise_value_error():
    cell = Cell(
        cell_id="c1", cell_name="c1", dist_name="dist-name-khong-hop-le",
        priority=1, huong_id="11", action_type="qrxlevmin", status="active",
    )
    with pytest.raises(ValueError):
        QrxlevminCalculator().calculate([cell], {cell.dist_name: Qrxlevmin(-120)})


def test_dist_name_thieu_trong_current_qrxlevmin_raise_keyerror():
    cell = make_cell("c1", "qrxlevmin")
    with pytest.raises(KeyError):
        QrxlevminCalculator().calculate([cell], {})


def test_before_cr_va_cr_session_id_deu_none():
    cell = make_cell("c1", "qrxlevmin")
    result = QrxlevminCalculator().calculate([cell], {cell.dist_name: Qrxlevmin(-120)})
    param = result[0]
    assert param.qrxlevmin_before_cr is None
    assert param.cr_session_id is None
