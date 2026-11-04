"""
Tram entity — pure Python, khong import SQLModel.
Tu: ARCHITECTURE.md Section 3.1
"""

from dataclasses import dataclass


@dataclass
class Tram:
    # Entity mutable (khong frozen) — khac value object bat bien rsboost/qrxlevmin.
    # Chi giu 5 field ma domain logic (BUSINESS_RULES.md) thuc su dung toi —
    # cac field con lai cua bang tram (id, ten_quan_ly, ma_csht, ma_tinh,
    # ten_thiet_bi, last_synced_at, created_at, updated_at) la persistence
    # detail, thuoc models/tram.py (B4.1), khong phai business concept.
    tram_id: str
    tram_name: str
    longitude: float | None
    latitude: float | None
    trang_thai: str
