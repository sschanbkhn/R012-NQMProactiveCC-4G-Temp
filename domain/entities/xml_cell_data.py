"""
XmlCellData entity — pure Python, khong import SQLModel.
Tu: BUSINESS_RULES.md Section 7 (Nokia XML); TASK_LIST.md B7.1

Merge cua Cell (cell_id) + CellParam (action_type/rsboost_new/qrxlevmin_new) —
2 entity nay khong entity nao mot minh du du lieu de build 1 managedObject block
(CellParam co chu y ro rang KHONG chua cell_id/dist_name, xem domain/entities/
cell_param.py dong 29-34). Viec merge Cell + CellParam thanh XmlCellData la
trach nhiem cua TriggerCrUseCase (C2.1, chua code — xem TODO note tai do).
"""

from dataclasses import dataclass

from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel


@dataclass(frozen=True)
class XmlCellData:
    cell_id: str
    action_type: str  # "rsboost" | "qrxlevmin" — "skip" KHONG duoc dua vao day,
    # caller (TriggerCrUseCase) loc bo truoc khi tao XmlCellData. XmlBuilder
    # (adapters/netact/xml_builder.py) van tu loai phong thu neu gap "skip" lot
    # qua — xem chu y trong file do.
    rsboost_new: RsboostLevel | None
    qrxlevmin_new: Qrxlevmin | None
