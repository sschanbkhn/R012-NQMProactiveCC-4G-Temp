"""
CellParam entity — pure Python, khong import SQLModel.
Tu: DB_SCHEMA.md Section 2 (cell_params); UI_DESIGN.md interface CellParam;
    WORKFLOW.md buoc 7, 9, 11; TASK_LIST.md B5.3
"""

from dataclasses import dataclass

from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel


@dataclass
class CellParam:
    # Entity mutable (khong frozen), data holder bang qua ranh gioi
    # ICellParamsRepo — khong phai value object bat bien nhu RsboostLevel/Qrxlevmin.
    #
    # Khac voi Cell (B2.5, co chu y KHONG co field rsboost/qrxlevmin vi Cell dai
    # dien du lieu CDS, khac nguon/thoi diem voi RF param): CellParam CHINH LA
    # entity dai dien cho RF param (rsboost/qrxlevmin) tu NetAct — khong co xung
    # dot nguon du lieu nao can tranh, nen dung thang RsboostLevel/Qrxlevmin thay
    # vi float tho, tai su dung logic from_raw()/next_level()/decrease() da co.
    #
    # Cung 1 method upsert() duoc goi o 2 thoi diem khac nhau voi tap field khac
    # nhau (sync-netact chi ghi *_current; CR-trigger flow buoc 11 ghi
    # *_before_cr/*_new/action_type/cr_session_id) — nen toan bo field RF la
    # Optional, khong bat buoc du ca 6.
    #
    # Field DB KHONG dua vao day (persistence detail, cung ly do loai nhu
    # Tram/Cell): id (SERIAL PK — khong method nao cua ICellParamsRepo can),
    # cell_id (conflict key la (tram_id, cell_name), khong phai cell_id),
    # dist_name_base/dist_name_lncel_fdd/dist_name_sib (dung de build XML tu
    # Cell.dist_name trong luong in-memory, khong re-query qua CellParam),
    # last_synced_at/created_at/updated_at (audit timestamp).
    tram_id: str
    cell_name: str
    huong_id: str | None = None
    priority: int | None = None
    action_type: str | None = None
    rsboost_current: RsboostLevel | None = None
    rsboost_before_cr: RsboostLevel | None = None
    rsboost_new: RsboostLevel | None = None
    qrxlevmin_current: Qrxlevmin | None = None
    qrxlevmin_before_cr: Qrxlevmin | None = None
    qrxlevmin_new: Qrxlevmin | None = None
    cr_session_id: int | None = None
    # 2 field THEM (quyet dinh 03/10/2026, luat chon cell CR moi) - copy
    # nguyen tu Cell.sector/Cell.band (xem domain/entities/cell.py) qua
    # RsboostCalculator/QrxlevminCalculator, CHI de PreviewCrUseCase doc ra
    # tra len API (KHONG phai field DB - giong ly do loai cell_id/dist_name_*
    # o comment dau file, khong ghi vao cell_params).
    sector: int | None = None
    band: str | None = None
