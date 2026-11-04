"""
Unit test cho PriorityAssigner — assign action_type theo priority.
Tu: BUSINESS_RULES.md Section 4.1; TASK_LIST.md B3.3
"""

from domain.entities.cell import Cell
from domain.services.priority_assigner import PriorityAssigner


def make_cell(priority: int) -> Cell:
    return Cell(
        cell_id="c1",
        cell_name="4G-c1",
        dist_name="c1",
        priority=priority,
        huong_id="11",
        action_type="",
        status="active",
    )


def test_rank_1_gan_rsboost_rank_2_gan_qrxlevmin():
    # SUA 09/2026 (BUSINESS_RULES.md SS4.1 - 2 cell/huong): truoc day priority
    # 1 VA 2 CUNG gan rsboost (RSBOOST_RANKS={1,2}). Nay 1 huong chi con 2
    # cell nen rank 1 -> rsboost, rank 2 -> qrxlevmin - PHAI doi CUNG LUC voi
    # MAX_CELLS_PER_HUONG (neighbor_cell_filter.py), xem comment dau
    # priority_assigner.py.
    c1, c2 = make_cell(1), make_cell(2)
    PriorityAssigner().assign([c1, c2])
    assert c1.action_type == "rsboost"
    assert c2.action_type == "qrxlevmin"


def test_rank_3_tro_len_khong_gan_gi_ca():
    # SUA 09/2026: RSBOOST_RANKS/QRXLEVMIN_RANKS gio CHI co {1}/{2} - rank 3+
    # (neu lo xay ra, vd goi assign() truc tiep voi > MAX_CELLS_PER_HUONG cell
    # nhu test nay co y lam) KHONG khop nhanh nao, giu nguyen action_type =
    # "" (rong). Day CHINH LA rui ro "cell bien mat khoi CR am tham" da ghi
    # trong comment dau file - test nay khoa hanh vi do lai, KHONG phai xac
    # nhan no la mong muon.
    c1, c2, c3, c4 = make_cell(1), make_cell(2), make_cell(3), make_cell(4)
    PriorityAssigner().assign([c1, c2, c3, c4])
    assert c1.action_type == "rsboost"
    assert c2.action_type == "qrxlevmin"
    assert c3.action_type == ""
    assert c4.action_type == ""


def test_mutate_in_place_khong_tra_ve_list_moi():
    cells = [make_cell(1)]
    result = PriorityAssigner().assign(cells)
    assert result is None
    assert cells[0].action_type == "rsboost"


def test_input_rong_khong_loi():
    PriorityAssigner().assign([])
