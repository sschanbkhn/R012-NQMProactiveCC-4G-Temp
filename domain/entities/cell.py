"""
Cell entity — pure Python, khong import SQLModel.
Tu: ARCHITECTURE.md Section 3.1; BUSINESS_RULES.md Section 2, 4
"""

from dataclasses import dataclass


@dataclass
class Cell:
    # Entity mutable (khong frozen) — action_type duoc gan boi priority_assigner.py
    # (B3.3), roi co the bi ghi de thanh "skip" boi rsboost_calculator.py /
    # qrxlevmin_calculator.py (B3.4/B3.5) neu cell o cap/floor.
    #
    # CO CHU Y: entity nay KHONG co field rsboost_current/qrxlevmin_current.
    # Cell dai dien du lieu tu CDS (neighbor lookup — BUSINESS_RULES.md SS2),
    # trong khi rsboost_current/qrxlevmin_current den tu nguon khac (sync NetAct
    # hang ngay vao cell_params — DB_SCHEMA.md SS2), khac thoi diem voi CDS.
    # Nhet chung 2 nguon du lieu nay vao 1 entity se gay hieu nham la luon dong bo.
    # Dung dung kien truc: rsboost_calculator.py/qrxlevmin_calculator.py (B3.4/B3.5)
    # nhan Cell (de biet cell_name/action_type) + doc rieng gia tri hien tai qua
    # ICellParamsRepo, roi tra ve RsboostLevel/Qrxlevmin moi — khong mutate vao Cell.
    # KHONG tu them field rsboost/qrxlevmin vao day.
    cell_id: str | None
    cell_name: str
    dist_name: str
    priority: int
    huong_id: str | None
    action_type: str
    status: str
    # 2 field THEM (quyet dinh 03/10/2026, luat chon cell CR moi) - CHI
    # filter_for_cr() (Nhanh B) gan gia tri, filter_affected() (Nhanh A) de
    # None (mac dinh) vi Nhanh A khong con khai niem band/sector cho tung cell.
    # Default None o CUOI de KHONG pha vo cac noi dang dung Cell(...) kieu
    # positional (test cu, filter_affected()) ma khong biet 2 field nay.
    #   - sector: chu so cuoi huong_id cua TRAM TAT (khong phai cua cell lan
    #     can) - dung lam KHOA GOM NHOM thay cho huong_id o priority_assigner.py,
    #     vi 1 sector gio co the gop cell tu NHIEU huong_id (xem
    #     neighbor_cell_filter.py::filter_for_cr() Buoc 2/3).
    #   - band: "1800 F1"/"1800 F2" suy tu LNCEL cua CHINH CELL LAN CAN (DN
    #     cua no), KHONG phai band huong tram tat - xem BUSINESS_RULES.md
    #     muc luat chon cell CR 03/10/2026. Chi de phuc vu hien thi preview.
    sector: int | None = None
    band: str | None = None
