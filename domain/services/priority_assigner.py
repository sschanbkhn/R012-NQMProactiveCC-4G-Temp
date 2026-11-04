"""
PriorityAssigner.
Tu: BUSINESS_RULES.md Section 4.1 (Cell Treatment); TASK_LIST.md B3.3
"""

from collections import defaultdict

from domain.entities.cell import Cell

# {1,2}/{3,4} -> {1}/{2} (quyet dinh van hanh 09/2026, user chot): 1 huong chi
# con 2 cell (MAX_CELLS_PER_HUONG o domain/services/neighbor_cell_filter.py),
# nen rank 1 = rsboost, rank 2 = qrxlevmin.
#
# PHAI sua CUNG LUC voi MAX_CELLS_PER_HUONG: neu tran van la 4 ma rank chi map
# 1-2 thi cell rank 3/4 giu action_type = "" -> khong vao nhanh rsboost lan
# qrxlevmin, bien mat khoi CR ma khong loi.
#
# Huong chi co 1 cell -> chi rank 1 -> chi rsboost, KHONG loi (vong lap
# enumerate ben duoi khong doi hoi du 2 cell).
RSBOOST_RANKS = {1}
QRXLEVMIN_RANKS = {2}


class PriorityAssigner:
    def assign(self, cells: list[Cell]) -> None:
        # BUG CU: dung cell.priority GOC tu CDS de xac dinh rsboost/qrxlevmin —
        # sai vi priority goc co the co khoang trong (VD 1,2,5,6) sau khi
        # nb_lncel_filter/huong_cell_selector loai bot cell NB-/MBF- o giua.
        # SUA: dung THU HANG trong danh sach cell cuoi cung cua MOI HUONG
        # (rank 1,2 theo thu tu cell.priority tang dan trong tung huong - toi da
        # 2 cell/huong tu 09/2026), khong dung cell.priority goc nua.
        # SUA 03/10/2026 (luat chon cell CR moi): gom nhom theo cell.sector
        # thay vi cell.huong_id - tu khi filter_for_cr() gop cell tu NHIEU
        # huong_id vao CUNG 1 sector (xem neighbor_cell_filter.py), 2 cell
        # "cung nhom de xep rank 1/2" co the mang huong_id goc KHAC nhau.
        # Fallback ve huong_id khi sector=None (test cu/caller tu dung Cell
        # khong qua filter_for_cr(), VD test_priority_assigner.py) - giu
        # nguyen hanh vi cu cho cac truong hop do, KHONG bat sua test.
        by_huong: dict[str | int | None, list[Cell]] = defaultdict(list)
        for cell in cells:
            key = cell.sector if cell.sector is not None else cell.huong_id
            by_huong[key].append(cell)

        for huong_cells in by_huong.values():
            huong_cells.sort(key=lambda c: c.priority)
            for rank, cell in enumerate(huong_cells, start=1):
                if rank in RSBOOST_RANKS:
                    cell.action_type = "rsboost"
                elif rank in QRXLEVMIN_RANKS:
                    cell.action_type = "qrxlevmin"
            # priority ngoai 1-4: khong xay ra theo BUSINESS_RULES.md SS2.1
            # (CDS luon tra priority 1|2|3|4) — khong validate cho case nay.
