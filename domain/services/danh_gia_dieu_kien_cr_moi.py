"""
Gan nhan "ngoai dieu kien moi" cho cell DA CHAY CR (cell_params) - CHI DOC,
KHONG sua du lieu cu. Quyet dinh 04/10/2026: KHONG hoi to/sua CR/phieu cu -
luat band + tran 2/sector (chot 03-04/10/2026) chi ap dung cho CR chay TU
BAY GIO, du lieu CU van giu nguyen trong DB. Module nay CHI tinh toan thuan
tuy (khong I/O) de API gan nhan LUC DOC, giup nguoi van hanh biet session/cell
nao chay theo luat CU co the khac neu chay lai.

3 ly do (list rong = dat du dieu kien moi):
  BAND_KHONG_PHAI_1800   - LNCEL cua CHINH CELL (suy tu dist_name, lay tu
                           cr_affected_cells - xem ham duoi) khong khop
                           ^[13][0-9]$ (1800 F1/F2, dung luat 03/10/2026)
  KHONG_XAC_DINH_BAND    - khong tim duoc dist_name tuong ung (cell_params
                           KHONG tu luu cell_id/dist_name cho dong CR - xem
                           models/cell_params.py - phai JOIN qua
                           cr_affected_cells, session cu truoc 22/07/2026
                           khong co dong cr_affected_cells nao de doi chieu)
  VUOT_2_CELL_SECTOR     - sector (huong_id%10) cua cell nay co > 2 cell
                           CHAY CR trong CUNG session; cell vuot la cell
                           NGOAI 2 cell dau khi sap theo priority tang dan
                           (dung luat 04/10/2026, XUAT_PHIEU_MAX_PER_SECTOR=2)
"""

import re
from typing import Protocol

_LNCEL_CHAY_CR_RE = re.compile(r"^[13][0-9]$")

LY_DO_BAND_KHONG_PHAI_1800 = "BAND_KHONG_PHAI_1800"
LY_DO_KHONG_XAC_DINH_BAND = "KHONG_XAC_DINH_BAND"
LY_DO_VUOT_2_CELL_SECTOR = "VUOT_2_CELL_SECTOR"


class _CellDaChayCR(Protocol):
    # Chi can 3 thuoc tinh nay - CellParam (domain/entities/cell_param.py)
    # khop san, KHONG ep kieu cu the de ham nay khong phu thuoc nguoc vao
    # entity (tranh import vong neu sau nay CellParam chuyen cho).
    cell_name: str
    huong_id: str | None
    priority: int | None


def _lncel_local_id(dist_name: str) -> str:
    # Giong het _lncel_local_id() trong neighbor_cell_filter.py - KHONG import
    # chung vi ham do la "private" (gach dau _) cua module kia, va 2 chuc nang
    # nay doc lap ve vong doi (1 ben loc LUC CHAY CR, ben nay gan nhan LUC DOC
    # cell DA chay tu lau) - chi trung CONG THUC, khong trung NGU CANH.
    return dist_name.rsplit("LNCEL-", 1)[-1]


def gan_nhan_ngoai_dieu_kien_moi(
    cells: list[_CellDaChayCR], dist_name_theo_cell: dict[str, str]
) -> dict[str, list[str]]:
    """cells: cac cell DA CHAY CR cua 1 session (vd ICellParamsRepo.get_by_cr_session_id()).
    dist_name_theo_cell: {cell_name: dist_name} suy tu cr_affected_cells CUNG
    session (dist_name la DN that cua CHINH CELL, mang LNCEL cua no - KHAC
    huong_id cua cell_params, von la huong_id cua TRAM TAT chu khong phai cua
    cell lan can). Cell KHONG co trong dict nay -> KHONG_XAC_DINH_BAND.

    Tra {cell_name: [ly_do,...]} - list RONG nghia la dat du dieu kien moi.
    Dict luon co DU moi cell trong `cells` lam key (ke ca khi list rong), de
    caller khong phai tu kiem .get() voi default.
    """
    nhan: dict[str, list[str]] = {c.cell_name: [] for c in cells}

    for c in cells:
        dist_name = dist_name_theo_cell.get(c.cell_name)
        if dist_name is None:
            nhan[c.cell_name].append(LY_DO_KHONG_XAC_DINH_BAND)
            continue
        if not _LNCEL_CHAY_CR_RE.match(_lncel_local_id(dist_name)):
            nhan[c.cell_name].append(LY_DO_BAND_KHONG_PHAI_1800)

    # Sector = huong_id (cua TRAM TAT, luu tren chinh cell_params) % 10 - GIONG
    # dinh nghia sector dung xuyen suot du an (domain/services/neighbor_cell_filter.py,
    # application/xuat_phieu_use_case.py). huong_id khong phai so hop le (None
    # hoac chuoi la) -> gom vao nhom sector=None, CUNG tran nhu sector so thuc
    # (dung tinh than "sector NULL la 1 nhom rieng" da chot 04/10/2026).
    theo_sector: dict[int | None, list[_CellDaChayCR]] = {}
    for c in cells:
        sector = int(c.huong_id) % 10 if c.huong_id is not None and c.huong_id.isdigit() else None
        theo_sector.setdefault(sector, []).append(c)

    for nhom in theo_sector.values():
        # Sap theo priority TANG DAN (gia tri nho = uu tien cao, dung quy uoc
        # CDS/BUSINESS_RULES.md xuyen suot du an) - 2 cell DAU la "trong han
        # muc", tu cell thu 3 tro di la vuot. priority None xep CUOI (coi nhu
        # uu tien thap nhat) thay vi crash so sanh None < int.
        nhom_sap = sorted(nhom, key=lambda c: (c.priority is None, c.priority))
        for c in nhom_sap[2:]:
            nhan[c.cell_name].append(LY_DO_VUOT_2_CELL_SECTOR)

    return nhan
