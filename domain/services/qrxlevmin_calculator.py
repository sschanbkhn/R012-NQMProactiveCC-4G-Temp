"""
QrxlevminCalculator.
Tu: BUSINESS_RULES.md Section 6 (Qrxlevmin Calculation); WORKFLOW.md Step 10;
    TASK_LIST.md B3.5
"""

from domain.entities.cell import Cell
from domain.entities.cell_param import CellParam
from domain.services.dist_name import extract_lnbts
from domain.value_objects.qrxlevmin import Qrxlevmin


class QrxlevminCalculator:
    def calculate(
        self, cells: list[Cell], current_qrxlevmin: dict[str, Qrxlevmin]
    ) -> list[CellParam]:
        # tram_id parse rieng tu cell.dist_name, khong nhan tu ngoai nua —
        # ly do giong het RsboostCalculator (cell_infor.dn_lncel co the lech
        # voi dn_sib cung dong, khong dung lam nguon tram_id — quyet dinh 12/07/2026).
        #
        # LNBTS (khong phai MRBTS) - ly do giong het RsboostCalculator, xem
        # domain/services/dist_name.py.
        #
        # current_qrxlevmin gio key theo cell.dist_name (khong phai cell_name),
        # do ICellInforRepo.get_qrxlevmin_by_neighbor_dns() tra ve dict key = dn.
        result: list[CellParam] = []
        for cell in cells:
            if cell.action_type != "qrxlevmin":
                continue

            tram_id = extract_lnbts(cell.dist_name)

            current = current_qrxlevmin[cell.dist_name]
            new_level = current.decrease()
            action = "skip" if new_level == current else "qrxlevmin"

            result.append(
                CellParam(
                    tram_id=tram_id,
                    cell_name=cell.cell_name,
                    huong_id=cell.huong_id,
                    priority=cell.priority,
                    action_type=action,
                    qrxlevmin_current=current,
                    qrxlevmin_new=new_level,
                    sector=cell.sector,
                    band=cell.band,
                )
            )
        return result
