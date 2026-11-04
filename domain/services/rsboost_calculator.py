"""
RsboostCalculator.
Tu: BUSINESS_RULES.md Section 5 (Rsboost Calculation); WORKFLOW.md Step 8;
    TASK_LIST.md B3.4
"""

from domain.entities.cell import Cell
from domain.entities.cell_param import CellParam
from domain.services.dist_name import extract_lnbts
from domain.value_objects.rsboost_level import RsboostLevel


class RsboostCalculator:
    def calculate(
        self, cells: list[Cell], current_rsboost: dict[str, RsboostLevel]
    ) -> list[CellParam]:
        # tram_id KHONG con truyen tu ngoai - parse rieng cho tung cell tu
        # cell.dist_name, vi cell_infor.dn_lncel co the lech voi dn_fdd cung
        # dong (bug "lech dong" da xac nhan), khong dung lam nguon tram_id.
        #
        # LNBTS (khong phai MRBTS) - da verify DB that: bang tram khoa theo
        # LNBTS, MRBTS co the khac LNBTS (12 nhom, gay FK violation neu dung
        # MRBTS lam tram_id). Xem domain/services/dist_name.py de biet chi tiet.
        #
        # current_rsboost gio key theo cell.dist_name (khong phai cell_name),
        # do repo query LIKE tren dn_fdd va tra ve dict key = dn cua neighbor.
        result: list[CellParam] = []
        for cell in cells:
            if cell.action_type != "rsboost":
                continue

            tram_id = extract_lnbts(cell.dist_name)

            current = current_rsboost[cell.dist_name]
            new_level = current.next_level()
            action = "skip" if new_level == current else "rsboost"

            result.append(
                CellParam(
                    tram_id=tram_id,
                    cell_name=cell.cell_name,
                    huong_id=cell.huong_id,
                    priority=cell.priority,
                    action_type=action,
                    rsboost_current=current,
                    rsboost_new=new_level,
                    sector=cell.sector,
                    band=cell.band,
                )
            )
        return result
